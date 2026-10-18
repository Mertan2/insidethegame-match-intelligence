"""Broadcast overlay cues: timed, machine-readable graphics instructions.

Turns insights into cues a broadcast graphics engine could render on a live feed
(lower thirds, score bugs, stat flashes). Each cue has an in/out time, a screen
slot, a template name and the data to fill it, with no rendered text, so the
rendering partner controls styling and language.
"""

from __future__ import annotations

from typing import Any

from .base import Insight, MatchState, Plugin

# insight kind -> (slot, template, duration seconds, priority)
CUE_RULES: dict[str, tuple[str, str, float, int]] = {
    "goal": ("lower_third", "goal", 8.0, 100),
    "big_chance": ("lower_third", "big_chance", 5.0, 70),
    "forecast_on_target": ("top_bug", "forecast_on_target", 3.0, 80),
    "rocket_shot": ("top_bug", "shot_speed", 4.0, 60),
    "shot": ("top_bug", "shot", 3.0, 40),
    "difficult_pass": ("top_bug", "pass_rating", 4.0, 50),
    "momentum_swing": ("side_panel", "momentum", 6.0, 55),
    "regime_chaos": ("side_panel", "regime", 5.0, 45),
    "regime_control": ("side_panel", "regime", 5.0, 45),
}


class OverlaysPlugin(Plugin):
    name = "overlays"
    description = "Timed broadcast graphics cues (lower thirds, bugs) from key moments"

    def reset(self, state: MatchState) -> None:
        self.timeline: list[dict[str, Any]] = []
        self._active_ids: tuple[int, ...] = ()

    def on_insights(self, insights: list[Insight], state: MatchState) -> dict[str, Any] | None:
        frame = state.frame
        assert frame is not None
        for ins in insights:
            rule = CUE_RULES.get(ins.kind)
            if rule is None:
                continue
            slot, template, duration, priority = rule
            self.timeline.append(
                {
                    "id": len(self.timeline),
                    "t_in": round(ins.t, 2),
                    "t_out": round(ins.t + duration, 2),
                    "slot": slot,
                    "template": template,
                    "priority": priority,
                    "team": ins.team,
                    "team_name": state.team_name(ins.team),
                    "player_id": ins.player_id,
                    "player": state.player_name(ins.player_id) if ins.player_id else None,
                    "score": dict(frame.score),
                    "data": ins.data,
                }
            )
        active = self.active(frame.t)
        ids = tuple(c["id"] for c in active)
        if ids == self._active_ids:
            return None
        self._active_ids = ids
        return {"active": active}

    def active(self, t: float) -> list[dict[str, Any]]:
        """Highest-priority live cue per slot."""
        by_slot: dict[str, dict[str, Any]] = {}
        for cue in self.timeline[-30:]:
            if cue["t_in"] <= t < cue["t_out"]:
                cur = by_slot.get(cue["slot"])
                if cur is None or cue["priority"] > cur["priority"] or (
                    cue["priority"] == cur["priority"] and cue["t_in"] > cur["t_in"]
                ):
                    by_slot[cue["slot"]] = cue
        return list(by_slot.values())

    def snapshot(self) -> dict[str, Any] | None:
        return {"timeline": self.timeline}
