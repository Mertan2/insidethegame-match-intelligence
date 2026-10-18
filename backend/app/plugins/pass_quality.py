"""Pass distance, accuracy and a 0-100 difficulty rating."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from ..models import Event
from .base import Insight, MatchState, Plugin


def pass_difficulty(
    distance: float, pressure_m: float, receiver_space_m: float, progress_m: float, aerial: bool, weak_foot: bool = False
) -> float:
    """Heuristic difficulty, 0 (trivial) .. 100 (exceptional). Swap for a learned model later."""
    score = (
        0.9 * min(distance, 50)
        + 18 * math.exp(-pressure_m / 2.0)
        + 14 * math.exp(-receiver_space_m / 3.0)
        + 0.35 * max(progress_m, 0)
        + (8 if aerial else 0)
        + (7 if weak_foot else 0)
    )
    return float(np.clip(score, 0, 100))


class PassQualityPlugin(Plugin):
    name = "pass_quality"
    description = "Pass distance, accuracy and difficulty rating; flags line-breaking passes"

    def reset(self, state: MatchState) -> None:
        self.recent: list[dict[str, Any]] = []
        self.by_team = {s: {"count": 0, "completed": 0, "difficulty_sum": 0.0, "progressive": 0} for s in ("home", "away")}
        self._dirty = False

    def on_event(self, event: Event, state: MatchState) -> list[Insight]:
        if event.type != "pass" or event.team is None:
            return []
        d = event.data
        receiver_id = d.get("intended_receiver_id")
        receiver_xy = state.player_xy(receiver_id) if receiver_id else None
        space = 10.0
        if receiver_xy is not None and state.frame is not None:
            opp = [np.array([x, y]) for pid, x, y in state.frame.players if state.players[pid].team != event.team]
            space = min(float(np.linalg.norm(o - receiver_xy)) for o in opp)
        direction = 1 if event.team == "home" else -1
        progress = ((event.end_x or event.x or 0) - (event.x or 0)) * direction
        difficulty = pass_difficulty(
            float(d.get("distance", 0)), float(d.get("pressure_distance", 10)), space, progress, d.get("kind") == "aerial",
            bool(d.get("weak_foot")),
        )
        completed = d.get("outcome") == "complete"
        rec = {
            "t": event.t,
            "passer_id": event.player_id,
            "passer": state.player_name(event.player_id),
            "team": event.team,
            "receiver": state.player_name(d.get("receiver_id")) if d.get("receiver_id") else None,
            "distance_m": d.get("distance"),
            "speed_kmh": d.get("speed_kmh"),
            "kind": d.get("kind"),
            "progress_m": round(progress, 1),
            "difficulty": round(difficulty),
            "body_part": d.get("body_part"),
            "weak_foot": bool(d.get("weak_foot")),
            "outcome": d.get("outcome"),
        }
        self.recent = (self.recent + [rec])[-8:]
        team = self.by_team[event.team]
        team["count"] += 1
        team["completed"] += completed
        team["difficulty_sum"] += difficulty
        team["progressive"] += progress >= 15 and completed
        self._dirty = True
        if completed and difficulty >= 70:
            return [
                Insight(
                    t=event.t,
                    kind="difficult_pass",
                    importance=0.45 + (difficulty - 70) / 100,
                    source=self.name,
                    team=event.team,
                    player_id=event.player_id,
                    headline=f"{rec['passer']} completes a difficulty-{rec['difficulty']} pass",
                    data=rec,
                )
            ]
        return []

    def on_frame(self, state: MatchState) -> dict[str, Any] | None:
        if not self._dirty:
            return None
        self._dirty = False
        return self.snapshot()

    def snapshot(self) -> dict[str, Any] | None:
        teams = {
            s: {
                "accuracy_pct": round(100 * t["completed"] / t["count"], 1) if t["count"] else 0.0,
                "avg_difficulty": round(t["difficulty_sum"] / t["count"], 1) if t["count"] else 0.0,
                "progressive_passes": t["progressive"],
            }
            for s, t in self.by_team.items()
        }
        return {"recent": self.recent, "teams": teams}
