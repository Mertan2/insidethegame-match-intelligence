"""The match analyst as an A2A (Agent2Agent) agent.

A broadcaster's own agent, a studio tool or another team's assistant can discover this agent from
its card (`/.well-known/agent-card.json`) and send it messages over A2A JSON-RPC (`/a2a`):

- ask anything about the match ("who is tiring?", "why are Riverside on top?"),
- "explain the 8th-minute goal": the explainer agent's breakdown of that moment,
- "highlights": the producer's package (intro, one line per clip, outro).

It is a Microsoft Agent Framework `Agent` whose chat client routes each request to the agents that
already serve the app (ask, explainer, producer), and Agent Framework's `A2AExecutor` puts it on the
official A2A SDK server. Answers come from the same grounded data as the UI.
"""

from __future__ import annotations

import os
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from agent_framework import Agent, BaseChatClient, ChatResponse, Message
from agent_framework.a2a import A2AExecutor
from starlette.routing import BaseRoute

from . import ratelimit

Handler = Callable[[str], Awaitable[str]]

MINUTE = re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)?\s*(?:'|’|min(?:ute)?s?\b|-minute)", re.I)


def route(text: str) -> str:
    """Which skill a request is for."""
    t = text.lower()
    if "highlight" in t or "recap" in t or "package" in t:
        return "highlights"
    if ("explain" in t or "break down" in t or "breakdown" in t) and MINUTE.search(text):
        return "explain"
    return "ask"


def minute_of(text: str) -> int | None:
    m = MINUTE.search(text)
    return int(m.group(1)) if m else None


class MatchAnalystClient(BaseChatClient):
    """Agent Framework chat client that answers with the app's own agents instead of a single model call."""

    OTEL_PROVIDER_NAME = "insidethegame.match_analyst"

    def __init__(self, handlers: Mapping[str, Handler], **kwargs: Any):
        super().__init__(**kwargs)
        self.handlers = handlers

    async def _inner_get_response(
        self, *, messages: Sequence[Message], stream: bool, options: Mapping[str, Any], **kwargs: Any
    ) -> ChatResponse:
        text = next((m.text for m in reversed(messages) if m.role == "user" and m.text), "")
        if not ratelimit.allow("a2a", "a2a"):
            reply = "Too many requests right now; try again in a minute."
        elif not text.strip():
            reply = "Ask me about the match, ask me to explain a moment (\"explain the 8th-minute goal\"), or ask for the highlights."
        else:
            reply = await self.handlers[route(text)](text)
        return ChatResponse(messages=[Message(role="assistant", contents=[reply])])


def agent_card(url: str) -> AgentCard:
    return AgentCard(
        name="Inside the Game match analyst",
        description=(
            "Explainable football match intelligence from synthetic tracking and event data: answers questions "
            "with live-data tools, explains any shot or goal step by step, and cuts a narrated highlights package."
        ),
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[AgentInterface(url=url, protocol_binding="JSONRPC")],
        skills=[
            AgentSkill(id="ask", name="Ask about the match",
                       description="Answers any question about the match from live-data tools (score, players, teams, events, forecast).",
                       tags=["football", "stats", "q&a"], examples=["Who has been the best player?", "Who is tiring?"]),
            AgentSkill(id="explain", name="Explain a moment",
                       description="Breaks down a goal or chance: how the ball was won, the key pass, the space at the shot, and why it worked.",
                       tags=["football", "explainability"], examples=["Explain the 8th-minute goal"]),
            AgentSkill(id="highlights", name="Highlights package",
                       description="The producer's highlights: intro, one line per clip (goals first, then the best chances), outro.",
                       tags=["football", "recap", "highlights"], examples=["Give me the highlights"]),
        ],
    )


def build_routes(handlers: Mapping[str, Handler], path: str = "/a2a") -> list[BaseRoute]:
    """Agent card + JSON-RPC routes, ready to add to the FastAPI app."""
    url = os.getenv("A2A_URL") or f"{os.getenv('PUBLIC_URL', 'http://localhost:8000').rstrip('/')}{path}"
    card = agent_card(url)
    agent = Agent(client=MatchAnalystClient(handlers), name="match-analyst", description=card.description,
                  instructions="Answer football match questions from the Inside the Game data.")
    handler = DefaultRequestHandler(agent_executor=A2AExecutor(agent), task_store=InMemoryTaskStore(), agent_card=card)
    return [*create_agent_card_routes(card), *create_jsonrpc_routes(handler, path)]
