"""Key moments, the explainer (telestrator beats) and the highlights package."""

import asyncio
import json
import re

from app.agents import Persona
from app.agents.explain_agent import ExplainAgent, ProducerAgent, choose_beats, explain, highlights
from app.agents.llm import NullLLM
from app.moments import find_moments, frames_between, pick_highlights


def test_every_shot_becomes_a_moment_with_its_build_up(long_match):
    moments = find_moments(long_match)
    shots = [e for e in long_match.events if e.type == "shot"]
    assert len(moments) == len(shots)
    goals = [m for m in moments if m["kind"] == "goal"]
    assert len(goals) == sum(1 for e in long_match.events if e.type == "goal" and not e.data.get("own_goal"))
    for m in moments:
        assert m["steps"][-1]["type"] == "shot"
        assert m["start"] <= m["clip_start"] <= m["t"] < m["end"]
        assert all(s["t"] <= m["t"] for s in m["steps"])
        passes = [s for s in m["steps"] if s["type"] == "pass"]
        assert len(passes) == m["passes"] and sum(s["key_pass"] for s in passes) == min(1, len(passes))
        shot = m["steps"][-1]
        assert 0 < shot["angle_deg"] <= 180 and shot["distance_m"] > 0


def test_highlights_keep_every_goal_in_match_order(long_match):
    moments = find_moments(long_match)
    reel = pick_highlights(moments)
    assert all(m in reel for m in moments if m["kind"] == "goal")
    assert [m["t"] for m in reel] == sorted(m["t"] for m in reel)
    early = pick_highlights(moments, upto=moments[2]["t"])
    assert all(m["t"] <= moments[2]["t"] for m in early)  # no spoilers in "highlights so far"


def test_replay_frames_cover_the_window(long_match):
    m = find_moments(long_match)[0]
    frames = frames_between(long_match, m["start"], m["end"])
    assert frames[0]["t"] <= m["start"] + 0.1 and frames[-1]["t"] >= m["end"] - 0.1


def test_explain_without_a_model_uses_grounded_templates(long_match):
    goal = next(m for m in find_moments(long_match) if m["kind"] == "goal")
    out = asyncio.run(explain(NullLLM(), long_match.meta, goal, Persona(), "full"))
    assert out["trace"][0]["path"] == "template"
    assert out["beats"][-1]["type"] == "shot" and "scores" in out["beats"][-1]["text"]
    assert out["verdict"].startswith("Why:")
    assert [b["t"] for b in out["beats"]] == sorted(b["t"] for b in out["beats"])


class JsonLLM:
    """Fake model: answers the explainer with one line per requested beat, the producer with intro/outro."""

    available = True

    def __init__(self, drop_beat: bool = False):
        self.drop_beat = drop_beat
        self.calls = 0

    async def complete(self, system, prompt, max_tokens=300, json_mode=False):
        self.calls += 1
        assert json_mode
        if system.startswith(ExplainAgent.instructions[:30]):
            keys = re.search(r"Beats to write: ([\d, ]+)", prompt).group(1).split(", ")
            if self.drop_beat:
                keys = keys[:-1]
            return json.dumps({"headline": "Big moment", "beats": {k: f"line {k}" for k in keys}, "verdict": "Because."})
        assert system.startswith(ProducerAgent.instructions[:30])
        return json.dumps({"intro": "Here we go.", "outro": "That's all."})


def test_explainer_writes_one_line_per_beat(long_match):
    goal = next(m for m in find_moments(long_match) if m["kind"] == "goal")
    out = asyncio.run(explain(JsonLLM(), long_match.meta, goal, Persona(language="es"), "full"))
    assert out["trace"][0]["path"] == "llm"
    assert [b["text"] for b in out["beats"]] == [f"line {i + 1}" for i in range(len(out["beats"]))]
    assert out["headline"] == "Big moment" and out["language"] == "es"


def test_explainer_retries_then_falls_back_when_beats_are_missing(long_match):
    goal = next(m for m in find_moments(long_match) if m["kind"] == "goal")
    llm = JsonLLM(drop_beat=True)
    out = asyncio.run(explain(llm, long_match.meta, goal, Persona(), "full"))
    assert llm.calls == 2  # one retry
    assert out["trace"][-1]["path"] == "template" and all(b["text"] for b in out["beats"])


def test_highlights_fan_out_one_explainer_per_clip_then_the_producer(long_match):
    clips = pick_highlights(find_moments(long_match))
    reel = asyncio.run(highlights(JsonLLM(), long_match.meta, clips, {"home": 1, "away": 1}, 20, True, Persona()))
    assert len(reel["items"]) == len(clips)
    assert [t["agent"] for t in reel["trace"]].count("explainer") == len(clips)
    assert reel["trace"][-1]["agent"] == "producer" and reel["intro"] == "Here we go."
    for item in reel["items"]:
        # Short clips only narrate steps inside the clip.
        assert all(b["t"] >= item["moment"]["clip_start"] or b["type"] == "shot" for b in item["beats"])
        assert choose_beats(item["moment"], "short", item["moment"]["clip_start"])


def test_rate_limit_window():
    from app import ratelimit

    ip = "203.0.113.9"
    assert all(ratelimit.allow(ip, "ask", now=100.0) for _ in range(ratelimit.LIMITS["ask"]))
    assert not ratelimit.allow(ip, "ask", now=100.5)
    assert ratelimit.allow(ip, "ask", now=161.0)  # window has passed
    assert ratelimit.allow("198.51.100.1", "ask", now=100.5)  # other clients unaffected
