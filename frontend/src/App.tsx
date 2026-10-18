import { useEffect, useState } from "react";
import { Ball3D } from "./components/Ball3D";
import { CommentaryFeed } from "./components/CommentaryFeed";
import { Controls } from "./components/Controls";
import { MatchPicker, type MatchSummary } from "./components/MatchPicker";
import { OverlayLayer } from "./components/OverlayLayer";
import { Pitch2D } from "./components/Pitch2D";
import { PlayerFocus } from "./components/PlayerFocus";
import { RecapPanel } from "./components/RecapPanel";
import { StatsPanel } from "./components/StatsPanel";
import type { Persona } from "./types";
import { useLiveMatch } from "./useLiveMatch";

const DEFAULT_PERSONA: Persona = { mode: "casual", language: "en", favorite_team: null, favorite_player: null };

export default function App() {
  const [matchId, setMatchId] = useState<string | null>(null);
  const [persona, setPersona] = useState<Persona>(DEFAULT_PERSONA);
  const [view, setView] = useState<"2d" | "3d" | "both">("both");
  const [matches, setMatches] = useState<MatchSummary[]>([]);
  // The current persona is read when (re)connecting, so switching match keeps the viewer's settings.
  const { state, send, clearNarrations } = useLiveMatch(matchId, persona, 4);

  useEffect(() => {
    fetch("/api/matches")
      .then((r) => r.json())
      .then((list: MatchSummary[]) => {
        setMatches(list);
        setMatchId(list[0]?.match_id ?? null);
      });
  }, []);

  const updatePersona = (patch: Partial<Persona>) => {
    const next = { ...persona, ...patch };
    setPersona(next);
    send({ type: "persona", persona: next });
  };

  const control = (msg: { action?: string; t?: number; speed?: number }) => {
    if (msg.action === "seek") clearNarrations();
    send({ type: "control", ...msg });
  };

  const { meta, frame } = state;
  if (!meta) return <div className="loading">{matchId ? "Connecting to live feed…" : "Loading match…"}</div>;

  const clock = frame ? `${Math.floor(frame.t / 60)}:${String(Math.floor(frame.t % 60)).padStart(2, "0")}` : "0:00";

  return (
    <div className="app">
      <header>
        <div className="brand">Inside the Game · Match Intelligence</div>
        <div className="scoreboard">
          <span className="team" style={{ color: meta.teams.home.color }}>{meta.teams.home.name}</span>
          <span className="score">
            {frame?.score.home ?? 0} - {frame?.score.away ?? 0}
          </span>
          <span className="team" style={{ color: meta.teams.away.color }}>{meta.teams.away.name}</span>
          <span className="clock">{clock}</span>
          {state.ended && <span className="chip">FT</span>}
          {!state.connected && <span className="chip warn">offline</span>}
        </div>
        <div className="segmented">
          {(["2d", "3d", "both"] as const).map((v) => (
            <button key={v} className={view === v ? "active" : ""} onClick={() => setView(v)}>
              {v.toUpperCase()}
            </button>
          ))}
        </div>
        <MatchPicker
          matches={matches}
          current={matchId}
          onSelect={setMatchId}
          onCreated={(list, id) => {
            setMatches(list);
            setMatchId(id);
          }}
        />
      </header>

      <Controls
        meta={meta}
        persona={persona}
        onPersona={updatePersona}
        paused={state.paused}
        speed={state.speed}
        t={frame?.t ?? 0}
        onControl={(m) => control(m)}
        available={state.available}
        enabled={state.enabled}
        onPlugins={(enabled) => send({ type: "plugins", enabled })}
      />

      <main>
        <section className={`views ${view}`}>
          {view !== "3d" && (
            <div className="view view2d">
              <OverlayLayer meta={meta} cues={state.plugins.overlays?.active ?? []} />
              <Pitch2D
                meta={meta}
                frame={frame}
                forecast={state.plugins.ball_forecast}
                speed={state.plugins.speed_metrics}
                favoritePlayer={persona.favorite_player}
              />
            </div>
          )}
          {view !== "2d" && (
            <div className="view view3d">
              <Ball3D meta={meta} frame={frame} forecast={state.plugins.ball_forecast} focusId={persona.favorite_player} />
            </div>
          )}
        </section>
        <aside>
          {persona.favorite_player && (
            <PlayerFocus meta={meta} playerId={persona.favorite_player} plugins={state.plugins} narrations={state.narrations} />
          )}
          <CommentaryFeed meta={meta} narrations={state.narrations} persona={persona} />
        </aside>
        <section className="bottom">
          <StatsPanel meta={meta} plugins={state.plugins} persona={persona} />
          <RecapPanel matchId={meta.match_id} persona={persona} />
          <div className="panel">
            <h3>Agents</h3>
            {state.agents.map((a) => (
              <div key={a.name} className="agent">
                <b>{a.name}</b> <span className="muted">{a.role}</span>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
