"""Plugin contract. Every analytics module implements this and is toggled at runtime."""

from __future__ import annotations

from abc import ABC
from collections import deque
from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np
from pydantic import BaseModel, Field

from ..models import Event, Frame, MatchMeta, PlayerMeta


class Insight(BaseModel):
    """A machine-readable signal that something worth talking about happened.

    Plugins emit insights; the agent layer decides which ones become narration.
    """

    t: float
    kind: str
    importance: float  # 0..1
    source: str
    headline: str
    team: str | None = None
    player_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


@dataclass
class MatchState:
    meta: MatchMeta
    frame: Frame | None = None
    history: deque[Frame] = field(default_factory=lambda: deque(maxlen=60))
    events: list[Event] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.players: dict[str, PlayerMeta] = {p.id: p for p in self.meta.players}

    @property
    def dt(self) -> float:
        return 1.0 / self.meta.fps

    def push(self, frame: Frame, events: list[Event]) -> None:
        self.frame = frame
        self.history.append(frame)
        self.events.extend(events)

    def ball_track(self, n: int) -> np.ndarray:
        """Last n ball positions, oldest first, shape (k, 3)."""
        frames = list(self.history)[-n:]
        return np.array([f.ball for f in frames], dtype=float)

    def player_xy(self, player_id: str, frame: Frame | None = None) -> np.ndarray | None:
        frame = frame or self.frame
        if frame is None:
            return None
        for pid, x, y in frame.players:
            if pid == player_id:
                return np.array([x, y])
        return None

    def player_name(self, player_id: str | None) -> str:
        if player_id is None or player_id not in self.players:
            return "Unknown"
        return self.players[player_id].name

    def team_name(self, side: str | None) -> str:
        if side is None:
            return ""
        return self.meta.teams[side].name


class Plugin(ABC):
    """Base class for analytics modules.

    - `on_event` reacts to discrete events and may return insights.
    - `on_frame` runs every tracking frame and may return a UI payload
      (sent to clients under `plugins[name]`); return None to send nothing.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    default_enabled: ClassVar[bool] = True

    def reset(self, state: MatchState) -> None:  # noqa: B027 - optional hook
        pass

    def on_event(self, event: Event, state: MatchState) -> list[Insight]:
        return []

    def on_frame(self, state: MatchState) -> dict[str, Any] | None:
        return None

    def drain_insights(self) -> list[Insight]:
        """Insights detected during on_frame (trend-based rather than event-based)."""
        return []

    def on_insights(self, insights: list[Insight], state: MatchState) -> dict[str, Any] | None:
        """Second phase: sees every plugin's insights for this tick. A returned payload
        replaces this plugin's on_frame payload. For consumers such as broadcast overlays."""
        return None

    def snapshot(self) -> dict[str, Any] | None:
        """Latest full state for agents and late-joining clients."""
        return None
