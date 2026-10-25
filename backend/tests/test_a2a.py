"""The match analyst over A2A: routing, the agent card, and an Agent Framework agent answering through it."""

import asyncio

from agent_framework import Agent
from fastapi.testclient import TestClient

from app.a2a_server import MatchAnalystClient, minute_of, route


def test_requests_route_to_the_right_skill():
    assert route("Explain the 8th-minute goal") == "explain"
    assert route("break down the 14' chance") == "explain"
    assert route("Give me the highlights") == "highlights"
    assert route("Who is tiring?") == "ask"
    assert route("explain why they are dominating") == "ask"  # no minute: a question, not a moment
    assert minute_of("explain the 8th-minute goal") == 8 and minute_of("the 14' chance") == 14


def test_agent_framework_agent_answers_through_the_skills():
    async def handler(name):
        async def h(text):
            return f"{name}: {text}"
        return h

    async def run():
        handlers = {n: await handler(n) for n in ("ask", "explain", "highlights")}
        agent = Agent(client=MatchAnalystClient(handlers), name="match-analyst", instructions="x")
        return (await agent.run("Explain the 3rd-minute goal")).text

    assert asyncio.run(run()) == "explain: Explain the 3rd-minute goal"


def test_agent_card_is_published():
    from app.main import app

    with TestClient(app) as c:
        card = c.get("/.well-known/agent-card.json").json()
    assert card["name"] == "Inside the Game match analyst"
    assert {s["id"] for s in card["skills"]} == {"ask", "explain", "highlights"}
    assert card["supportedInterfaces"][0]["url"].endswith("/a2a")
