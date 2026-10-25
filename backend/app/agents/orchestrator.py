"""Orchestrates the agents as a Microsoft Agent Framework workflow over shared state.

stats -> tactics -> narrator -> persona. Each agent is its own Agent Framework executor in a
sequential `Workflow`; they coordinate through the blackboard kept in workflow shared state
(each step reads it, writes its own slot, and hands off a signal to the next executor). Each
step has a timeout; on timeout or error the agent's deterministic template runs instead, and
the trace records what happened, so one failing model call never silences the live feed.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from agent_framework import Executor, Workflow, WorkflowBuilder, WorkflowContext, handler

from .. import telemetry
from ..models import MatchMeta
from ..plugins import Insight
from .ask_agent import AskAgent
from .base import Agent, Blackboard, Persona
from .llm import LLMClient, NullLLM
from .narrator_agent import NarratorAgent
from .persona_agent import PersonaAgent
from .recap_agent import RecapAgent
from .stats_agent import StatsAgent
from .tactics_agent import TacticsAgent

AGENT_TIMEOUT_S = 4.0
MIN_GAP_S = 8.0  # game seconds between narrations unless the moment is huge
BLACKBOARD = "blackboard"  # workflow shared-state key


async def run_step(agent: Agent, bb: Blackboard, timeout: float | None = None) -> None:
    """Run one agent with a timeout and template fallback, appending its trace entry (and a tracing span)."""
    started = time.perf_counter()
    with telemetry.span(f"agent.{agent.name}", **{"agent.name": agent.name, "moment.kind": (bb.moment or {}).get("kind")}) as sp:
        try:
            path = await asyncio.wait_for(agent.run(bb), timeout=timeout or AGENT_TIMEOUT_S)
            status = "ok"
        except Exception as exc:  # noqa: BLE001 - includes TimeoutError
            status = f"fallback:{type(exc).__name__}"
            path = "template"
            try:
                agent.run_template(bb)
            except Exception as exc2:  # noqa: BLE001
                status = f"failed:{type(exc2).__name__}"
        ms = round((time.perf_counter() - started) * 1000, 1)
        sp.set_attribute("agent.path", path)
        sp.set_attribute("agent.status", status)
        sp.set_attribute("agent.ms", ms)
    bb.trace.append({"agent": agent.name, "path": path, "status": status, "ms": ms})


class AgentStep(Executor):
    """Workflow executor hosting one agent. The first step receives the blackboard and puts it in
    shared state; later steps receive the previous agent's name as a hand-off signal."""

    def __init__(self, agent: Agent, last: bool):
        super().__init__(id=agent.name)
        self.agent = agent
        self.last = last

    @handler
    async def step(self, message: Blackboard | str, ctx: WorkflowContext[str, Blackboard | None]) -> None:
        bb = message if isinstance(message, Blackboard) else ctx.get_state(BLACKBOARD)
        await run_step(self.agent, bb)
        ctx.set_state(BLACKBOARD, bb)
        if self.agent.name == "stats" and bb.moment is None:
            await ctx.yield_output(None)  # nothing worth saying; the chain stops here
        elif self.last:
            await ctx.yield_output(bb)
        else:
            await ctx.send_message(self.agent.name)


def build_workflow(chain: list[Agent]) -> Workflow:
    steps = [AgentStep(a, last=i == len(chain) - 1) for i, a in enumerate(chain)]
    builder = WorkflowBuilder(name="live-narration", start_executor=steps[0], output_from=steps)
    return builder.add_chain(steps).build()


class Orchestrator:
    def __init__(self, meta: MatchMeta, llm: LLMClient | None = None):
        self.meta = meta
        self.llm = llm or NullLLM()
        self.chain: list[Agent] = [StatsAgent(self.llm), TacticsAgent(self.llm), NarratorAgent(self.llm), PersonaAgent(self.llm)]
        self.recap_agent = RecapAgent(self.llm)
        self.players = {p.id: p for p in meta.players}
        self.team_names = {s: t.name for s, t in meta.teams.items()}
        self._last_t = -1e9
        self.history: list[dict[str, Any]] = []

    AGENT_CLASSES = (StatsAgent, TacticsAgent, NarratorAgent, PersonaAgent, RecapAgent, AskAgent)

    @classmethod
    def describe_agents(cls) -> list[dict[str, str]]:
        return [{"name": a.name, "role": a.role} for a in cls.AGENT_CLASSES]

    def describe(self) -> list[dict[str, str]]:
        return self.describe_agents()

    def should_run(self, insights: list[Insight], t: float) -> bool:
        if not insights:
            return False
        if max(i.importance for i in insights) >= 0.8:
            return True
        return t - self._last_t >= MIN_GAP_S

    async def narrate(
        self, t: float, score: dict[str, int], insights: list[Insight], snapshots: dict[str, Any], persona: Persona
    ) -> dict[str, Any] | None:
        bb = Blackboard(
            t=t,
            score=score,
            team_names=self.team_names,
            players=self.players,
            persona=persona,
            insights=insights,
            snapshots=snapshots,
        )
        # A workflow instance runs one request at a time; narrations can overlap, so build one per run.
        with telemetry.span("narration", **{"insight.kind": insights[0].kind if insights else None,
                                            "persona.mode": persona.mode, "persona.language": persona.language}):
            result = await build_workflow(self.chain).run(bb)
        outputs = result.get_outputs()
        final: Blackboard | None = outputs[-1] if outputs else None
        if final is None or final.output is None:
            return None
        self._last_t = t
        out = {**final.output, "trace": final.trace}
        self.history.append(out)
        return out

    async def recap(self, insights: list[Insight], snapshots: dict[str, Any], score: dict[str, int], persona: Persona) -> dict[str, Any]:
        bb = Blackboard(
            t=self.meta.minutes * 60.0,
            score=score,
            team_names=self.team_names,
            players=self.players,
            persona=persona,
            insights=insights,
            snapshots=snapshots,
        )
        await run_step(self.recap_agent, bb, timeout=AGENT_TIMEOUT_S * 3)
        return {**(bb.output or {}), "path": bb.trace[-1]["path"], "trace": bb.trace}
