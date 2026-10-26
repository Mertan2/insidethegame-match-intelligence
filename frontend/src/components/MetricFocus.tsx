import { FOCUS_METRICS, type FocusMetric, type MatchMeta, type PluginPayloads } from "../types";

interface Props {
  meta: MatchMeta;
  metric: FocusMetric;
  plugins: PluginPayloads;
  favoritePlayer: string | null;
}

/** Metric-focus mode: the one number this viewer cares about, live, for every player. */
export function MetricFocus({ meta, metric, plugins, favoritePlayer }: Props) {
  const def = FOCUS_METRICS.find((m) => m.id === metric);
  const rows = plugins.stats?.players ?? [];
  if (!def || rows.length === 0) return null;
  const key = def.key as keyof (typeof rows)[number];
  const ranked = [...rows]
    .map((r) => ({ id: r.player_id, name: r.name, team: r.team, value: Number(r[key] ?? 0) }))
    .sort((a, b) => b.value - a.value);
  const top = ranked.slice(0, 6);
  const max = top[0]?.value || 1;
  const mine = favoritePlayer ? ranked.findIndex((r) => r.id === favoritePlayer) : -1;
  const fmt = (v: number) => (def.unit === "xG" ? v.toFixed(2) : def.unit === "km/h" ? v.toFixed(1) : String(Math.round(v)));

  return (
    <div className="panel metric-focus">
      <h3>
        Your metric <span className="ops-sum">{def.label}</span>
      </h3>
      {top.map((r, i) => (
        <div key={r.id} className={`metric-row ${r.id === favoritePlayer ? "mine" : ""}`}>
          <span className="metric-rank">{i + 1}</span>
          <span className="metric-name" style={{ color: meta.teams[r.team].color }}>{r.name}</span>
          <span className="metric-bar"><span style={{ width: `${(100 * r.value) / max}%`, background: meta.teams[r.team].color }} /></span>
          <span className="metric-val">{fmt(r.value)}{def.unit && def.unit !== "xG" ? ` ${def.unit}` : ""}</span>
        </div>
      ))}
      {mine >= 6 && (
        <div className="metric-row mine">
          <span className="metric-rank">{mine + 1}</span>
          <span className="metric-name">{ranked[mine].name}</span>
          <span className="metric-bar"><span style={{ width: `${(100 * ranked[mine].value) / max}%` }} /></span>
          <span className="metric-val">{fmt(ranked[mine].value)}</span>
        </div>
      )}
    </div>
  );
}
