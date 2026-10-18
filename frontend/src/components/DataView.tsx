import type { Frame, MatchEvent, MatchMeta, PluginPayloads, SeriesPoint } from "../types";
import type { FeedStats } from "../useLiveMatch";

interface Props {
  meta: MatchMeta;
  frame: Frame | null;
  plugins: PluginPayloads;
  series: SeriesPoint[];
  events: MatchEvent[];
  feed: FeedStats;
  playerKmh: Record<string, number>;
  pitch?: React.ReactNode;
}

/** The raw feed made visible: throughput, live charts, per-player tracking and the event stream. */
export function DataView({ meta, frame, plugins, series, events, feed, playerKmh, pitch }: Props) {
  const tMax = Math.max(60, series.length ? series[series.length - 1].t : 60);
  const home = meta.teams.home;
  const away = meta.teams.away;
  const goals = series.filter((p, i) => i > 0 && (p.goalsHome !== series[i - 1].goalsHome || p.goalsAway !== series[i - 1].goalsAway));

  return (
    <div className="dataview">
      <div className="feed-tiles">
        <Tile label="Feed" value={<><span className="pulse" /> LIVE</>} />
        <Tile label="Frame" value={frame ? `#${frame.f}` : "-"} sub="10 Hz tracking" />
        <Tile label="Messages / s" value={feed.msgsPerSec} sub={`${feed.totalMsgs} total`} />
        <Tile label="Throughput" value={`${feed.kbPerSec} KB/s`} sub={`${feed.totalKb} KB received`} />
        <Tile label="Events" value={events.length} sub="in stream" />
        <Tile label="Objects tracked" value={frame ? frame.players.length + 1 : 0} sub="22 players + ball, 44 feet" />
      </div>

      <div className="data-top">
      {pitch && <div className="view view2d data-pitch">{pitch}</div>}
      <div className="charts">
        <Chart title="xG race" tMax={tMax} yMax={Math.max(1, ...series.map((p) => Math.max(p.xgHome, p.xgAway))) * 1.1}
          lines={[{ color: home.color, values: series.map((p) => [p.t, p.xgHome]), label: home.short },
                  { color: away.color, values: series.map((p) => [p.t, p.xgAway]), label: away.short }]}
          markers={goals.map((g) => g.t)} />
        <Chart title={`Possession ${home.short} %`} tMax={tMax} yMin={20} yMax={80} mid={50}
          lines={[{ color: home.color, values: series.filter((p) => p.possHome !== null).map((p) => [p.t, p.possHome as number]), label: home.short }]}
          markers={goals.map((g) => g.t)} />
        <Chart title={`Momentum (${home.short} ↑ / ${away.short} ↓)`} tMax={tMax} yMin={-1} yMax={1} mid={0} area
          lines={[{ color: "#ffe65a", values: series.map((p) => [p.t, p.momentum]), label: "momentum" }]}
          markers={goals.map((g) => g.t)} />
        <Chart title="Ball speed km/h" tMax={tMax} yMax={Math.max(60, ...series.map((p) => p.ballKmh)) * 1.05}
          lines={[{ color: "#9be7ff", values: series.map((p) => [p.t, p.ballKmh]), label: "ball" }]} />
      </div>
      </div>

      <div className="data-tables">
        <TrackingTable meta={meta} frame={frame} plugins={plugins} playerKmh={playerKmh} />
        <EventStream meta={meta} events={events} />
      </div>
    </div>
  );
}

function Tile({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="tile">
      <div className="muted small">{label}</div>
      <div className="tile-value">{value}</div>
      {sub && <div className="muted small">{sub}</div>}
    </div>
  );
}

interface Line {
  color: string;
  values: [number, number][];
  label: string;
}

function Chart({ title, lines, tMax, yMin = 0, yMax, mid, area, markers = [] }: {
  title: string; lines: Line[]; tMax: number; yMin?: number; yMax: number; mid?: number; area?: boolean; markers?: number[];
}) {
  const W = 320, H = 110, P = 4;
  const x = (t: number) => P + (t / tMax) * (W - 2 * P);
  const y = (v: number) => H - P - ((Math.min(Math.max(v, yMin), yMax) - yMin) / (yMax - yMin || 1)) * (H - 2 * P);
  const path = (vals: [number, number][]) => vals.map(([t, v], i) => `${i ? "L" : "M"}${x(t).toFixed(1)},${y(v).toFixed(1)}`).join("");
  return (
    <div className="chart">
      <div className="chart-head">
        <span>{title}</span>
        <span className="chart-legend">
          {lines.map((l) => {
            const last = l.values[l.values.length - 1];
            return <b key={l.label} style={{ color: l.color }}>{l.label} {last ? round(last[1]) : "-"}</b>;
          })}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        {mid !== undefined && <line x1={P} x2={W - P} y1={y(mid)} y2={y(mid)} className="chart-mid" />}
        {markers.map((t) => <line key={t} x1={x(t)} x2={x(t)} y1={P} y2={H - P} className="chart-goal" />)}
        {lines.map((l) => (
          <g key={l.label}>
            {area && l.values.length > 1 && (
              <path d={`${path(l.values)}L${x(l.values[l.values.length - 1][0])},${y(mid ?? yMin)}L${x(l.values[0][0])},${y(mid ?? yMin)}Z`}
                fill={l.color} opacity={0.18} />
            )}
            <path d={path(l.values)} fill="none" stroke={l.color} strokeWidth={1.8} vectorEffect="non-scaling-stroke" />
          </g>
        ))}
      </svg>
      <div className="chart-axis muted small"><span>0′</span><span>{Math.floor(tMax / 60)}′</span></div>
    </div>
  );
}

