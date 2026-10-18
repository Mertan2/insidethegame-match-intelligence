import type { MatchMeta, Persona, PluginPayloads, Side } from "../types";

interface Props {
  meta: MatchMeta;
  plugins: PluginPayloads;
  persona: Persona;
}

export function StatsPanel({ meta, plugins, persona }: Props) {
  const stats = plugins.stats?.teams;
  const home = meta.teams.home;
  const away = meta.teams.away;
  const analyst = persona.mode === "analyst";

  const row = (label: string, h: number | string | undefined, a: number | string | undefined) => (
    <div className="stat-row" key={label}>
      <span className="num">{h ?? "-"}</span>
      <span className="label">{label}</span>
      <span className="num">{a ?? "-"}</span>
    </div>
  );

  return (
    <div className="panel">
      <h3>Match stats</h3>
      {!stats && <p className="muted">Stats plugin disabled.</p>}
      {stats && (
        <>
          <div className="poss">
            <div style={{ width: `${stats.home.possession_pct}%`, background: home.color }}>{stats.home.possession_pct}%</div>
            <div style={{ width: `${stats.away.possession_pct}%`, background: away.color }}>{stats.away.possession_pct}%</div>
          </div>
          {row("Shots", stats.home.shots, stats.away.shots)}
          {row("On target", stats.home.shots_on_target, stats.away.shots_on_target)}
          {analyst && row("xG", stats.home.xg.toFixed(2), stats.away.xg.toFixed(2))}
          {row("Passes", stats.home.passes, stats.away.passes)}
          {analyst && row("Pass accuracy %", stats.home.pass_accuracy_pct, stats.away.pass_accuracy_pct)}
          {analyst && row("Tackles won", `${stats.home.tackles_won}/${stats.home.tackles}`, `${stats.away.tackles_won}/${stats.away.tackles}`)}
          {analyst && row("Interceptions", stats.home.interceptions, stats.away.interceptions)}
          {analyst && row("Pressures", stats.home.pressures, stats.away.pressures)}
        </>
      )}
      {analyst && plugins.pass_quality && (
        <>
          {row("Avg pass difficulty", plugins.pass_quality.teams.home.avg_difficulty, plugins.pass_quality.teams.away.avg_difficulty)}
          {row("Progressive passes", plugins.pass_quality.teams.home.progressive_passes, plugins.pass_quality.teams.away.progressive_passes)}
        </>
      )}
      {plugins.momentum && <MomentumBar meta={meta} momentum={plugins.momentum.momentum} regime={plugins.momentum.regime} chaos={plugins.momentum.chaos_index} />}
      {plugins.speed_metrics && (
        <div className="chips">
          <span className="chip">Ball {plugins.speed_metrics.ball_speed_kmh} km/h</span>
          <span className="chip">Fastest shot {plugins.speed_metrics.max_shot_kmh} km/h</span>
        </div>
      )}
      {plugins.ball_forecast?.accuracy && plugins.ball_forecast.accuracy.mean_error_m !== null && (
        <div className="chips">
          <span className="chip">
            Forecast error {plugins.ball_forecast.accuracy.mean_error_m} m @ {plugins.ball_forecast.accuracy.horizon_s}s
          </span>
          {plugins.ball_forecast.active && plugins.ball_forecast.goal_crossing && (
            <span className={`chip ${plugins.ball_forecast.goal_crossing.on_target ? "hot" : ""}`}>
              {plugins.ball_forecast.goal_crossing.on_target ? "ON TARGET" : "Off target"} in {plugins.ball_forecast.goal_crossing.in_s}s
            </span>
          )}
        </div>
      )}
      {analyst && plugins.stats && <TopPlayers players={plugins.stats.players} meta={meta} />}
    </div>
  );
}

function MomentumBar({ meta, momentum, regime, chaos }: { meta: MatchMeta; momentum: number; regime: string; chaos: number }) {
  const pct = 50 + momentum * 50;
  const leader: Side = momentum >= 0 ? "home" : "away";
  return (
    <div className="momentum">
      <div className="momentum-label">
        Momentum <b style={{ color: meta.teams[leader].color }}>{meta.teams[leader].short}</b> · <span className={`regime ${regime}`}>{regime}</span>{" "}
        <span className="muted">chaos {chaos.toFixed(2)}</span>
      </div>
      <div className="momentum-track">
        <div className="momentum-mid" />
        <div className="momentum-dot" style={{ left: `${pct}%`, background: meta.teams[leader].color }} />
      </div>
    </div>
  );
}

function TopPlayers({ players, meta }: { players: NonNullable<PluginPayloads["stats"]>["players"]; meta: MatchMeta }) {
  const top = [...players].sort((a, b) => b.distance_m - a.distance_m).slice(0, 5);
  return (
    <table className="players">
      <thead>
        <tr>
          <th>Player</th>
          <th>Dist m</th>
          <th>Top km/h</th>
          <th>Pass</th>
        </tr>
      </thead>
      <tbody>
        {top.map((p) => (
          <tr key={p.player_id}>
            <td style={{ color: meta.teams[p.team].color }}>{p.name}</td>
            <td>{p.distance_m}</td>
            <td>{p.top_speed_kmh}</td>
            <td>
              {p.passes_completed}/{p.passes}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
