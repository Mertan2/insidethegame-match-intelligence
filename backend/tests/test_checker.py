from app.agents.base import Blackboard, Persona
from app.agents.checker_agent import CheckerAgent, numbers_in
from app.agents.llm import NullLLM


def _bb(text: str) -> Blackboard:
    bb = Blackboard(t=480.0, score={"home": 1, "away": 1}, team_names={"home": "Northbridge FC", "away": "Riverside Athletic"},
                    players={}, persona=Persona(), insights=[], snapshots={})
    bb.moment = {"kind": "goal", "headline": "GOAL Northbridge FC - Hugo Ashdown",
                 "facts": {"xg": 0.56, "team_possession_pct": 41.7, "speed_kmh": 96.6, "distance_m": 2436}}
    bb.output = {"text": text}
    return bb


def check(text: str) -> dict:
    bb = _bb(text)
    CheckerAgent(NullLLM()).run_template(bb)
    return bb.output["check"]


def test_grounded_numbers_pass_in_any_language():
    assert check("Ashdown levels it 1-1 at 8 minutes with 41.7% possession and xG 0.56.")["grounded"]
    assert check("Gol de Ashdown en el minuto 8: xG 0,56 y 41,7% de posesión.")["grounded"]
    assert check("A 96.6 km/h strike, rounded: about 97 km/h, after 2.4 km covered.")["grounded"]
    assert check("هدف في الدقيقة ٨ بنسبة استحواذ ٤١٫٧")["numbers"] >= 1


def test_an_invented_number_is_flagged():
    out = check("Ashdown levels it with 73% possession and an xG of 0.91.")
    assert not out["grounded"]
    assert out["flagged"] == ["73", "0.91"]


def test_number_parsing():
    assert [v for _, v in numbers_in("0,56 and 2,436 m and 1.000.000")] == [0.56, 2436.0, 1000000.0]
