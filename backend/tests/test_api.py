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
