import type { MatchMeta, Narration, Persona } from "../types";

interface Props {
  meta: MatchMeta;
  narrations: Narration[];
  persona: Persona;
  model: string | null;
}

export function CommentaryFeed({ meta, narrations, persona, model }: Props) {
  const analyst = persona.mode === "analyst";
  return (
    <div className="panel feed">
      <h3>Live AI commentary</h3>
      {narrations.length === 0 && <p className="muted">The agents are watching. Commentary appears at the next key moment or state-of-play update.</p>}
      {narrations.map((n, i) => (
        <div key={`${n.t}-${i}`} className={`narration ${n.kind}`} style={{ borderColor: n.team ? meta.teams[n.team].color : "#556" }}>
          <div className="narration-head">
            <span className="clock">{n.clock}</span>
            <span className="kind">{n.kind.replaceAll("_", " ")}</span>
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
