"""Core match statistics: possession, passing, shooting, xG, per-player physical load."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from ..models import Event
from .base import Insight, MatchState, Plugin


def _team_template() -> dict[str, float]:
    return {
        "possession_frames": 0,
        "passes": 0,
        "passes_completed": 0,
        "aerial_passes": 0,
        "shots": 0,
        "shots_on_target": 0,
        "goals": 0,
        "xg": 0.0,
        "tackles": 0,
        "tackles_won": 0,
        "interceptions": 0,
        "pressures": 0,
    }


MAX_HUMAN_SPEED_MS = 12.5  # ~45 km/h; faster frame-to-frame moves are teleports at restarts


class StatsPlugin(Plugin):
    name = "stats"
    description = "Possession, passing, shots, xG and per-player distance/top speed"

    def reset(self, state: MatchState) -> None:
        self.teams = {"home": _team_template(), "away": _team_template()}
        self.players: dict[str, dict[str, float]] = defaultdict(
            lambda: {
                "distance_m": 0.0, "top_speed_kmh": 0.0, "passes": 0, "passes_completed": 0, "shots": 0, "xg": 0.0,
                "left_foot": 0, "right_foot": 0, "weak_foot": 0, "weak_foot_completed": 0,
            }
        )
        self._prev_pos: dict[str, np.ndarray] = {}
        self._speed_window: dict[str, list[np.ndarray]] = defaultdict(list)
        self._last: dict[str, Any] | None = None
        self._state: MatchState | None = state

    def on_event(self, event: Event, state: MatchState) -> list[Insight]:
        team = self.teams.get(event.team or "")
        if team is None:
            return []
        player = self.players[event.player_id] if event.player_id else None
        d = event.data
        out: list[Insight] = []
        if player is not None and event.type in ("pass", "shot") and d.get("body_part") in ("left_foot", "right_foot"):
            player[d["body_part"]] += 1
            if d.get("weak_foot"):
                player["weak_foot"] += 1
                player["weak_foot_completed"] += d.get("outcome") in ("complete", "goal", "saved")
        if event.type == "pass":
            team["passes"] += 1
            team["aerial_passes"] += d.get("kind") == "aerial"
            if player is not None:
                player["passes"] += 1
            if d.get("outcome") == "complete":
                team["passes_completed"] += 1
                if player is not None:
                    player["passes_completed"] += 1
        elif event.type == "shot":
            xg = float(d.get("xg", 0.0))
            team["shots"] += 1
            team["xg"] += xg
            team["shots_on_target"] += d.get("outcome") in ("goal", "saved")
            if player is not None:
                player["shots"] += 1
                player["xg"] += xg
            if d.get("outcome") != "goal":
                big = xg >= 0.3
                out.append(
                    Insight(
                        t=event.t,
                        kind="big_chance" if big else "shot",
                        importance=min(0.85, 0.4 + xg),
                        source=self.name,
                        team=event.team,
                        player_id=event.player_id,
                        headline=f"{state.player_name(event.player_id)} shoots ({d.get('outcome')}, xG {xg:.2f})",
                        data={"xg": xg, "outcome": d.get("outcome"), "distance": d.get("distance"),
                              "speed_kmh": d.get("speed_kmh")},
                    )
                )
        elif event.type == "goal":
            team["goals"] += 1
            out.append(
                Insight(
                    t=event.t,
                    kind="goal",
                    importance=1.0,
                    source=self.name,
                    team=event.team,
                    player_id=event.player_id,
                    headline=f"GOAL {state.team_name(event.team)}"
                    + (f" - {state.player_name(event.player_id)}" if event.player_id else " (own goal)"),
                    data={"score": d.get("score"), "own_goal": d.get("own_goal", False)},
                )
            )
        elif event.type == "tackle":
            team["tackles"] += 1
            team["tackles_won"] += bool(d.get("success"))
        elif event.type == "pressure":
            team["pressures"] += 1
        elif event.type == "possession_change" and d.get("cause") == "interception":
            team["interceptions"] += 1
        return out

    def on_frame(self, state: MatchState) -> dict[str, Any] | None:
        frame = state.frame
        assert frame is not None
        if frame.owner:
            self.teams[state.players[frame.owner].team]["possession_frames"] += 1
        max_step = MAX_HUMAN_SPEED_MS * state.dt
        for pid, x, y in frame.players:
            pos = np.array([x, y])
            prev = self._prev_pos.get(pid)
            self._prev_pos[pid] = pos
            window = self._speed_window[pid]
            if prev is not None:
                step = float(np.linalg.norm(pos - prev))
                if step > max_step:  # repositioned for a restart, not running
                    window.clear()
                    window.append(pos)
                    continue
                self.players[pid]["distance_m"] += step
            window.append(pos)
            if len(window) > 6:
                window.pop(0)
                speed = float(np.linalg.norm(window[-1] - window[0])) / (5 * state.dt) * 3.6
                if speed > self.players[pid]["top_speed_kmh"]:
                    self.players[pid]["top_speed_kmh"] = speed
        if frame.f % state.meta.fps != 0:
            return None
        self._last = self._build(state)
        return self._last

    def _build(self, state: MatchState) -> dict[str, Any]:
        total_poss = sum(t["possession_frames"] for t in self.teams.values()) or 1
        teams = {}
        for side, t in self.teams.items():
            teams[side] = {
                **{k: (round(v, 2) if isinstance(v, float) else v) for k, v in t.items() if k != "possession_frames"},
                "possession_pct": round(100 * t["possession_frames"] / total_poss, 1),
                "pass_accuracy_pct": round(100 * t["passes_completed"] / t["passes"], 1) if t["passes"] else 0.0,
            }
        players = [
            {
                "player_id": pid,
                "name": state.player_name(pid),
                "team": state.players[pid].team,
                "distance_m": round(p["distance_m"]),
                "top_speed_kmh": round(p["top_speed_kmh"], 1),
                "passes": p["passes"],
                "passes_completed": p["passes_completed"],
                "shots": p["shots"],
                "xg": round(p["xg"], 2),
                "preferred_foot": state.players[pid].preferred_foot,
                "left_foot": p["left_foot"],
                "right_foot": p["right_foot"],
                "weak_foot_pct": round(100 * p["weak_foot"] / (p["left_foot"] + p["right_foot"]), 1)
                if p["left_foot"] + p["right_foot"]
                else 0.0,
                "weak_foot_success_pct": round(100 * p["weak_foot_completed"] / p["weak_foot"], 1) if p["weak_foot"] else None,
            }
            for pid, p in self.players.items()
            if pid in state.players
        ]
        return {"teams": teams, "players": players}

    def snapshot(self) -> dict[str, Any] | None:
        # Payloads go out once a second; snapshots must include events since the last one.
        return self._build(self._state) if self._state is not None else self._last
