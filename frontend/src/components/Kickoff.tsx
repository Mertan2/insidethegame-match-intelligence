import { AUDIENCES, type Audience } from "../audience";
import type { MatchMeta, Persona } from "../types";
import { BrandMark, Icon } from "./Icon";

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
  audience: Audience;
  onAudience: (a: Audience) => void;
  onKickoff: () => void;
}

/** Pre-match screen: who is watching and in which language, then one click starts the match with live spoken commentary. */
export function Kickoff({ meta, persona, voiceAvailable, onLanguage, audience, onAudience, onKickoff }: Props) {
  return (
    <div className="kickoff">
      <div className="kickoff-card">
        <div className="kickoff-kicker">
          <BrandMark size={11} /> INSIDE THE GAME
        </div>
        <h1 className="kickoff-headline">
          Your personal commentator. <span>Live.</span>
        </h1>
        <p className="kickoff-sub">
          <span style={{ color: meta.teams.home.color }}>{meta.teams.home.name}</span>
          <span className="kickoff-vs"> v </span>
          <span style={{ color: meta.teams.away.color }}>{meta.teams.away.name}</span>
          <span className="muted"> · {meta.minutes}-minute match · a team of AI agents commentates every moment{voiceAvailable ? ", out loud" : ""}</span>
        </p>
        <div className="kickoff-who">Who's watching?</div>
        <div className="audience-cards">
          {(Object.keys(AUDIENCES) as Audience[]).map((a) => (
            <button key={a} className={`audience-card ${audience === a ? "active" : ""}`} onClick={() => onAudience(a)}>
              <span className="audience-icon">
                <Icon name={AUDIENCES[a].icon} size={24} />
              </span>
              <b>{AUDIENCES[a].label}</b>
              <span>{AUDIENCES[a].blurb}</span>
            </button>
          ))}
        </div>
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
        </div>
        <button className="kickoff-go" onClick={onKickoff}>
          <Icon name="play" size={18} /> Kick off{voiceAvailable ? " with live commentary" : ""}
        </button>
        <div className="kickoff-foot muted">Club, player and the metric you care about can be set any time during the match.</div>
      </div>
    </div>
  );
}
