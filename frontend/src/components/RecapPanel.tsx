import { useState } from "react";
import type { Persona, Recap } from "../types";

export function RecapPanel({ matchId, persona }: { matchId: string; persona: Persona }) {
  const [recap, setRecap] = useState<Recap | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    const params = new URLSearchParams({ mode: persona.mode, lang: persona.language });
    if (persona.favorite_team) params.set("favorite_team", persona.favorite_team);
    if (persona.favorite_player) params.set("favorite_player", persona.favorite_player);
    try {
      const res = await fetch(`/api/matches/${matchId}/recap?${params}`);
      setRecap(await res.json());
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="panel">
      <h3>
        Automated recap{" "}
        <button onClick={load} disabled={loading}>
          {loading ? "Writing…" : "Generate"}
        </button>
      </h3>
      {recap && (
        <>
          <h4>{recap.title}</h4>
          {recap.paragraphs.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
          <p className="muted small">
            via {recap.path}
            {recap.requested_language !== recap.language && ` · ${recap.requested_language} needs LLM, showing English`}
          </p>
        </>
      )}
    </div>
  );
}
