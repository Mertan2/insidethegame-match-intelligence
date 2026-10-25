"""Key moments of a match, reconstructed from the event feed and tracking.

A moment is a shot (goal, save or miss) plus the possession that led to it: how the ball was
won, every pass in the build-up, and what the tracking says at the instant of the shot
(pressure on the shooter, defenders between ball and goal, the keeper's position). These are
the facts the explain and highlights agents talk about, and the timeline the replay theatre
draws as annotations, so every caption points at something visible on the pitch.
"""

from __future__ import annotations

import math
from typing import Any

from .models import Event, Frame, Match

BUILDUP_MAX_S = 25.0  # look back at most this far for the start of the move
PRE_ROLL_S = 2.0
CLIP_S = 12.0  # highlights show at most this much before the shot  # replay starts a little before the move
POST_ROLL_S = {"goal": 4.0, "saved": 3.0, "off_target": 2.5}
GOAL_Y = (34.0 - 3.66, 34.0 + 3.66)


def attack_x(team: str) -> float:
    """The goal line a team attacks (teams don't swap ends in the synthetic data)."""
    return 105.0 if team == "home" else 0.0


def _frame_at(match: Match, t: float) -> Frame:
    f = min(max(int(round(t * match.meta.fps)), 0), len(match.frames) - 1)
    return match.frames[f]


def _progress(team: str, x0: float, x1: float) -> float:
    """Metres gained towards the opponents' goal."""
    return (x1 - x0) if team == "home" else (x0 - x1)


def _opponents_bypassed(frame: Frame, team: str, x0: float, x1: float, players: dict[str, Any]) -> int:
    """Outfield opponents the ball went past (between the pass's start and end, along the attack)."""
    lo, hi = sorted((x0, x1))
    return sum(
        1
        for pid, x, _ in frame.players
        if players[pid].team != team and players[pid].role != "GK" and lo < x < hi
    )


def _shot_context(match: Match, shot: Event) -> dict[str, Any]:
    """What the tracking shows at the moment of the shot."""
    players = {p.id: p for p in match.meta.players}
    frame = _frame_at(match, shot.t)
    gx = attack_x(shot.team or "home")
    sx, sy = shot.x, shot.y
    nearest, nearest_id = math.inf, None
    blockers = []
    keeper = None
    for pid, x, y in frame.players:
        p = players[pid]
        if p.team == shot.team:
            continue
        d = math.hypot(x - sx, y - sy)
        if p.role == "GK":
            keeper = {"player_id": pid, "x": x, "y": y, "off_line_m": round(abs(x - gx), 1)}
            continue
        if d < nearest:
            nearest, nearest_id = d, pid
        # In the triangle between the ball and the two posts?
        if _in_triangle((x, y), (sx, sy), (gx, GOAL_Y[0]), (gx, GOAL_Y[1])):
            blockers.append(pid)
    placement = None
    if shot.end_y is not None:
        off = shot.end_y - 34.0
        side = "centre" if abs(off) < 1.2 else ("left" if (off < 0) == (shot.team == "home") else "right")
        placement = side
    return {
        "distance_m": round(math.hypot(gx - sx, 34.0 - sy), 1),
        "angle_deg": round(_goal_angle(sx, sy, gx), 1),
        "nearest_defender_id": nearest_id,
        "nearest_defender_m": round(nearest, 1) if nearest_id else None,
        "defenders_in_the_way": len(blockers),
        "blocker_ids": blockers,
        "keeper": keeper,
        "placement": placement,
    }


def _goal_angle(x: float, y: float, gx: float) -> float:
    a = math.atan2(GOAL_Y[0] - y, gx - x)
    b = math.atan2(GOAL_Y[1] - y, gx - x)
    d = abs(math.degrees(b - a)) % 360
    return min(d, 360 - d)


def _in_triangle(p, a, b, c) -> bool:
    def sign(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])

    d1, d2, d3 = sign(p, a, b), sign(p, b, c), sign(p, c, a)
    neg = d1 < 0 or d2 < 0 or d3 < 0
    pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (neg and pos)


def _buildup(match: Match, idx: int, shot: Event) -> tuple[dict[str, Any] | None, list[Event]]:
    """Walk back from the shot to the start of the possession. Returns the regain (if any) and the passes."""
    passes: list[Event] = []
    regain = None
    for e in reversed(match.events[:idx]):
        if shot.t - e.t > BUILDUP_MAX_S:
            break
        if e.type in ("pressure", "tackle") and e.team != shot.team:
            continue  # the opponents trying, not having the ball
        if e.type == "pass" and e.team == shot.team and e.data.get("outcome") == "complete":
            passes.append(e)
            continue
        if e.type == "possession_change" and e.team == shot.team:
            regain = {
                "t": e.t, "x": e.x, "y": e.y, "player_id": e.player_id,
                "cause": e.data.get("cause"),
            }
            break
        if e.type in ("kickoff", "goal_kick") and e.team == shot.team:
            regain = {"t": e.t, "x": e.x, "y": e.y, "player_id": e.player_id, "cause": e.type}
            break
        if e.team not in (None, shot.team) and e.type in ("pass", "shot", "possession_change"):
            break
    passes.reverse()
    return regain, passes


