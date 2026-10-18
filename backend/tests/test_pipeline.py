from app.pipeline import LivePipeline
from app.plugins import PLUGIN_CLASSES


def run(pipeline, match, upto=None):
    insights, payloads = [], {}
    for frame in match.frames[:upto]:
        r = pipeline.process(frame)
        insights.extend(r.insights)
        payloads.update(r.payloads)
    return insights, payloads


def test_all_plugins_produce_payloads(match):
    _, payloads = run(LivePipeline(match), match)
    assert set(payloads) == set(PLUGIN_CLASSES)
    teams = payloads["stats"]["teams"]
    assert abs(teams["home"]["possession_pct"] + teams["away"]["possession_pct"] - 100) < 0.5


def test_stats_agree_with_events(match):
    pipeline = LivePipeline(match)
    run(pipeline, match)
    stats = pipeline.plugins["stats"].snapshot()["teams"]
    passes = sum(1 for e in match.events if e.type == "pass")
    assert stats["home"]["passes"] + stats["away"]["passes"] == passes


def test_forecast_accuracy_is_measured(match):
    pipeline = LivePipeline(match)
    run(pipeline, match)
    acc = pipeline.plugins["ball_forecast"].snapshot()["accuracy"]
    assert acc["samples"] > 0
    assert acc["mean_error_m"] < 2.0


def test_disabled_plugin_does_not_run_and_catches_up_on_enable(match):
    pipeline = LivePipeline(match, enabled=["stats"])
    _, payloads = run(pipeline, match, upto=1200)
    assert set(payloads) == {"stats"}
    pipeline.set_enabled(["stats", "pass_quality"])
    caught_up = pipeline.plugins["pass_quality"].snapshot()["teams"]
    reference = LivePipeline(match, enabled=["pass_quality"])
    run(reference, match, upto=1200)
    assert caught_up == reference.plugins["pass_quality"].snapshot()["teams"]


def test_goal_insight_emitted(match):
    insights, _ = run(LivePipeline(match), match)
    goals = sum(match.meta.final_score.values())
    assert sum(1 for i in insights if i.kind == "goal") == goals


def test_physical_metrics_ignore_restart_teleports(match):
    pipeline = LivePipeline(match)
    run(pipeline, match)
    players = pipeline.plugins["stats"].snapshot()["players"]
    assert max(p["top_speed_kmh"] for p in players) < 40
    assert max(p["distance_m"] for p in players) < 6 * 60 * 9  # under 9 m/s on average


def test_fatigue_compares_real_sprints_only(match):
    stats = LivePipeline(match).plugins["stats"]
    fresh = {m: 30.0 for m in range(0, 20)}
    stats._minute_top["tired"] = {**fresh, **{m: 26.0 for m in range(46, 60)}}
    stats._minute_top["idle"] = {**fresh, **{m: 12.0 for m in range(46, 60)}}  # no sprints lately
    assert round(stats._fatigue_pct("tired", 60 * 60.0), 1) == 13.3
    assert stats._fatigue_pct("idle", 60 * 60.0) is None
    assert stats._fatigue_pct("tired", 30 * 60.0) is None  # too early to judge


def test_forecast_calls_on_target_shots_before_they_arrive(long_match):
    insights, _ = run(LivePipeline(long_match), long_match)
    calls = [i for i in insights if i.kind == "forecast_on_target"]
    assert calls, "expected at least one on-target forecast"
    assert len(calls) <= sum(1 for e in long_match.events if e.type == "shot")
    assert all(c.data["lead_s"] > 0 for c in calls)


def test_overlay_cues_follow_insights(match):
    pipeline = LivePipeline(match)
    insights, _ = run(pipeline, match)
    timeline = pipeline.plugins["overlays"].snapshot()["timeline"]
    goal_cues = [c for c in timeline if c["template"] == "goal"]
    assert len(goal_cues) == sum(1 for i in insights if i.kind == "goal")
    for cue in timeline:
        assert cue["t_out"] > cue["t_in"]
        assert cue["slot"] in {"lower_third", "top_bug", "side_panel"}
    # At any moment at most one cue per slot is live.
    active = pipeline.plugins["overlays"].active(timeline[0]["t_in"] + 0.1)
    assert len({c["slot"] for c in active}) == len(active)
