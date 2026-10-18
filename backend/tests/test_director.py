from app.commentary import CommentaryScheduler
from app.pipeline import LivePipeline
from app.plugins import Insight


def _run(match):
    pipeline = LivePipeline(match)
    insights = []
    for frame in match.frames:
        insights.extend(pipeline.process(frame).insights)
    return pipeline, insights


def test_director_covers_the_whole_match(long_match):
    _, insights = _run(long_match)
    kinds = [i.kind for i in insights if i.source == "director"]
    # play-by-play roughly every 6 game seconds while the ball is in play
    assert kinds.count("play_by_play") > 120
    assert kinds.count("recap") >= 4  # every 4 minutes
    assert {"half_time_recap", "full_time_recap"} <= set(kinds)
    facts = [i for i in insights if i.kind == "fun_fact"]
    assert len(facts) >= 5
    assert len({i.data["fun_fact"] for i in facts}) == len(facts)  # never repeats itself


def test_briefs_are_grounded_in_the_data(long_match):
    _, insights = _run(long_match)
    pbp = next(i for i in insights if i.kind == "play_by_play")
    assert "has the ball" in pbp.data["on_screen"] and pbp.player_id
    name = next(p.name for p in long_match.meta.players if p.id == pbp.player_id)
    assert pbp.data["on_screen"].startswith(name)
    ft = next(i for i in insights if i.kind == "full_time_recap")
    h, a = long_match.meta.final_score["home"], long_match.meta.final_score["away"]
    assert f"{h}-{a}" in ft.data["recap"]


def _ins(kind, importance, t):
    return Insight(t=t, kind=kind, importance=importance, source="test", headline=kind)


def test_scheduler_paces_lines_and_puts_key_moments_first():
    now = [0.0]
    s = CommentaryScheduler(line_gap_s=5.0, clock=lambda: now[0])
    first = s.offer([_ins("play_by_play", 0.57, 10.0)], 10.0)
    assert first is not None and first.kind == "play_by_play"
    s.last_line = now[0]
    assert s.offer([_ins("fun_fact", 0.64, 11.0)], 11.0) is None  # too soon for routine chatter
    goal = s.offer([_ins("goal", 1.0, 12.0)], 12.0)  # key moments don't wait
    assert goal is not None and goal.kind == "goal"
    s.last_line = now[0]
    now[0] = 6.0
    nxt = s.offer([_ins("play_by_play", 0.57, 14.0)], 14.0)
    assert nxt is not None and nxt.kind == "fun_fact"  # fun fact outranks play-by-play
    s.last_line = now[0]
    now[0] = 30.0
    assert s.offer([], 40.0) is None  # stale play-by-play is dropped
