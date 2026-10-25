import type { MatchMeta, Narration, PluginPayloads } from "../types";

interface Props {
  meta: MatchMeta;
  playerId: string;
  plugins: PluginPayloads;
  narrations: Narration[];
}

/** Player-focus mode: one player's live numbers and every moment they were involved in. */
export function PlayerFocus({ meta, playerId, plugins, narrations }: Props) {
  const player = meta.players.find((p) => p.id === playerId);
  if (!player) return null;
  const team = meta.teams[player.team];
  const stats = plugins.stats?.players.find((p) => p.player_id === playerId);
  const tag = plugins.speed_metrics?.tags.find((t) => t.player_id === playerId);
  const moments = narrations.filter((n) => n.player_id === playerId);

  return (
    <div className="panel focus" style={{ borderColor: team.color }}>
      <h3>
        Player focus
        {tag && <span className="chip hot">{tag.distance_km != null ? `${tag.distance_km} km covered` : `sprinting ${tag.speed_kmh} km/h`}</span>}
      </h3>
      <div className="focus-name">
        <span className="focus-number" style={{ background: team.color }}>
          {player.number}
        </span>
        <div>
          <b>{player.name}</b>
          <div className="muted small">
            {team.name} · {player.role}
          </div>
        </div>
      </div>
      {stats ? (
        <div className="focus-grid">
          <Metric label="Distance" value={`${(stats.distance_m / 1000).toFixed(2)} km`} />
          <Metric label="Top speed" value={`${stats.top_speed_kmh} km/h`} />
          <Metric label="Passes" value={`${stats.passes_completed}/${stats.passes}`} />
          <Metric label="Shots · xG" value={`${stats.shots} · ${stats.xg.toFixed(2)}`} />
          <Metric label="Strong foot" value={player.preferred_foot === "left" ? "Left" : "Right"} />
          <Metric
            label="Sprint drop"
            value={stats.fatigue_pct === null ? "measuring…" : `${stats.fatigue_pct}% vs fresh`}
          />
          <Metric
            label="Weak foot use"
            value={`${stats.weak_foot_pct}%${stats.weak_foot_success_pct !== null ? ` · ${stats.weak_foot_success_pct}% ok` : ""}`}
          />
          <FootSplit left={stats.left_foot} right={stats.right_foot} headers={stats.headers} />
        </div>
      ) : (
        <p className="muted small">Enable the stats plugin for live numbers.</p>
      )}
      {moments.length > 0 && (
        <div className="focus-moments">
          {moments.slice(0, 4).map((m, i) => (
            <div key={i} className="small">
              <span className="clock">{m.clock}</span> {m.text}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function FootSplit({ left, right, headers }: { left: number; right: number; headers: number }) {
  const total = left + right + headers;
  const pct = (n: number) => (total ? (100 * n) / total : 0);
  return (
    <div className="foot-split">
      <div className="muted small">
        Touches L {left} · R {right} · Head {headers}
      </div>
      <div className="foot-bar">
        <div style={{ width: `${total ? pct(left) : 50}%` }} className="foot-left" />
        <div style={{ width: `${pct(headers)}%` }} className="foot-head" />
        <div style={{ width: `${total ? pct(right) : 50}%` }} className="foot-right" />
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <div className="muted small">{label}</div>
      <div className="metric-value">{value}</div>
    </div>
  );
}
