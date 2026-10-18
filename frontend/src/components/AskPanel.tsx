import { useState } from "react";
import type { Answer, Persona } from "../types";

const SUGGESTIONS: Record<string, string[]> = {
  en: ["Who has been the best player so far?", "Why is one team dominating?", "Who is tiring?", "How good was that last shot?"],
  tr: ["Şu ana kadar en iyi oyuncu kim?", "Neden bir takım baskın?", "Kim yoruluyor?", "Son şut ne kadar iyiydi?"],
  es: ["¿Quién ha sido el mejor jugador?", "¿Por qué domina un equipo?", "¿Quién se está cansando?", "¿Qué tal fue el último disparo?"],
};

/** Ask the AI about the live match; answers show which live-data tools the agent called. */
export function AskPanel({ answers, asking, onAsk, persona, model }: {
  answers: Answer[]; asking: boolean; onAsk: (q: string) => void; persona: Persona; model: string | null;
}) {
  const [q, setQ] = useState("");
  const submit = (text: string) => {
    const t = text.trim();
    if (!t || asking) return;
    onAsk(t);
    setQ("");
  };
  return (
    <div className="panel ask">
      <h3>
        Ask the AI
        <span className="ai-badge">AI · {model ?? "offline rules"}</span>
      </h3>
      <form onSubmit={(e) => { e.preventDefault(); submit(q); }} className="ask-form">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask anything about this match…" disabled={asking} />
        <button type="submit" disabled={asking || !q.trim()}>{asking ? "Thinking…" : "Ask"}</button>
      </form>
      <div className="chips">
        {(SUGGESTIONS[persona.language] ?? SUGGESTIONS.en).map((s) => (
          <button key={s} className="chip suggestion" onClick={() => submit(s)} disabled={asking}>{s}</button>
        ))}
      </div>
      {answers.map((a, i) => (
        <div key={i} className="answer">
          <div className="answer-q"><span className="clock">{a.clock}</span> {a.question}</div>
          <p>{a.answer}</p>
          <div className="trace">
            {a.tools.map((t, j) => (
              <span key={j} className="chip tool-chip" title={JSON.stringify(t.args)}>
                ⚙ {t.tool}({Object.values(t.args).join(", ")})
              </span>
            ))}
            <span className="chip">{a.path === "llm" ? "AI" : a.path} · {(a.ms / 1000).toFixed(1)}s</span>
          </div>
        </div>
      ))}
    </div>
  );
}
