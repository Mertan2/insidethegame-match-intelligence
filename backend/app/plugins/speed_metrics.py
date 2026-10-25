"""Ball speed, shot speed and player name tags triggered by sprint and distance thresholds."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import Event
from .base import Insight, MatchState, Plugin

SPRINT_KMH = 25.0
TAG_COOLDOWN_S = 20.0
TAG_VISIBLE_S = 3.0
MAX_PLAYER_KMH = 45.0
MAX_BALL_KMH = 200.0
DISTANCE_STEP_M = 1000.0  # a distance tag each time a player passes another kilometre
MAX_STEP_M = 12.0  # per-frame movement above this is a restart reposition, not running


class SpeedMetricsPlugin(Plugin):
    name = "speed_metrics"
    description = "Live ball speed, shot speed, and player tags when sprint or distance thresholds are hit"

    def reset(self, state: MatchState) -> None:
        self.max_shot_kmh = 0.0
        self.last_shot: dict[str, Any] | None = None
        self.tags: list[dict[str, Any]] = []
        self._tag_cooldown: dict[str, float] = {}
        self._ball_kmh = 0.0
        self._distance: dict[str, float] = {}
        self._prev: dict[str, tuple[float, float]] = {}
        self._next_km: dict[str, float] = {}

    def on_event(self, event: Event, state: MatchState) -> list[Insight]:
        if event.type != "shot":
            return []
        kmh = float(event.data.get("speed_kmh", 0.0))
        self.last_shot = {"t": event.t, "player": state.player_name(event.player_id), "speed_kmh": kmh}
        if kmh > self.max_shot_kmh:
            self.max_shot_kmh = kmh
            if kmh >= 100:
                return [
                    Insight(
                        t=event.t,
                        kind="rocket_shot",
                        importance=0.5,
                        source=self.name,
                        team=event.team,
                        player_id=event.player_id,
                        headline=f"{self.last_shot['player']} hits it at {kmh:.0f} km/h, fastest of the match",
                        data=self.last_shot,
                    )
                ]
        return []

    def on_frame(self, state: MatchState) -> dict[str, Any] | None:
        frame = state.frame
        assert frame is not None
        track = state.ball_track(2)
        if len(track) == 2:
            kmh = float(np.linalg.norm(track[1] - track[0])) / state.dt * 3.6
            if kmh <= MAX_BALL_KMH:  # larger jumps are the ball being placed for a restart
                self._ball_kmh = kmh

        for pid, x, y in frame.players:
            prev = self._prev.get(pid)
            self._prev[pid] = (x, y)
            if prev is None:
                continue
            step = float(np.hypot(x - prev[0], y - prev[1]))
            if step > MAX_STEP_M:
                continue
            total = self._distance.get(pid, 0.0) + step
            self._distance[pid] = total
            if total >= self._next_km.get(pid, DISTANCE_STEP_M):
                self._next_km[pid] = self._next_km.get(pid, DISTANCE_STEP_M) + DISTANCE_STEP_M
                self.tags.append({"t": frame.t, "player_id": pid, "name": state.player_name(pid), "distance_km": round(total / 1000, 1)})

        hist = list(state.history)
        if len(hist) >= 6:
            then = {pid: (x, y) for pid, x, y in hist[-6].players}
            for pid, x, y in frame.players:
                if pid not in then:
                    continue
                kmh = float(np.hypot(x - then[pid][0], y - then[pid][1])) / (5 * state.dt) * 3.6
                if kmh > MAX_PLAYER_KMH:
                    continue  # repositioned for a restart
                if kmh >= SPRINT_KMH and frame.t - self._tag_cooldown.get(pid, -1e9) > TAG_COOLDOWN_S:
                    self._tag_cooldown[pid] = frame.t
                    self.tags.append(
                        {"t": frame.t, "player_id": pid, "name": state.player_name(pid), "speed_kmh": round(kmh, 1)}
                    )
        self.tags = [tg for tg in self.tags if frame.t - tg["t"] <= TAG_VISIBLE_S]
        if frame.f % 2:
            return None
        return self.snapshot()

    def snapshot(self) -> dict[str, Any] | None:
        return {
            "ball_speed_kmh": round(self._ball_kmh, 1),
            "max_shot_kmh": round(self.max_shot_kmh, 1),
            "last_shot": self.last_shot,
            "tags": self.tags,
        }
