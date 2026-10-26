"""Shared blackboard and agent base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from agent_framework import Agent as AFAgent
from pydantic import BaseModel

from ..models import PlayerMeta
from ..plugins import Insight
from .llm import LLMChatClient, LLMClient


class Persona(BaseModel):
    mode: Literal["casual", "analyst"] = "casual"
    language: str = "en"
    favorite_team: Literal["home", "away"] | None = None
    favorite_player: str | None = None
    # The one performance metric this viewer cares about; commentary and the UI keep it in view.
    focus_metric: Literal["distance", "sprints", "top_speed", "passing", "shots", "pressure"] | None = None


METRICS = {
    "distance": ("distance_m", "distance covered", "m"),
    "sprints": ("sprint_m", "sprint distance", "m"),
    "top_speed": ("top_speed_kmh", "top speed", "km/h"),
    "passing": ("passes_completed", "completed passes", ""),
    "shots": ("xg", "expected goals", "xG"),
    "pressure": ("pressures", "pressures applied", ""),
}


def metric_leaders(snapshots: dict, metric: str, n: int = 3) -> list[dict]:
    """Top players for a focus metric from the stats snapshot, as the agents and the UI see them."""
    key, _, _ = METRICS[metric]
    rows = (snapshots.get("stats") or {}).get("players", [])
    rows = [r for r in rows if r.get(key) is not None]
    return [{"player_id": r["player_id"], "name": r["name"], "team": r["team"], "value": r[key]}
            for r in sorted(rows, key=lambda r: r[key], reverse=True)[:n]]


@dataclass
class Blackboard:
    """Shared state the agents read from and write to, in order."""

    t: float
    score: dict[str, int]
    team_names: dict[str, str]
    players: dict[str, PlayerMeta]
    persona: Persona
    insights: list[Insight]
    snapshots: dict[str, Any]
    moment: dict[str, Any] | None = None  # StatsAgent
    why: dict[str, Any] | None = None  # TacticsAgent
    line: str | None = None  # NarratorAgent
    output: dict[str, Any] | None = None  # PersonaAgent
    trace: list[dict[str, Any]] = field(default_factory=list)

    @property
    def clock(self) -> str:
        return f"{int(self.t // 60) + 1}'"

    def name(self, player_id: str | None) -> str:
        return self.players[player_id].name if player_id in self.players else ""


class Agent(ABC):
    """One role in the chain. When a model is configured it is backed by its own Microsoft
    Agent Framework `Agent` (name, description, instructions); otherwise only the template runs."""

    name: ClassVar[str]
    role: ClassVar[str]
    instructions: ClassVar[str] = ""

    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.agent: AFAgent | None = None
        if llm.available and self.instructions:
            self.agent = AFAgent(
                client=LLMChatClient(llm), name=self.name, description=self.role, instructions=self.instructions
            )

    async def ask(self, prompt: str, max_tokens: int, json_mode: bool = False) -> str:
        """One stateless turn on this agent's Agent Framework agent (json_mode: reply must be a JSON object)."""
        if self.agent is None:
            raise RuntimeError("No LLM configured")
        resp = await self.agent.run(prompt, options={"max_tokens": max_tokens, "json_mode": json_mode})
        text = resp.text.strip()
        if not text:
            raise ValueError("Empty agent response")
        return text

    async def run(self, bb: Blackboard) -> str:
        """Returns which path ran: 'llm' or 'template'. Raises on hard failure."""
        if self.llm.available:
            try:
                await self.run_llm(bb)
                return "llm"
            except Exception as exc:  # noqa: BLE001 - any model failure falls back
                bb.trace.append({"agent": self.name, "llm_error": type(exc).__name__})
        self.run_template(bb)
        return "template"

    async def run_llm(self, bb: Blackboard) -> None:
        self.run_template(bb)

    @abstractmethod
    def run_template(self, bb: Blackboard) -> None: ...
