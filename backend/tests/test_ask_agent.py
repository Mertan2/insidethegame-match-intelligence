import asyncio
import json

from app.agents import Persona
from app.agents.ask_agent import AskAgent, LiveContext, run_tool, tool_specs
from app.pipeline import LivePipeline


def _ctx(match, upto=2400):
    p = LivePipeline(match)
    for f in match.frames[:upto]:
        p.process(f)
    st = p.state
    return LiveContext(meta=match.meta, t=st.frame.t, score=dict(st.frame.score), snapshots=p.snapshots(), events=list(st.events))


class ToolCallingLLM:
    """Fake model: asks for one tool, then answers with what it got back."""

    available = True

    def __init__(self):
        self.seen = []

    async def chat(self, messages, tools, max_tokens=400):
        tool_msgs = [m for m in messages if m["role"] == "tool"]
        if not tool_msgs:
            return {"content": None, "tool_calls": [{"id": "c1", "type": "function",
                    "function": {"name": "get_match_state", "arguments": "{}"}}]}
        state = json.loads(tool_msgs[-1]["content"])
        self.seen.append(state)
        return {"content": f"It's {state['score']['home']}-{state['score']['away']} at {state['clock']}."}


class BrokenLLM:
    available = True

    async def chat(self, messages, tools, max_tokens=400):
        raise ConnectionError("down")


def test_tools_return_live_data(match):
    ctx = _ctx(match)
    names = {t["function"]["name"] for t in tool_specs()}
    assert {"get_match_state", "get_player", "get_recent_events", "get_top_players"} <= names
    state = run_tool(ctx, "get_match_state", {})
    assert state["score"] == ctx.score and state["clock"] == ctx.clock()
    player = run_tool(ctx, "get_player", {"name": match.meta.players[9].name})
    assert player["name"] == match.meta.players[9].name and "distance_m" in player
    assert "error" in run_tool(ctx, "get_player", {"name": "Nobody Atall"})
    assert run_tool(ctx, "get_team_stats", {"team": "Riverside"})["team"] == "Riverside Athletic"
    assert len(run_tool(ctx, "get_top_players", {"metric": "distance_m"})["top"]) == 5
    events = run_tool(ctx, "get_recent_events", {"minutes": 60})["events"]
    assert all(e["type"] != "pass" for e in events)


def test_llm_answer_uses_tools(match):
    llm = ToolCallingLLM()
    out = asyncio.run(AskAgent(llm).answer("What's the score?", _ctx(match), Persona()))
    assert out["path"] == "llm"
    assert out["tools"] == [{"tool": "get_match_state", "args": {}}]
    assert out["answer"].startswith("It's ")


def test_falls_back_without_model(match):
    out = asyncio.run(AskAgent(BrokenLLM()).answer("who has the most possession?", _ctx(match), Persona()))
    assert out["path"].startswith("template") and "Possession" in out["answer"]
