import pytest
from fastapi.testclient import TestClient

from app import main
from app.store import MatchStore


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "MatchStore", lambda: MatchStore(tmp_path))
    monkeypatch.setattr(main, "DEFAULT_MINUTES", 2)
    with TestClient(main.app) as c:
        yield c


def test_rest_endpoints(client):
    matches = client.get("/api/matches").json()
    assert len(matches) == 1
    mid = matches[0]["match_id"]
    assert client.get(f"/api/matches/{mid}").json()["minutes"] == 2
    assert {p["name"] for p in client.get("/api/plugins").json()} >= {"stats", "ball_forecast"}
    recap = client.get(f"/api/matches/{mid}/recap").json()
    assert recap["title"].startswith("Northbridge FC")
    cues = client.get(f"/api/matches/{mid}/overlays").json()
    assert cues["match_id"] == mid and isinstance(cues["cues"], list)


def test_live_websocket_streams_and_toggles_plugins(client):
    mid = client.get("/api/matches").json()[0]["match_id"]
    with client.websocket_connect(f"/ws/live/{mid}?speed=32&plugins=stats") as ws:
        meta = ws.receive_json()
        assert meta["type"] == "meta" and meta["enabled"] == ["stats"]
        ws.send_json({"type": "plugins", "enabled": ["stats", "speed_metrics"]})
        seen_plugins = set()
        acked = False
        for _ in range(200):
            msg = ws.receive_json()
            if msg["type"] == "plugins_ack":
                acked = True
            if msg["type"] == "tick":
                seen_plugins |= set(msg["plugins"])
                assert len(msg["frame"]["players"]) == 22
        assert acked
        assert "speed_metrics" in seen_plugins


def test_tts_reports_unconfigured_and_builds_ssml(client, monkeypatch):
    from app.speech import Speech

    monkeypatch.setattr(main, "speech", None)
    assert client.post("/api/tts", json={"text": "Goal!"}).status_code == 503
    ssml = Speech.ssml("Gol & <kurtarış>", "tr", excited=True)
    assert "tr-TR-AhmetNeural" in ssml and "&amp; &lt;kurtarış&gt;" in ssml and "+6%" in ssml
    assert "rate='+0%'" in Speech.ssml("Quiet spell.", "tr", excited=False)  # routine lines at natural speed
    hd = Speech.ssml("GOAL!", "en", excited=True)  # HD voice: pace and tone come from the text, no prosody
    assert "DragonHD" in hd and "prosody" not in hd


def test_explain_depth_short_has_fewer_beats(client):
    match_id = client.get("/api/matches").json()[0]["match_id"]
    moment = client.get(f"/api/matches/{match_id}/moments").json()[0]
    full = client.get(f"/api/matches/{match_id}/moments/{moment['id']}/explain").json()
    short = client.get(f"/api/matches/{match_id}/moments/{moment['id']}/explain?depth=short").json()
    quick = client.get(f"/api/matches/{match_id}/moments/{moment['id']}/explain?depth=quick").json()
    assert 0 < len(short["beats"]) <= len(quick["beats"]) <= len(full["beats"])
    assert short["verdict"] == "" and quick["verdict"]
    assert client.get(f"/api/matches/{match_id}/moments/{moment['id']}/explain?depth=huge").status_code == 422


def test_every_fans_call_narrates_one_moment_for_three_viewers(client):
    match_id = client.get("/api/matches").json()[0]["match_id"]
    goals = [m for m in client.get(f"/api/matches/{match_id}/moments").json() if m["kind"] == "goal"]
    if not goals:
        return
    goal = goals[0]
    out = client.get(f"/api/matches/{match_id}/moments/{goal['id']}/viewers").json()
    assert len(out["viewers"]) == 3
    scorer, rival, analyst = out["viewers"]
    assert scorer["persona"]["favorite_team"] == goal["team"]
    assert rival["persona"]["favorite_team"] != goal["team"] and rival["persona"]["language"] == "tr"
    assert analyst["persona"]["mode"] == "analyst"
    assert all([s["agent"] for s in v["trace"] if "path" in s] == ["stats", "tactics", "narrator", "persona", "checker"] for v in out["viewers"])
    assert rival["text"].startswith("Not what you wanted to see.")
