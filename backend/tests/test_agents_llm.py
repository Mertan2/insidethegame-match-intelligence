"""LLM-path tests with mocked models: Agent Framework workflow, fallback, translation, Foundry client."""

import asyncio
import json

import httpx
import pytest
from agent_framework import Agent as AFAgent

from app.agents import Orchestrator, Persona, orchestrator as orch_mod
from app.agents.llm import FoundryLLM, LLMChatClient
from app.agents.narrator_agent import SYSTEM as NARRATOR_SYSTEM
from app.agents.persona_agent import SYSTEM as PERSONA_SYSTEM
from app.agents.recap_agent import SYSTEM as RECAP_SYSTEM
from app.agents.tactics_agent import SYSTEM as TACTICS_SYSTEM
from app.plugins import Insight

REPLIES = {
    TACTICS_SYSTEM: "They have been pressing hard.",
    NARRATOR_SYSTEM: "What a chance!",
    PERSONA_SYSTEM: "¡Qué ocasión!",
    RECAP_SYSTEM: "Informe del partido.\nSegundo párrafo.",
}


class FakeLLM:
    """Stands in for Foundry: answers by system prompt and records every call."""

    available = True

    def __init__(self, delay: float = 0.0):
        self.calls: list[dict] = []
        self.delay = delay

    async def complete(self, system, prompt, max_tokens=300):
        self.calls.append({"system": system, "prompt": prompt, "max_tokens": max_tokens})
        if self.delay:
            await asyncio.sleep(self.delay)
        return REPLIES[system]


def _insight(match, **kw):
    base = dict(t=600.0, kind="big_chance", importance=0.75, source="stats", team="home",
                player_id=match.meta.players[9].id, headline="Big chance",
                data={"xg": 0.42, "outcome": "saved", "distance": 9.5})
    return Insight(**{**base, **kw})


def _narrate(orch, match, persona):
    return asyncio.run(orch.narrate(600.0, {"home": 0, "away": 0}, [_insight(match)], {}, persona))


def test_each_llm_agent_is_an_agent_framework_agent(match):
    orch = Orchestrator(match.meta, llm=FakeLLM())
    stats, *llm_agents, checker = orch.chain
    assert checker.agent is None  # the fact-checker is deterministic too
    assert stats.agent is None  # stays deterministic so numbers are grounded
    for a in [*llm_agents, orch.recap_agent]:
        assert isinstance(a.agent, AFAgent) and a.agent.name == a.name


def test_llm_path_in_trace_and_translation(match):
    llm = FakeLLM()
    out = _narrate(Orchestrator(match.meta, llm=llm), match, Persona(mode="analyst", language="es"))
    assert out is not None
    trace = {s["agent"]: s for s in out["trace"]}
    assert list(trace) == ["stats", "tactics", "narrator", "persona", "checker"]
    assert trace["stats"]["path"] == "deterministic"
    assert all(trace[a]["path"] == "llm" and trace[a]["status"] == "ok" for a in ("tactics", "narrator", "persona"))
    assert out["text"] == "¡Qué ocasión!"
    assert out["language"] == "es" and out["requested_language"] == "es"
    # Persona sees the narrator's and tactics agent's output via the shared blackboard.
    persona_call = next(c for c in llm.calls if c["system"] == PERSONA_SYSTEM)
    sent = json.loads(persona_call["prompt"])
    assert sent["language"] == "es" and "What a chance!" in sent["text"] and "pressing hard" in sent["text"]
    assert all(f["agent"] != "persona" or "llm_error" not in f for f in out["trace"])


def test_agents_are_stateless_between_narrations(match):
    llm = FakeLLM()
    orch = Orchestrator(match.meta, llm=llm)
    _narrate(orch, match, Persona(language="tr"))
    first = [c["prompt"] for c in llm.calls]
    llm.calls.clear()
    _narrate(orch, match, Persona(language="tr"))
    # No conversation history leaks into the next moment's prompts.
    assert [c["prompt"] for c in llm.calls] == first


def test_timeout_falls_back_to_template(match, monkeypatch):
    monkeypatch.setattr(orch_mod, "AGENT_TIMEOUT_S", 0.05)
    out = _narrate(Orchestrator(match.meta, llm=FakeLLM(delay=0.5)), match, Persona(language="tr"))
    assert out is not None and match.meta.players[9].name in out["text"]
    steps = [s for s in out["trace"] if "path" in s and s["agent"] not in ("stats", "checker")]
    assert all(s["path"] == "template" and s["status"] == "fallback:TimeoutError" for s in steps)
    assert out["language"] == "en" and out["requested_language"] == "tr"  # honest about missing translation


def test_recap_llm_path(match):
    orch = Orchestrator(match.meta, llm=FakeLLM())
    out = asyncio.run(orch.recap([_insight(match, kind="goal")], {}, {"home": 1, "away": 0}, Persona(language="es")))
    assert out["path"] == "llm"
    assert out["paragraphs"] == ["Informe del partido.", "Segundo párrafo."]
    assert out["language"] == "es"


def test_chat_client_passes_instructions_and_max_tokens():
    llm = FakeLLM()
    agent = AFAgent(client=LLMChatClient(llm), name="narrator", instructions=NARRATOR_SYSTEM)
    resp = asyncio.run(agent.run("moment json", options={"max_tokens": 80}))
    assert resp.text == "What a chance!"
    assert llm.calls == [{"system": NARRATOR_SYSTEM, "prompt": "moment json", "max_tokens": 80}]


def _foundry(handler) -> FoundryLLM:
    llm = FoundryLLM("https://res.openai.azure.com/", "test-key", "gpt-4o-mini")
    llm._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return llm


def _completion(text):
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": text}}]})


def test_foundry_request_shape():
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        return _completion("  Hola  ")

    assert asyncio.run(_foundry(handler).complete("sys", "hi", max_tokens=50)) == "Hola"
    req = seen[0]
    assert str(req.url) == "https://res.openai.azure.com/openai/deployments/gpt-4o-mini/chat/completions?api-version=2024-10-21"
    assert req.headers["api-key"] == "test-key"
    body = json.loads(req.content)
    assert body["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    assert body["max_tokens"] == 50


def test_foundry_switches_to_reasoning_params():
    bodies = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        bodies.append(body)
        if "max_tokens" in body:
            return httpx.Response(400, json={"error": {"message": "Unsupported parameter: 'max_tokens' is not supported with this model."}})
        return _completion("ok")

    llm = _foundry(handler)
    assert asyncio.run(llm.complete("sys", "hi", max_tokens=50)) == "ok"
    assert bodies[-1]["max_completion_tokens"] == 400 and "temperature" not in bodies[-1]
    asyncio.run(llm.complete("sys", "again", max_tokens=50))
    assert len(bodies) == 3  # remembered: no second failed attempt


def test_foundry_errors_raise():
    llm = _foundry(lambda req: httpx.Response(401, json={"error": "bad key"}))
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(llm.complete("sys", "hi"))
