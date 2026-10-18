"""Runs enabled plugins over the replayed stream: ingest -> interpret -> insights."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import Event, Frame, Match
from .plugins import PLUGIN_CLASSES, Insight, MatchState, Plugin


@dataclass
class TickResult:
    frame: Frame
    events: list[Event]
    payloads: dict[str, Any] = field(default_factory=dict)
    insights: list[Insight] = field(default_factory=list)


class LivePipeline:
    def __init__(self, match: Match, enabled: list[str] | None = None):
        self.match = match
        self.events_by_frame: dict[int, list[Event]] = {}
        for ev in match.events:
            self.events_by_frame.setdefault(ev.frame, []).append(ev)
        self.plugins: dict[str, Plugin] = {name: cls() for name, cls in PLUGIN_CLASSES.items()}
        if enabled is None:
            enabled = [n for n, c in PLUGIN_CLASSES.items() if c.default_enabled]
        self.enabled: list[str] = [n for n in enabled if n in self.plugins]
        self.reset()

    def reset(self) -> None:
        self.state = MatchState(meta=self.match.meta)
        for p in self.plugins.values():
            p.reset(self.state)

    def process(self, frame: Frame, events: list[Event] | None = None) -> TickResult:
        events = self.events_by_frame.get(frame.f, []) if events is None else events
        self.state.push(frame, events)
        result = TickResult(frame=frame, events=events)
        for name in self.enabled:
            plugin = self.plugins[name]
            for ev in events:
                result.insights.extend(plugin.on_event(ev, self.state))
            payload = plugin.on_frame(self.state)
            if payload is not None:
                result.payloads[name] = payload
            result.insights.extend(plugin.drain_insights())
        for name in self.enabled:
            payload = self.plugins[name].on_insights(result.insights, self.state)
            if payload is not None:
                result.payloads[name] = payload
        return result

    def set_enabled(self, names: list[str]) -> None:
        """Toggle plugins at runtime. Newly enabled plugins catch up on the match so far."""
        names = [n for n in names if n in self.plugins]
        added = [n for n in names if n not in self.enabled]
        self.enabled = names
        if added and self.state.frame is not None:
            self._catch_up(added, self.state.frame.f)

    def _catch_up(self, names: list[str], upto: int) -> None:
        shadow = MatchState(meta=self.match.meta)
        for n in names:
            self.plugins[n].reset(shadow)
        for frame in self.match.frames[: upto + 1]:
            events = self.events_by_frame.get(frame.f, [])
            shadow.push(frame, events)
            for n in names:
                plugin = self.plugins[n]
                for ev in events:
                    plugin.on_event(ev, shadow)
                plugin.on_frame(shadow)
                plugin.drain_insights()

    def seek(self, frame_idx: int) -> None:
        """Rebuild all plugin state up to frame_idx (silently)."""
        self.reset()
        for frame in self.match.frames[:frame_idx]:
            self.process(frame)

    def snapshots(self) -> dict[str, Any]:
        return {n: self.plugins[n].snapshot() for n in self.enabled}
