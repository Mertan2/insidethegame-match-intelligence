import type { MatchMeta, Persona } from "../types";

const LANGUAGES: [string, string][] = [
  ["en", "English"],
  ["tr", "Türkçe"],
  ["es", "Español"],
  ["fr", "Français"],
  ["de", "Deutsch"],
  ["pt", "Português"],
  ["ar", "العربية"],
];

interface Props {
  meta: MatchMeta;
  persona: Persona;
  voiceAvailable: boolean;
  onLanguage: (language: string) => void;
  onMode: (mode: Persona["mode"]) => void;
  onKickoff: () => void;
}

/** Pre-match screen: choose language and style, then one click starts the match with live spoken commentary. */
export function Kickoff({ meta, persona, voiceAvailable, onLanguage, onMode, onKickoff }: Props) {
  return (
    <div className="kickoff">
      <div className="kickoff-card">
        <div className="kickoff-kicker">LIVE · AI COMMENTARY</div>
        <h1>
          <span style={{ color: meta.teams.home.color }}>{meta.teams.home.name}</span>
          <span className="kickoff-vs">vs</span>
          <span style={{ color: meta.teams.away.color }}>{meta.teams.away.name}</span>
        </h1>
        <p className="muted">
          An AI commentary team watches every event and frame and talks you through the match: play-by-play, fun
          facts, recaps and the big moments{voiceAvailable ? ", spoken live" : ""}.
        </p>
        <div className="kickoff-options">
          <label>
            Commentary language
            <select value={persona.language} onChange={(e) => onLanguage(e.target.value)}>
              {LANGUAGES.map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <div className="segmented">
            {(["casual", "analyst"] as const).map((m) => (
              <button key={m} className={persona.mode === m ? "active" : ""} onClick={() => onMode(m)}>
                {m === "casual" ? "Casual fan" : "Analyst"}
              </button>
            ))}
          </div>
        </div>
        <button className="kickoff-go" onClick={onKickoff}>
          ▶ Kick off{voiceAvailable ? " with live commentary 🔊" : ""}
        </button>
      </div>
    </div>
  );
}