def find_moments(match: Match) -> list[dict[str, Any]]:
    """Every shot as a moment, with its build-up, shot context and a replay window."""
    players = {p.id: p for p in match.meta.players}
    moments: list[dict[str, Any]] = []
    for idx, shot in enumerate(match.events):
        if shot.type != "shot" or not shot.team:
            continue
        outcome = shot.data.get("outcome", "off_target")
        regain, passes = _buildup(match, idx, shot)
        steps: list[dict[str, Any]] = []
        if regain:
            steps.append({"type": "regain", **regain})
        for i, p in enumerate(passes):
            frame = _frame_at(match, p.t)
            end_x = p.end_x if p.end_x is not None else p.x
            end_y = p.end_y if p.end_y is not None else p.y
            steps.append({
                "type": "pass", "t": p.t, "player_id": p.player_id, "receiver_id": p.data.get("receiver_id"),
                "x": p.x, "y": p.y, "end_x": end_x, "end_y": end_y,
                "length_m": round(math.hypot(end_x - p.x, end_y - p.y), 1),
                "progress_m": round(_progress(shot.team, p.x, end_x), 1),
                "bypassed": _opponents_bypassed(frame, shot.team, p.x, end_x, players)
                if _progress(shot.team, p.x, end_x) > 0 else 0,
                "kind": p.data.get("kind"), "body_part": p.data.get("body_part"),
                "key_pass": i == len(passes) - 1,
            })
        ctx = _shot_context(match, shot)
        steps.append({
            "type": "shot", "t": shot.t, "player_id": shot.player_id, "x": shot.x, "y": shot.y,
            "end_x": shot.end_x if shot.end_x is not None else attack_x(shot.team),
            "end_y": shot.end_y if shot.end_y is not None else 34.0,
            "xg": shot.data.get("xg"), "speed_kmh": shot.data.get("speed_kmh"),
            "body_part": shot.data.get("body_part"), "weak_foot": shot.data.get("weak_foot"),
            "outcome": outcome, **ctx,
        })
        start = (regain["t"] if regain else (passes[0].t if passes else shot.t)) - PRE_ROLL_S
        start = max(start, shot.t - BUILDUP_MAX_S - PRE_ROLL_S, 0.0)
        end = min(shot.t + POST_ROLL_S.get(outcome, 3.0), len(match.frames) / match.meta.fps - 0.1)
        score_after = dict(_frame_at(match, shot.t + 1.5).score)
        moments.append({
            "id": f"m{shot.id}",
            "t": shot.t,
            "minute": int(shot.t // 60) + 1,
            "kind": "goal" if outcome == "goal" else ("save" if outcome == "saved" else "miss"),
            "team": shot.team,
            "player_id": shot.player_id,
            "xg": shot.data.get("xg") or 0.0,
            "score_after": score_after,
            "start": round(start, 1),
            "clip_start": round(max(start, shot.t - CLIP_S), 1),  # shorter cut for the highlights reel
            "end": round(end, 1),
            "passes": len(passes),
            "steps": steps,
        })
    return moments


def rank(moment: dict[str, Any]) -> float:
    """How much a moment belongs in the highlights: goals first, then the clearest chances."""
    shot = moment["steps"][-1]
    base = {"goal": 10.0, "save": 2.0, "miss": 1.0}[moment["kind"]]
    return base + 5 * moment["xg"] + 0.2 * moment["passes"] + (0.5 if (shot.get("speed_kmh") or 0) > 100 else 0.0)


def pick_highlights(moments: list[dict[str, Any]], upto: float | None = None, limit: int = 6) -> list[dict[str, Any]]:
    """All goals plus the best other chances, in match order."""
    pool = [m for m in moments if upto is None or m["t"] <= upto]
    goals = [m for m in pool if m["kind"] == "goal"]
    others = sorted((m for m in pool if m["kind"] != "goal"), key=rank, reverse=True)
    chosen = goals + others[: max(0, limit - len(goals))]
    return sorted(chosen[: max(limit, len(goals))], key=lambda m: m["t"])


def frames_between(match: Match, start: float, end: float, step: int = 1) -> list[dict[str, Any]]:
    """Compact tracking for a replay window."""
    fps = match.meta.fps
    lo = max(0, int(start * fps))
    hi = min(len(match.frames), int(end * fps) + 1)
    return [
        {"t": f.t, "ball": f.ball, "players": f.players, "owner": f.owner, "score": f.score}
        for f in match.frames[lo:hi:step]
    ]
