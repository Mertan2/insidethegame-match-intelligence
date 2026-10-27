import type { MatchMeta, Moment, Narration, Persona } from "../types";
import { Icon } from "./Icon";

const KIND_LABEL: Record<string, string> = {
  play_by_play: "play-by-play",
  fun_fact: "fun fact",
  recap: "recap",
  half_time_recap: "half-time recap",
  full_time_recap: "full-time recap",
};

interface Props {
  meta: MatchMeta;
  narrations: Narration[];
  persona: Persona;
  model: string | null;
  moments?: Moment[];
  onExplain?: (m: Moment) => void;
}

/** The key moment a commentary line is about (a goal or chance a few seconds earlier), if any. */
function momentFor(n: Narration, moments: Moment[]): Moment | undefined {
  if (!["goal", "big_chance", "rocket_shot", "forecast_on_target"].includes(n.kind)) return undefined;
  return moments.find((m) => m.t <= n.t + 1 && n.t - m.t < 6);
}

export function CommentaryFeed({ meta, narrations, persona, model, moments = [], onExplain }: Props) {
  const analyst = persona.mode === "analyst";
  return (
    <div className="panel feed">
      <h3>Live AI commentary</h3>
      {narrations.length === 0 && <p className="muted">The agents are watching. Commentary appears at the next key moment or state-of-play update.</p>}
      {narrations.map((n, i) => (
        <div key={`${n.t}-${i}`} className={`narration ${n.kind}`} style={{ borderColor: n.team ? meta.teams[n.team].color : "#556" }}>
          <div className="narration-head">
            <span className="clock">{n.clock}</span>
            <span className={`kind kind-${n.kind}`}>{KIND_LABEL[n.kind] ?? n.kind.replaceAll("_", " ")}</span>
            {n.trace.some((s) => s.path === "llm") ? (
              <span className="ai-badge on small" title="Written live by the agent team">AI · {model ?? "model"}</span>
            ) : (
              <span className="muted small">rule template</span>
            )}
            {n.requested_language !== n.language && (
              <span className="muted small" title="Translation needs an LLM (set AZURE_OPENAI_* env vars)">
                {n.requested_language} → en fallback
              </span>
            )}
          </div>
          <p>{n.text}</p>
          {n.check && n.check.numbers > 0 && (
            <span
              className={`check-chip ${n.check.grounded ? "ok" : "warn"}`}
              title="The fact-checker agent compared every number in this line with the stats agent's facts"
            >
              {n.check.grounded ? `✓ ${n.check.numbers} number${n.check.numbers === 1 ? "" : "s"} fact-checked` : `unverified: ${n.check.flagged.join(", ")}`}
            </span>
          )}
          {onExplain && momentFor(n, moments) && (
            <button className="explain-btn" onClick={() => onExplain(momentFor(n, moments)!)}>
              <Icon name="play" size={12} /> Replay & explain
            </button>
          )}
          {analyst && n.facts.length > 0 && (
            <details className="brief">
              <summary>What the director told the narrator</summary>
              <ul>
                {n.facts.map((f, j) => (
                  <li key={j}>{f}</li>
                ))}
              </ul>
            </details>
          )}
          {analyst && n.why.length > 0 && (
            <ul className="why">
              {n.why.map((w, j) => (
                <li key={j}>{w}</li>
              ))}
            </ul>
          )}
          {analyst && (
            <div className="trace">
              {n.trace
                .filter((s) => s.status)
                .map((s) => (
                  <span key={s.agent} className={`chip ${s.status === "ok" ? "" : "warn"}`} title={s.status}>
                    {s.agent} · {s.path} · {s.ms}ms
                  </span>
                ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
