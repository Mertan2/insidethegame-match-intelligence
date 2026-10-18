"""Broadcast director: decides what the commentator could talk about next.

Watches every event and every frame and emits three kinds of briefs for the narrator:

- play_by_play: what is on screen right now (who has the ball, where, the current move,
  what just happened), so commentary follows the picture;
- fun_fact: milestones and records as they happen (long passing moves, fastest shot,
  braces, headed or weak-foot goals, saves, distance covered, ...);
- recap: a running summary every few minutes, plus half-time and full-time recaps.

Every number in a brief comes from the tracking and event data; the narrator only phrases it.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

import numpy as np

from ..models import Event
from .base import Insight, MatchState, Plugin

PBP_EVERY_S = 6.0
RECAP_EVERY_S = 240.0
MOVE_MILESTONES = (8, 12, 16, 20, 25)
PLAYER_PASS_MILESTONES = (15, 25, 40, 60)
TEAM_PASS_MILESTONES = (100, 200, 300, 400)
DISTANCE_MILESTONES_KM = (1, 2, 3, 4, 5, 6, 8, 10)
MAX_STEP_M = 1.25  # per-frame movement above this is a restart reposition, not running


class DirectorPlugin(Plugin):
    name = "director"
    description = "Broadcast director: play-by-play of what's on screen, fun facts and running recaps"

    def reset(self, state: MatchState) -> None:
        self.recent: deque[Event] = deque(maxlen=40)
        self.move_team: str | None = None
        self.move_len = 0
        self.move_announced = False
        self.best_move = 0
        self.passes_done: dict[str, int] = defaultdict(int)
        self.team_passes: dict[str, int] = defaultdict(int)
        self.goals: dict[str, int] = defaultdict(int)
        self.team_shots: dict[str, int] = defaultdict(int)
        self.team_goals: dict[str, int] = defaultdict(int)
        self.saves: dict[str, int] = defaultdict(int)
        self.headers_shots = 0
        self.fastest_shot = 0.0
        self.longest_pass = 0.0
        self.distance: dict[str, float] = defaultdict(float)
        self.km_announced = 0
        self.possession_frames: dict[str, int] = defaultdict(int)
        self._prev: dict[str, np.ndarray] = {}
        self.fired: set[str] = set()
        self.said: set[str] = set()
        self.team_best_move: dict[str, int] = defaultdict(int)
        self.last_pbp_t = -1e9
        self.last_recap_t = 0.0
        self._insights: list[Insight] = []

    # ------------------------------------------------------------------ helpers
    def _fact(self, key: str, t: float, text: str, team: str | None = None, player_id: str | None = None,
              category: str = "milestone", importance: float = 0.64) -> None:
        if key in self.fired or text in self.said:
            return
        self.fired.add(key)
        self.said.add(text)
        self._insights.append(Insight(t=t, kind="fun_fact", importance=importance, source=self.name, team=team,
                                      player_id=player_id, headline=text, data={"fun_fact": text, "category": category}))

    def drain_insights(self) -> list[Insight]:
        out, self._insights = self._insights, []
        return out

    # ------------------------------------------------------------------ events
    def on_event(self, event: Event, state: MatchState) -> list[Insight]:
        self.recent.append(event)
        d, t, side, pid = event.data, event.t, event.team, event.player_id
        name = state.player_name(pid) if pid else ""
        team = state.team_name(side) if side else ""

        if event.type == "possession_change" or event.type in ("goal", "half_time", "full_time", "kickoff"):
            self._end_move(state, t)
        if event.type == "pass":
            if d.get("outcome") == "complete" and side:
                if self.move_team != side:
                    self._end_move(state, t)
                    self.move_team = side
                self.move_len += 1
                self.team_passes[side] += 1
                self.passes_done[pid or ""] += 1
                for m in MOVE_MILESTONES:
                    if self.move_len == m and m > self.team_best_move[side]:  # only when the team beats its own best
                        self.team_best_move[side] = m
                        self.move_announced = True
                        self._fact(f"move-{side}-{m}", t, f"{team} have strung together {m} passes in a row without losing the ball",
                                   side, None, "passing move")
                n = self.passes_done[pid or ""]
                others = [v for k, v in self.passes_done.items() if k != (pid or "")]
                if n in PLAYER_PASS_MILESTONES and n > max(others, default=0):  # a clear leader, not a tie
                    self._fact(f"pp-{pid}-{n}", t, f"{name} has completed {n} passes, more than any other player on the pitch",
                               side, pid, "passing")
                if self.team_passes[side] in TEAM_PASS_MILESTONES:
                    self._fact(f"tp-{side}-{self.team_passes[side]}", t,
                               f"That's {team}'s {self.team_passes[side]}th completed pass of the match", side, None, "passing")
                dist = float(d.get("distance") or 0)
                if dist >= 40 and dist >= self.longest_pass + 3:
                    self.longest_pass = dist
                    self._fact(f"lp-{t:.0f}", t, f"{name}'s {dist:.0f}-metre pass is the longest completed pass of the match so far",
                               side, pid, "record")
            elif side and self.move_team == side:
                self._end_move(state, t)
        elif event.type == "shot" and side:
            self.team_shots[side] += 1
            kmh = float(d.get("speed_kmh") or 0)
            if kmh >= 95 and kmh > self.fastest_shot:
                self._fact(f"fs-{t:.0f}", t, f"{name}'s shot at {kmh:.0f} km/h is the fastest of the match so far", side, pid, "record")
            self.fastest_shot = max(self.fastest_shot, kmh)
            if d.get("body_part") == "head":
                self.headers_shots += 1
                if self.headers_shots == 1:
                    self._fact("first-header", t, f"{name} has the first headed attempt of the match", side, pid, "first")
            if d.get("outcome") == "saved":
                keeper_side = "away" if side == "home" else "home"
                self.saves[keeper_side] += 1
                if self.saves[keeper_side] in (3, 5, 7):
                    self._fact(f"sv-{keeper_side}-{self.saves[keeper_side]}", t,
                               f"That's save number {self.saves[keeper_side]} for the {state.team_name(keeper_side)} goalkeeper",
                               keeper_side, None, "goalkeeping")
            if self.team_goals[side] == 0 and self.team_shots[side] in (6, 9, 12):
                self._fact(f"drought-{side}-{self.team_shots[side]}", t,
                           f"{team} have now had {self.team_shots[side]} shots without scoring", side, None, "streak")
        elif event.type == "goal" and side:
            self.team_goals[side] += 1
            if pid:
                self.goals[pid] += 1
                shot = next((e for e in reversed(self.recent) if e.type == "shot" and e.player_id == pid), None)
                if self.goals[pid] == 2:
                    self._fact(f"brace-{pid}", t, f"That's a brace for {name}, two goals in this match", side, pid, "scoring", 0.7)
                elif self.goals[pid] == 3:
                    self._fact(f"hat-{pid}", t, f"Hat-trick! {name} has three goals", side, pid, "scoring", 0.75)
                if shot is not None and shot.data.get("body_part") == "head":
                    self._fact(f"hg-{t:.0f}", t, f"{name}'s goal was a header", side, pid, "scoring", 0.7)
                elif shot is not None and shot.data.get("weak_foot"):
                    foot = "left" if shot.data.get("body_part") == "left_foot" else "right"
                    self._fact(f"wf-{t:.0f}", t, f"{name} scored with the weaker {foot} foot", side, pid, "scoring", 0.7)
        elif event.type in ("half_time", "full_time"):
            label = "half-time" if event.type == "half_time" else "full-time"
            self._insights.append(Insight(t=t, kind=f"{event.type}_recap", importance=0.9, source=self.name,
                                          headline=f"{label.capitalize()} recap", data={"recap": self._recap_text(state, t, label)}))
            self.last_recap_t = t
        return []

    def _end_move(self, state: MatchState, t: float) -> None:
        if self.move_team and self.move_len >= 10 and self.move_len > self.best_move:
            self.best_move = self.move_len
            if not self.move_announced:  # don't repeat a move we just called mid-flow
                    self._fact(f"best-move-{t:.0f}", t, f"That {self.move_len}-pass move was the longest of the match so far",
                           self.move_team, None, "record")
        self.move_len = 0
        self.move_announced = False

    # ------------------------------------------------------------------ frames
    def on_frame(self, state: MatchState) -> dict[str, Any] | None:
        frame = state.frame
        assert frame is not None
        if frame.owner:
            self.possession_frames[state.players[frame.owner].team] += 1
        for pid, x, y in frame.players:
            pos = np.array([x, y])
            prev = self._prev.get(pid)
            self._prev[pid] = pos
            if prev is not None:
                step = float(np.linalg.norm(pos - prev))
                if step <= MAX_STEP_M:
                    self.distance[pid] += step
        if frame.f % state.meta.fps == 0 and self.distance:
            leader, metres = max(self.distance.items(), key=lambda kv: kv[1])
            for km in DISTANCE_MILESTONES_KM:
                if metres >= km * 1000 and self.km_announced < km:
                    self.km_announced = km
                    self._fact(f"km-{km}", frame.t, f"{state.player_name(leader)} is the first player to cover {km} km in this match",
                               state.players[leader].team, leader, "running")
        t = frame.t
        if frame.owner and t - self.last_pbp_t >= PBP_EVERY_S:
            self.last_pbp_t = t
            on_screen = self._on_screen(state)
            self._insights.append(Insight(t=t, kind="play_by_play", importance=0.57, source=self.name,
                                          team=state.players[frame.owner].team, player_id=frame.owner,
                                          headline=on_screen, data={"on_screen": on_screen, "recent_play": self._recent_play(state, t)}))
        if t - self.last_recap_t >= RECAP_EVERY_S:
            self.last_recap_t = t
            self._insights.append(Insight(t=t, kind="recap", importance=0.75, source=self.name, headline="Running recap",
                                          data={"recap": self._recap_text(state, t, f"minute {int(t // 60) + 1}")}))
        return self.snapshot() if frame.f % state.meta.fps == 0 else None

    def _on_screen(self, state: MatchState) -> str:
        frame = state.frame
        assert frame is not None and frame.owner
        p = state.players[frame.owner]
        x, y = next((px, py) for pid, px, py in frame.players if pid == frame.owner)
        ax, ay = (x, y) if p.team == "home" else (105 - x, 68 - y)  # attacking frame
        if ax > 88.5 and 13.84 < ay < 54.16:
            zone = "in the opponents' penalty area"
        elif ax > 70:
            zone = "in the final third"
        elif ax > 35:
            zone = "in midfield"
        else:
            zone = "in their own half"
        side = "on the left" if ay > 45 else "on the right" if ay < 23 else "through the middle"
        move = f", {self.move_len} passes into this move" if self.move_team == p.team and self.move_len >= 3 else ""
        return f"{p.name} ({state.team_name(p.team)}) has the ball {zone} {side}{move}"

    def _recent_play(self, state: MatchState, t: float) -> str:
        bits: list[str] = []
        for e in list(self.recent)[-8:]:
            if t - e.t > 12:
                continue
            who = state.player_name(e.player_id) if e.player_id else ""
            if e.type == "pass" and e.data.get("outcome") == "complete" and e.data.get("receiver_id"):
                bits.append(f"{who} to {state.player_name(e.data['receiver_id'])}")
            elif e.type == "tackle" and e.data.get("success"):
                bits.append(f"{who} wins a tackle")
            elif e.type == "possession_change" and e.data.get("cause") == "interception":
                bits.append(f"{who} intercepts")
            elif e.type in ("corner", "throw_in", "goal_kick"):
                bits.append(f"{e.type.replace('_', ' ')} to {state.team_name(e.team)}")
        return "; ".join(bits[-4:])

    def _recap_text(self, state: MatchState, t: float, label: str) -> str:
        frame = state.frame
        score = frame.score if frame else {"home": 0, "away": 0}
        total = sum(self.possession_frames.values()) or 1
        poss = {s: round(100 * self.possession_frames[s] / total) for s in ("home", "away")}
        h, a = state.team_name("home"), state.team_name("away")
        parts = [f"{label.capitalize()}: {h} {score['home']}-{score['away']} {a}",
                 f"possession {poss['home']}%-{poss['away']}%",
                 f"shots {self.team_shots['home']}-{self.team_shots['away']}"]
        if self.passes_done:
            pid, n = max(self.passes_done.items(), key=lambda kv: kv[1])
            if pid in state.players:
                parts.append(f"most passes: {state.player_name(pid)} ({n})")
        scorers = [f"{state.player_name(pid)} ({n})" for pid, n in self.goals.items() if pid in state.players]
        if scorers:
            parts.append("scorers: " + ", ".join(scorers))
        if self.fastest_shot:
            parts.append(f"fastest shot {self.fastest_shot:.0f} km/h")
        if self.best_move >= 10:
            parts.append(f"longest passing move {self.best_move} passes")
        return "; ".join(parts) + "."

    def snapshot(self) -> dict[str, Any] | None:
        return {"best_move": self.best_move, "fastest_shot_kmh": round(self.fastest_shot, 1),
                "longest_pass_m": round(self.longest_pass, 1), "facts_fired": len(self.fired)}
