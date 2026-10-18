"""Data contracts for matches, events and tracking frames."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

TeamSide = Literal["home", "away"]

EventType = Literal[
    "kickoff",
    "pass",
    "shot",
    "goal",
    "tackle",
    "pressure",
    "possession_change",
    "throw_in",
    "goal_kick",
    "corner",
    "half_time",
    "full_time",
]


class PlayerMeta(BaseModel):
    id: str
    name: str
    number: int
    team: TeamSide
    role: Literal["GK", "DEF", "MID", "FWD"]
    preferred_foot: Literal["left", "right"] = "right"


class TeamMeta(BaseModel):
    side: TeamSide
    name: str
    short: str
    color: str


class MatchMeta(BaseModel):
    match_id: str
    seed: int
    minutes: int
    fps: int
    pitch: tuple[float, float] = (105.0, 68.0)
    teams: dict[str, TeamMeta]
    players: list[PlayerMeta]
    final_score: dict[str, int] = Field(default_factory=lambda: {"home": 0, "away": 0})


class Event(BaseModel):
    """A discrete match event. Synthetic data uses the same shape a real feed would map into."""

    id: int
    t: float  # seconds since kickoff
    frame: int
    type: EventType
    team: TeamSide | None = None
    player_id: str | None = None
    x: float | None = None
    y: float | None = None
    end_x: float | None = None
    end_y: float | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class Frame(BaseModel):
    """Tracking snapshot. Compact field names keep the WebSocket payload small."""

    f: int  # frame index
    t: float
    ball: tuple[float, float, float]
    players: list[tuple[str, float, float]]  # (player_id, x, y)
    # Limb tracking: (player_id, left_x, left_y, left_z, right_x, right_y, right_z) foot positions in metres.
    feet: list[tuple[str, float, float, float, float, float, float]] | None = None
    owner: str | None = None  # player in control of the ball
    score: dict[str, int]


class Match(BaseModel):
    meta: MatchMeta
    frames: list[Frame]
    events: list[Event]
