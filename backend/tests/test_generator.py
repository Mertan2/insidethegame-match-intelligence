from collections import Counter

from app.generator import generate_match


def test_frames_cover_match_and_stay_on_pitch(match):
    assert len(match.frames) == 6 * 60 * match.meta.fps
    for f in match.frames[::50]:
        x, y, z = f.ball
        assert -1 <= x <= 106 and -1 <= y <= 69 and z >= 0
        assert len(f.players) == 22


def test_event_mix_is_football_like(match):
    counts = Counter(e.type for e in match.events)
    assert counts["pass"] > 50
    assert counts["kickoff"] >= 2  # start + second half
    completed = sum(1 for e in match.events if e.type == "pass" and e.data["outcome"] == "complete")
    assert 0.6 < completed / counts["pass"] < 0.95
    assert all(e.data.get("outcome") for e in match.events if e.type in ("pass", "shot"))


def test_score_matches_goal_events(match):
    goals = Counter(e.team for e in match.events if e.type == "goal")
    assert match.meta.final_score == {"home": goals.get("home", 0), "away": goals.get("away", 0)}


def test_feet_track_players_and_alternate(match):
    pos = {pid: (x, y) for pid, x, y in match.frames[500].players}
    for pid, lx, ly, lz, rx, ry, rz in match.frames[500].feet:
        px, py = pos[pid]
        assert ((lx - px) ** 2 + (ly - py) ** 2) ** 0.5 < 1.5  # kicking foot can reach the ball
        assert ((rx - px) ** 2 + (ry - py) ** 2) ** 0.5 < 1.5
        assert 0 <= lz <= 0.3 and 0 <= rz <= 0.3
    # A running player's feet lift alternately rather than together.
    lifts = [(f[3] > 0.05, f[6] > 0.05) for fr in match.frames[100:400] for f in fr.feet if f[0] == "h9"]
    assert any(left and not right for left, right in lifts) and any(right and not left for left, right in lifts)


def test_kicks_record_foot_and_weak_foot_is_minority(match):
    kicks = [e for e in match.events if e.type in ("pass", "shot")]
    assert all(e.data["body_part"] in ("left_foot", "right_foot", "head") for e in kicks)
    footed = [e for e in kicks if e.data["body_part"] != "head"]
    weak = sum(e.data["weak_foot"] for e in footed) / len(footed)
    assert 0.08 < weak < 0.35
    lefties = sum(p.preferred_foot == "left" for p in match.meta.players)
    assert 0 < lefties < 22


def test_headers_are_a_realistic_minority(long_match):
    m = long_match
    kicks = [e for e in m.events if e.type in ("pass", "shot")]
    headers = [e for e in kicks if e.data["body_part"] == "head"]
    assert 0.03 < len(headers) / len(kicks) < 0.25
    assert any(e.type == "shot" for e in headers), "crosses should produce headed attempts"
    assert all(not e.data["weak_foot"] for e in headers)
    assert any(e.data.get("kind") == "cross" for e in kicks)


def test_deterministic_for_seed():
    a = generate_match(seed=5, minutes=2)
    b = generate_match(seed=5, minutes=2)
    assert a.frames[-1].ball == b.frames[-1].ball
    assert len(a.events) == len(b.events)
