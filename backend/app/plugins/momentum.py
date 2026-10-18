"""Explainability signals: momentum, control vs chaos, and game rhythm."""

from __future__ import annotations

from collections import deque
from typing import Any

from ..models import Event
from .base import Insight, MatchState, Plugin

MOMENTUM_WINDOW_S = 300.0
CHAOS_WINDOW_S = 180.0
PUNDIT_EVERY_S = 120.0  # periodic "state of play" moment so live commentary never goes quiet


class MomentumPlugin(Plugin):
    name = "momentum"
    description = "Rolling momentum index, control-vs-chaos index and passing rhythm"

    def reset(self, state: MatchState) -> None:
        self._threat: deque[tuple[float, str, float]] = deque()
        self._changes: deque[float] = deque()
        self._total_changes = 0
        self._passes: deque[tuple[float, str]] = deque()
        self._last_momentum = 0.0
        self._last_regime = "balanced"
        self._last_swing_t = -1e9
        self._last_pundit_t = -1e9
        self._pending: list[Insight] = []
        self.current: dict[str, Any] | None = None

    def on_event(self, event: Event, state: MatchState) -> list[Insight]:
        if event.team is None:
            return []
        d = event.data
        w = 0.0
        if event.type == "pass" and d.get("outcome") == "complete":
            final_third = (event.end_x or 0) > 70 if event.team == "home" else (event.end_x or 105) < 35
            w = 1.0 if final_third else 0.1
            self._passes.append((event.t, event.team))
        elif event.type == "shot":
            w = 3.0 + 10 * float(d.get("xg", 0))
        elif event.type == "goal":
            w = 6.0
        elif event.type == "tackle" and d.get("success"):
            w = 0.5
        elif event.type == "possession_change":
            self._changes.append(event.t)
            self._total_changes += 1
            w = 0.8 if d.get("cause") == "interception" else 0.3
        if w:
            self._threat.append((event.t, event.team, w))
        return []

    def on_frame(self, state: MatchState) -> dict[str, Any] | None:
        frame = state.frame
        assert frame is not None
        t = frame.t
        for dq, window in ((self._threat, MOMENTUM_WINDOW_S), (self._changes, CHAOS_WINDOW_S), (self._passes, 60.0)):
            while dq and t - (dq[0] if isinstance(dq[0], float) else dq[0][0]) > window:
                dq.popleft()
        if frame.f % state.meta.fps != 0:
            return None

        home = sum(w for _, side, w in self._threat if side == "home")
        away = sum(w for _, side, w in self._threat if side == "away")
        momentum = (home - away) / (home + away) if home + away > 0 else 0.0
        minutes = min(CHAOS_WINDOW_S, max(t, 1.0)) / 60.0
        changes_per_min = len(self._changes) / minutes
        match_rate = self._total_changes / max(t / 60.0, 1.0)
        # Relative to this match's own rhythm: 0.5 = typical, 1.0 = twice as frantic as usual.
        chaos = min(1.0, changes_per_min / max(match_rate, 1e-6) / 2) if t > CHAOS_WINDOW_S else 0.5
        regime = "chaos" if chaos > 0.65 else "control" if chaos < 0.35 else "balanced"
        passes_per_min = {s: sum(1 for _, side in self._passes if side == s) for s in ("home", "away")}

        self.current = {
            "momentum": round(momentum, 3),  # +1 home dominant, -1 away dominant
            "chaos_index": round(chaos, 3),
            "regime": regime,
            "possession_changes_per_min": round(changes_per_min, 2),
            "passes_last_min": passes_per_min,
        }
        if abs(momentum - self._last_momentum) > 0.5 and t - self._last_swing_t > 120 and t > 120:
            side = "home" if momentum > self._last_momentum else "away"
            self._pending.append(
                Insight(
                    t=t,
                    kind="momentum_swing",
                    importance=0.6,
                    source=self.name,
                    team=side,
                    headline=f"Momentum swinging towards {state.team_name(side)}",
                    data={"from": round(self._last_momentum, 2), "to": round(momentum, 2)},
                )
            )
            self._last_swing_t = t
            self._last_momentum = momentum
        elif t - self._last_swing_t > 120:
            self._last_momentum = momentum
        if regime != self._last_regime and t > 90 and regime != "balanced":
            self._pending.append(
                Insight(
                    t=t,
                    kind=f"regime_{regime}",
                    importance=0.5,
                    source=self.name,
                    headline="The game is opening up, possession is changing hands constantly"
                    if regime == "chaos"
                    else "One side has taken control of the ball",
                    data=dict(self.current),
                )
            )
        self._last_regime = regime
        if t - self._last_pundit_t >= PUNDIT_EVERY_S and t >= 60:
            self._last_pundit_t = t
            leader = "home" if momentum > 0.15 else "away" if momentum < -0.15 else None
            self._pending.append(
                Insight(
                    t=t,
                    kind="state_of_play",
                    importance=0.56,
                    source=self.name,
                    team=leader,
                    headline=(f"{state.team_name(leader)} on top" if leader else "Evenly balanced") + f", game is {regime}",
                    data={"momentum": round(momentum, 2), "regime": regime,
                          "possession_changes_per_min": self.current["possession_changes_per_min"],
                          "passes_last_min_home": passes_per_min["home"], "passes_last_min_away": passes_per_min["away"]},
                )
            )
        return self.current

    def drain_insights(self) -> list[Insight]:
        pending, self._pending = self._pending, []
        return pending

    def snapshot(self) -> dict[str, Any] | None:
        return self.current
