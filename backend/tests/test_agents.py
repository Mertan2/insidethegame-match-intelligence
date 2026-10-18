import asyncio

from app.agents import Orchestrator, Persona
from app.plugins import Insight


class BrokenLLM:
    available = True

    async def complete(self, system, prompt, max_tokens=300):
        raise ConnectionError("model down")


def _insight(match, **kw):
    base = dict(t=600.0, kind="big_chance", importance=0.75, source="stats", team="home",
                player_id=match.meta.players[9].id, headline="Big chance",
                data={"xg": 0.42, "outcome": "saved", "distance": 9.5})
    return Insight(**{**base, **kw})


def test_narration_template_path(match):
    orch = Orchestrator(match.meta)
    out = asyncio.run(orch.narrate(600.0, {"home": 0, "away": 0}, [_insight(match)], {}, Persona(mode="analyst")))
    assert out is not None
    assert match.meta.players[9].name in out["text"]
    assert any("xG 0.42" in f for f in out["why"])
    assert [s["agent"] for s in out["trace"]] == ["stats", "tactics", "narrator", "persona"]


def test_low_importance_is_skipped_for_casual(match):
    orch = Orchestrator(match.meta)
    weak = _insight(match, importance=0.3)
    assert asyncio.run(orch.narrate(600.0, {"home": 0, "away": 0}, [weak], {}, Persona())) is None


def test_favorite_player_boosts_selection(match):
    orch = Orchestrator(match.meta)
    fav = match.meta.players[9].id
    weak = _insight(match, importance=0.4)
    out = asyncio.run(orch.narrate(600.0, {"home": 0, "away": 0}, [weak], {}, Persona(favorite_player=fav)))
    assert out is not None and out["text"].startswith("Your player!")


def test_llm_failure_falls_back_to_templates(match):
    orch = Orchestrator(match.meta, llm=BrokenLLM())
    out = asyncio.run(orch.narrate(600.0, {"home": 0, "away": 0}, [_insight(match)], {}, Persona()))
    assert out is not None and out["text"]
    assert any("llm_error" in s for s in out["trace"])


def test_goal_facts_state_score_and_effect(match):
    from app.agents.stats_agent import goal_effect

    assert goal_effect({"home": 1, "away": 1}, "home") == "equaliser"
    assert goal_effect({"home": 1, "away": 0}, "home") == "opening goal, takes the lead"
    assert goal_effect({"home": 1, "away": 3}, "home") == "pulls one back, still behind"
    orch = Orchestrator(match.meta)
    goal = _insight(match, kind="goal", importance=1.0, data={"score": {"home": 1, "away": 1}})
    out = asyncio.run(orch.narrate(435.0, {"home": 1, "away": 1}, [goal], {}, Persona(mode="analyst")))
    facts = " ".join(out["facts"])
    assert "equaliser" in facts and "1-1" in facts
