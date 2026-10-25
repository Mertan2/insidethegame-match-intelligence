import type { MatchMeta, Moment } from "../types";

interface Props {
  meta: MatchMeta;
  moments: Moment[];
  now: number;
  ended: boolean;
  busy: string | null;
  onExplain: (m: Moment) => void;
  onHighlights: () => void;
}

const ICON: Record<Moment["kind"], string> = { goal: "⚽", save: "🧤", miss: "↗" };

/**
 * The match so far as a timeline of key moments (no spoilers: only what has happened).
 * Click a moment to have the explainer agent break it down on the replay; the button cuts
 * an AI highlights package of everything so far.
 */
export function MomentsBar({ meta, moments, now, ended, busy, onExplain, onHighlights }: Props) {
  const total = meta.minutes * 60;
  const seen = moments.filter((m) => m.t <= now);
  const players = new Map(meta.players.map((p) => [p.id, p.name]));
  const half = total / 2;
  return (
    <div className="moments-bar">
      <div className="moments-label">
        <b>Key moments</b>
        <span className="muted">click to explain</span>
      </div>
      <div className="moments-track">
        <div className="moments-played" style={{ width: `${Math.min(100, (100 * now) / total)}%` }} />
        <div className="moments-half" style={{ left: `${(100 * half) / total}%` }} title="Half time" />
        {seen.map((m) => (
          <button
            key={m.id}
            className={`moment-pin ${m.kind}`}
            style={{ left: `${(100 * m.t) / total}%`, borderColor: meta.teams[m.team].color }}
            title={`${m.minute}' ${m.kind} · ${players.get(m.player_id)} (${meta.teams[m.team].short}) · xG ${m.xg.toFixed(2)}`}
            onClick={() => onExplain(m)}
            disabled={busy !== null}
          >
            {ICON[m.kind]}
          </button>
        ))}
        {seen.length === 0 && <span className="moments-empty muted">Shots and goals appear here as they happen</span>}
      </div>
      <button className="highlights-btn" onClick={onHighlights} disabled={busy !== null || seen.length === 0}>
        🎬 {ended ? "Match highlights" : "Highlights so far"}
      </button>
    </div>
  );
}
