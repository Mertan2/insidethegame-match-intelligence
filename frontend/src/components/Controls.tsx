import type { MatchMeta, Persona, PluginInfo, Side } from "../types";

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
  available: PluginInfo[];
  enabled: string[];
  onPlugins: (enabled: string[]) => void;
}

export function Controls({ meta, persona, onPersona, paused, speed, t, onControl, available, enabled, onPlugins }: Props) {
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
        />
      </div>
      <div className="control-group">
        <div className="segmented">
          {(["casual", "analyst"] as const).map((m) => (
            <button key={m} className={persona.mode === m ? "active" : ""} onClick={() => onPersona({ mode: m })}>
              {m === "casual" ? "Casual fan" : "Analyst"}
            </button>
          ))}
        </div>
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
        <select value={persona.favorite_player ?? ""} onChange={(e) => onPersona({ favorite_player: e.target.value || null })}>
          <option value="">Follow a player…</option>
          {meta.players.map((p) => (
            <option key={p.id} value={p.id}>
              {meta.teams[p.team].short} #{p.number} {p.name}
            </option>
          ))}
        </select>
      </div>
      <div className="control-group plugins">
        {available.map((p) => (
          <label key={p.name} title={p.description}>
            <input
              type="checkbox"
              checked={enabled.includes(p.name)}
              onChange={(e) => onPlugins(e.target.checked ? [...enabled, p.name] : enabled.filter((n) => n !== p.name))}
            />
            {p.name}
          </label>
        ))}
      </div>
    </div>
  );
}