const round = (v: number) => (Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(2));

function TrackingTable({ meta, frame, plugins, playerKmh }: { meta: MatchMeta; frame: Frame | null; plugins: PluginPayloads; playerKmh: Record<string, number> }) {
  const byId = new Map(meta.players.map((p) => [p.id, p]));
  const feet = new Map((frame?.feet ?? []).map((f) => [f[0], f]));
  const stats = new Map((plugins.stats?.players ?? []).map((p) => [p.player_id, p]));
  const rows = (frame?.players ?? [])
    .map(([id, x, y]) => ({ id, x, y, p: byId.get(id)!, kmh: playerKmh[id] ?? 0 }))
    .sort((a, b) => b.kmh - a.kmh);
  return (
    <div className="panel table-panel">
      <h3>Live tracking <span className="muted small">sorted by current speed</span></h3>
      <table className="players live">
        <thead>
          <tr><th>#</th><th>Player</th><th>x m</th><th>y m</th><th>Speed</th><th>Left foot</th><th>Right foot</th><th>Dist</th><th>Owner</th></tr>
        </thead>
        <tbody>
          {rows.map(({ id, x, y, p, kmh }) => {
            const f = feet.get(id);
            const s = stats.get(id);
            return (
              <tr key={id}>
                <td><span className="num-chip" style={{ background: meta.teams[p.team].color }}>{p.number}</span></td>
                <td>{p.name}</td>
                <td>{x.toFixed(1)}</td>
                <td>{y.toFixed(1)}</td>
                <td className="speed-cell">
                  <div className="speed-bar" style={{ width: `${Math.min(100, (kmh / 32) * 100)}%`, background: kmh > 24 ? "#ff7a59" : "#4fd1a5" }} />
                  <span>{kmh.toFixed(1)}</span>
                </td>
                <td className={f && f[3] > 0.05 ? "lifted" : ""}>{f ? `z ${f[3].toFixed(2)}` : "-"}</td>
                <td className={f && f[6] > 0.05 ? "lifted" : ""}>{f ? `z ${f[6].toFixed(2)}` : "-"}</td>
                <td>{s ? `${s.distance_m} m` : "-"}</td>
                <td>{frame?.owner === id ? "⚽" : ""}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const EVENT_LABEL: Record<string, string> = {
  pass: "PASS", shot: "SHOT", goal: "GOAL", tackle: "TACKLE", pressure: "PRESS", possession_change: "TURNOVER",
  throw_in: "THROW", goal_kick: "G.KICK", corner: "CORNER", kickoff: "KICKOFF", half_time: "HT", full_time: "FT",
};

function EventStream({ meta, events }: { meta: MatchMeta; events: MatchEvent[] }) {
  const byId = new Map(meta.players.map((p) => [p.id, p]));
  return (
    <div className="panel table-panel">
      <h3>Event stream <span className="muted small">newest first</span></h3>
      <div className="event-stream">
        {events.map((e) => {
          const d = e.data as Record<string, string | number | boolean | null>;
          const who = e.player_id ? byId.get(e.player_id)?.name : null;
          const detail = [
            d.kind, d.body_part && String(d.body_part).replace("_", " "), d.distance && `${d.distance} m`,
            d.speed_kmh && `${d.speed_kmh} km/h`, d.xg !== undefined && d.xg !== null && `xG ${d.xg}`,
            d.outcome, d.cause, d.success !== undefined && (d.success ? "won" : "lost"),
          ].filter(Boolean).join(" · ");
          return (
            <div key={e.id} className={`ev ev-${e.type}`}>
              <span className="ev-clock">{Math.floor(e.t / 60)}:{String(Math.floor(e.t % 60)).padStart(2, "0")}</span>
              <span className="ev-type" style={{ borderColor: e.team ? meta.teams[e.team].color : "#556" }}>{EVENT_LABEL[e.type] ?? e.type}</span>
              <span className="ev-who">{who ?? (e.team ? meta.teams[e.team].name : "")}</span>
              <span className="ev-detail muted">{detail}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
