import { useState } from "react";

export interface MatchSummary {
  match_id: string;
  seed: number;
  minutes: number;
  home: string;
  away: string;
  final_score: { home: number; away: number };
}

interface Props {
  matches: MatchSummary[];
  current: string | null;
  onSelect: (matchId: string) => void;
  onCreated: (matches: MatchSummary[], matchId: string) => void;
}

/** Pick a stored match or generate a new synthetic one (any seed, any length). */
export function MatchPicker({ matches, current, onSelect, onCreated }: Props) {
  const [minutes, setMinutes] = useState(20);
  const [busy, setBusy] = useState(false);

  const generate = async () => {
    setBusy(true);
    try {
      const seed = Math.floor(Math.random() * 10_000);
      const res = await fetch("/api/matches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seed, minutes }),
      });
      const created: { match_id: string } = await res.json();
      const list: MatchSummary[] = await (await fetch("/api/matches")).json();
      onCreated(list, created.match_id);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="control-group">
      <select value={current ?? ""} onChange={(e) => onSelect(e.target.value)} title="Synthetic match">
        {matches.map((m) => (
          <option key={m.match_id} value={m.match_id}>
            Seed {m.seed} · {m.minutes}′ (FT {m.final_score.home}-{m.final_score.away})
          </option>
        ))}
      </select>
      <select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} disabled={busy}>
        {[10, 20, 45, 90].map((m) => (
          <option key={m} value={m}>
            {m} min
          </option>
        ))}
      </select>
      <button onClick={generate} disabled={busy}>
        {busy ? `Generating… (~${Math.max(2, Math.round(minutes / 4))}s)` : "New match"}
      </button>
    </div>
  );
}
