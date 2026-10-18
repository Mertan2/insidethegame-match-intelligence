"""3D ball trajectory forecasting from tracking alone.

Estimates the ball's current velocity from the last few frames, integrates the
physics model forward, and reports the predicted path, landing spot, apex and
goal-line crossing. Spin is not observable, so the generator's Magnus curl is a
real source of forecast error; accuracy is measured against what actually happens.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .. import physics
from ..models import Event
from .base import Insight, MatchState, Plugin

MIN_SPEED = 4.0  # m/s, below this the ball is effectively at someone's feet
HORIZON_S = 1.0  # accuracy is scored on the position predicted this far ahead


def estimate_velocity(track: np.ndarray, dt: float) -> np.ndarray:
    """Velocity at the latest sample, correcting the backward difference for gravity."""
    v = (track[-1] - track[-2]) / dt
    if track[-1][2] > 0.02 or track[-2][2] > 0.02:
        v[2] -= physics.G * dt / 2
    return v


class BallForecastPlugin(Plugin):
    name = "ball_forecast"
    description = "Physics-based 3D ball trajectory, landing point and goal-line forecast"

    def reset(self, state: MatchState) -> None:
        self.current: dict[str, Any] = {"active": False}
        self._pending: list[tuple[int, np.ndarray]] = []  # (target frame, predicted xyz)
        self._errors: list[float] = []
        self._was_active = False
        self._last_shot_event: Event | None = None
        self._flagged_shot_id: int | None = None
        self._insights: list[Insight] = []

    def on_event(self, event: Event, state: MatchState) -> list[Insight]:
        if event.type == "shot":
            self._last_shot_event = event
        if event.type in ("pass", "shot"):
            self._pending.clear()  # a touch (e.g. a header) changes the flight; old forecasts can't be scored
        return []

    def drain_insights(self) -> list[Insight]:
        out, self._insights = self._insights, []
        return out

    def _flag_shot(self, crossing: dict[str, Any], t: float, state: MatchState) -> None:
        """First on-target forecast for the current shot: 'called it before it arrived'."""
        shot = self._last_shot_event
        if shot is None or t - shot.t > 2.0 or self._flagged_shot_id == shot.id or not crossing["on_target"]:
            return
        if crossing["in_s"] < 0.1:
            return  # already at the line: that's not a forecast
        self._flagged_shot_id = shot.id
        self._insights.append(
            Insight(
                t=t,
                kind="forecast_on_target",
                importance=0.55,
                source=self.name,
                team=shot.team,
                player_id=shot.player_id,
                headline=f"Forecast: {state.player_name(shot.player_id)}'s shot is on target, "
                f"arriving in {crossing['in_s']:.1f}s",
                data={"lead_s": crossing["in_s"], "y": crossing["y"], "z": crossing["z"], "speed_kmh": shot.data.get("speed_kmh")},
            )
        )

    def on_frame(self, state: MatchState) -> dict[str, Any] | None:
        frame = state.frame
        assert frame is not None
        track = state.ball_track(3)
        self._score(frame.f, frame.owner is None, track[-1] if len(track) else None)
        if frame.owner is not None or len(track) < 3:
            return self._deactivate()
        vel = estimate_velocity(track, state.dt)
        if float(np.linalg.norm(vel)) < MIN_SPEED:
            return self._deactivate()

        pos = track[-1].copy()
        points = physics.simulate(pos, vel, duration=3.0, dt=0.02, sample_every=0.1)
        landing = physics.first_landing(pos, vel)
        apex = max(p[2] for _, p in points)
        out: dict[str, Any] = {
            "active": True,
            "t": frame.t,
            "speed_kmh": round(float(np.linalg.norm(vel)) * 3.6, 1),
            "trajectory": [[round(float(c), 2) for c in p] for _, p in points],
            "apex_m": round(float(apex), 2),
            "landing": None,
            "goal_crossing": None,
            "accuracy": self._accuracy(),
        }
        if landing is not None:
            lt, lp = landing
            out["landing"] = {"x": round(float(lp[0]), 2), "y": round(float(lp[1]), 2), "in_s": round(lt, 2)}
        horizon = int(round(HORIZON_S * state.meta.fps))
        if len(points) > horizon:
            self._pending.append((frame.f + horizon, points[horizon][1].copy()))

        goal_x = physics.PITCH_LENGTH if vel[0] > 0 else 0.0
        crossing = physics.goal_line_crossing(points, goal_x)
        if crossing is not None:
            ct, cy, cz = crossing
            on_target = physics.GOAL_Y_MIN < cy < physics.GOAL_Y_MAX and 0 <= cz < physics.GOAL_HEIGHT
            out["goal_crossing"] = {
                "goal": "home" if goal_x == 0.0 else "away",
                "y": round(float(cy), 2),
                "z": round(float(cz), 2),
                "in_s": round(float(ct), 2),
                "on_target": bool(on_target),
            }
            self._flag_shot(out["goal_crossing"], frame.t, state)
        self.current = out
        self._was_active = True
        return out

    def _deactivate(self) -> dict[str, Any] | None:
        if not self._was_active:
            return None
        self._was_active = False
        self.current = {"active": False, "accuracy": self._accuracy()}
        return self.current

    def _score(self, f: int, free: bool, ball: np.ndarray | None) -> None:
        """Compare forecasts made HORIZON_S ago with where the ball actually is now.

        Forecasts whose flight was interrupted (a player took control) are discarded,
        since physics can't predict a touch.
        """
        if not free:
            self._pending.clear()
            return
        due = [p for p in self._pending if p[0] <= f]
        self._pending = [p for p in self._pending if p[0] > f]
        if ball is None:
            return
        for target_f, predicted in due:
            if target_f == f:
                self._errors = (self._errors + [float(np.linalg.norm(ball - predicted))])[-500:]

    def _accuracy(self) -> dict[str, Any]:
        if not self._errors:
            return {"horizon_s": HORIZON_S, "samples": 0, "mean_error_m": None}
        return {"horizon_s": HORIZON_S, "samples": len(self._errors), "mean_error_m": round(float(np.mean(self._errors)), 2)}

    def snapshot(self) -> dict[str, Any] | None:
        return self.current
