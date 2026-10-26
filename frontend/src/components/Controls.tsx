import { FOCUS_METRICS, type FocusMetric, type MatchMeta, type Persona, type Side } from "../types";

const LANGUAGES = [
  ["en", "English"],
  ["es", "Español"],
  ["tr", "Türkçe"],
  ["fr", "Français"],
  ["de", "Deutsch"],
  ["pt", "Português"],
  ["ar", "العربية"],
];

interface Props {
  meta: MatchMeta;
  persona: Persona;
  onPersona: (p: Partial<Persona>) => void;
  paused: boolean;
  speed: number;
  t: number;
  onControl: (msg: object) => void;
}

export function Controls({ meta, persona, onPersona, paused, speed, t, onControl }: Props) {
  const total = meta.minutes * 60;
  return (
    <div className="controls">
      <div className="control-group">
        <button onClick={() => onControl({ action: paused ? "play" : "pause" })}>{paused ? "▶ Play" : "⏸ Pause"}</button>
        <select value={speed} onChange={(e) => onControl({ speed: Number(e.target.value) })}>
          {[1, 2, 4, 8, 16, 32].map((s) => (
            <option key={s} value={s}>
              {s}x
            </option>
          ))}
        </select>
        <input
          type="range"
          min={0}
          max={total}
          step={5}
          value={t}
          onChange={(e) => onControl({ action: "seek", t: Number(e.target.value) })}
          className="seek"
          aria-label="Match clock"
        />
        <span className="muted seek-label">
          {Math.floor(t / 60)}' / {meta.minutes}'
        </span>
      </div>
      <div className="control-group">
        <select value={persona.language} onChange={(e) => onPersona({ language: e.target.value })}>
          {LANGUAGES.map(([code, label]) => (
            <option key={code} value={code}>
              {label}
            </option>
          ))}
        </select>
        <select
          value={persona.favorite_team ?? ""}
          onChange={(e) => onPersona({ favorite_team: (e.target.value || null) as Side | null })}
        >
          <option value="">No favourite club</option>
          <option value="home">{meta.teams.home.name}</option>
          <option value="away">{meta.teams.away.name}</option>
        </select>
        <select value={persona.focus_metric ?? ""} onChange={(e) => onPersona({ focus_metric: (e.target.value || null) as FocusMetric | null })} title="The one metric you care about: it stays on screen and in the commentary">
          <option value="">Metric I care about…</option>
          {FOCUS_METRICS.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
        <select value={persona.favorite_player ?? ""} onChange={(e) => onPersona({ favorite_player: e.target.value || null })}>
          <option value="">Follow a player…</option>
          {meta.players.map((p) => (
            <option key={p.id} value={p.id}>
              {meta.teams[p.team].short} #{p.number} {p.name}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
