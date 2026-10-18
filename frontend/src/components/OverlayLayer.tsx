import type { MatchMeta, OverlayCue } from "../types";

/** Renders broadcast cues the way a graphics engine would: one graphic per screen slot. */
export function OverlayLayer({ meta, cues }: { meta: MatchMeta; cues: OverlayCue[] }) {
  return (
    <div className="overlay-layer">
      {cues.map((cue) => (
        <div
          key={cue.id}
          className={`cue cue-${cue.slot}`}
          style={{ borderColor: cue.team ? meta.teams[cue.team].color : "#ffe65a" }}
        >
          <CueBody cue={cue} meta={meta} />
        </div>
      ))}
    </div>
  );
}

function CueBody({ cue, meta }: { cue: OverlayCue; meta: MatchMeta }) {
  const d = cue.data as Record<string, number | string | undefined>;
  switch (cue.template) {
    case "goal":
      return (
        <>
          <div className="cue-kicker">GOAL · {cue.team_name}</div>
          <div className="cue-title">{cue.player ?? "Own goal"}</div>
          <div className="cue-sub">
            {meta.teams.home.short} {cue.score.home} - {cue.score.away} {meta.teams.away.short}
          </div>
        </>
      );
    case "big_chance":
      return (
        <>
          <div className="cue-kicker">BIG CHANCE · xG {Number(d.xg).toFixed(2)}</div>
          <div className="cue-title">{cue.player}</div>
          <div className="cue-sub">{String(d.outcome ?? "").replace("_", " ")}</div>
        </>
      );
    case "forecast_on_target":
      return (
        <>
          <div className="cue-kicker">BALL TRACKER</div>
          <div className="cue-title">ON TARGET in {Number(d.lead_s).toFixed(1)}s</div>
          <div className="cue-sub">{d.speed_kmh} km/h</div>
        </>
      );
    case "shot_speed":
    case "shot":
      return (
        <>
          <div className="cue-kicker">SHOT · {cue.player}</div>
          <div className="cue-title">{d.speed_kmh} km/h</div>
        </>
      );
    case "pass_rating":
      return (
        <>
          <div className="cue-kicker">PASS RATING · {cue.player}</div>
          <div className="cue-title">{d.difficulty}/100</div>
          <div className="cue-sub">{d.distance_m} m</div>
        </>
      );
    case "momentum":
      return (
        <>
          <div className="cue-kicker">MOMENTUM</div>
          <div className="cue-title">{cue.team_name}</div>
        </>
      );
    case "regime":
      return (
        <>
          <div className="cue-kicker">GAME STATE</div>
          <div className="cue-title">{String(d.regime ?? "").toUpperCase()}</div>
          <div className="cue-sub">{d.possession_changes_per_min} turnovers/min</div>
        </>
      );
    default:
      return <div className="cue-title">{cue.template}</div>;
  }
}
