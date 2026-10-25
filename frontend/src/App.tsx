import { useEffect, useRef, useState } from "react";
import { Ball3D } from "./components/Ball3D";
import { AgentOps } from "./components/AgentOps";
import { AskPanel } from "./components/AskPanel";
import { CommentaryFeed } from "./components/CommentaryFeed";
import { Controls } from "./components/Controls";
import { DataView } from "./components/DataView";
import { Kickoff } from "./components/Kickoff";
import { MatchPicker, type MatchSummary } from "./components/MatchPicker";
import { MomentsBar } from "./components/MomentsBar";
import { OverlayLayer } from "./components/OverlayLayer";
import { Pitch2D } from "./components/Pitch2D";
import { PlayerFocus } from "./components/PlayerFocus";
import { RecapPanel } from "./components/RecapPanel";
import { ReplayTheater } from "./components/ReplayTheater";
import { StatsPanel } from "./components/StatsPanel";
import { AUDIENCES, loadAudience, saveAudience, type Audience, type View } from "./audience";
import type { Moment, Persona, Program, ReplayItem, TraceStep } from "./types";
import { useLiveMatch } from "./useLiveMatch";
import { useVoice } from "./useVoice";

const START_AUDIENCE = loadAudience();
const DEFAULT_PERSONA: Persona = { mode: AUDIENCES[START_AUDIENCE].mode, language: "en", favorite_team: null, favorite_player: null };

export default function App() {
  const [matchId, setMatchId] = useState<string | null>(null);
  const [persona, setPersona] = useState<Persona>(DEFAULT_PERSONA);
  const [audience, setAudienceState] = useState<Audience>(START_AUDIENCE);
  const [view, setView] = useState<View>(AUDIENCES[START_AUDIENCE].view);
  const [setupOpen, setSetupOpen] = useState(false);
  const [model, setModel] = useState<string | null>(null);
  const [voiceAvailable, setVoiceAvailable] = useState(false);
  const [voiceOn, setVoiceOn] = useState(false);
  const [kickedOff, setKickedOff] = useState(false);
  const [matches, setMatches] = useState<MatchSummary[]>([]);
  // The current persona is read when (re)connecting, so switching match keeps the viewer's settings.
  // The first match waits at 0:00 for the kick-off click (browsers only allow sound after a click).
  const { state, send, ask, clearNarrations } = useLiveMatch(matchId, persona, 2, !kickedOff);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then((h: { model: string | null; voice: string | null }) => {
        setModel(h.model);
        setVoiceAvailable(Boolean(h.voice));
      });
    fetch("/api/matches")
      .then((r) => r.json())
      .then((list: MatchSummary[]) => {
        setMatches(list);
        setMatchId(list[0]?.match_id ?? null);
      });
  }, []);

  const [moments, setMoments] = useState<Moment[]>([]);
  const [program, setProgram] = useState<Program | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [ftDismissed, setFtDismissed] = useState(false);
  const resumeAfterReplay = useRef(false);
  const justResumed = useRef(false); // play sent after a replay, acknowledgement not back yet

  useEffect(() => {
    if (!state.paused) justResumed.current = false;
  }, [state.paused]);

  useEffect(() => {
    setMoments([]);
    if (!matchId) return;
    fetch(`/api/matches/${matchId}/moments`)
      .then((r) => r.json())
      .then(setMoments)
      .catch(() => setMoments([]));
  }, [matchId]);

  // Live commentary stays quiet while a replay is on.
  const { speak, speaking, stop: stopVoice } = useVoice(voiceOn && program === null);
  const latestNarration = state.narrations[0];
  const latestAnswer = state.answers[0];
  // Speak each new AI commentary line and each answer as it arrives.
  useEffect(() => {
    // Above 2x the play outruns any voice: only key moments are spoken then.
    const key = ["goal", "big_chance", "half_time_recap", "full_time_recap"].includes(latestNarration?.kind ?? "");
    if (latestNarration && (state.speed <= 2 || key)) speak(latestNarration.text, latestNarration.language, latestNarration.kind);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestNarration]);
  useEffect(() => {
    if (latestAnswer) speak(latestAnswer.answer, persona.language, "answer");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestAnswer]);

  /** Pause the live feed, ask the agents for a replay, then open the theatre. */
  const openReplay = async <T,>(label: string, url: string, toProgram: (data: T) => Program) => {
    setBusy(label);
    resumeAfterReplay.current = (!state.paused || justResumed.current) && !state.ended;
    send({ type: "control", action: "pause" });
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(String(res.status));
      setProgram(toProgram((await res.json()) as T));
    } catch {
      if (resumeAfterReplay.current) send({ type: "control", action: "play" });
    } finally {
      setBusy(null);
    }
  };
  const query = `mode=${persona.mode}&lang=${persona.language}`;
  const explainMoment = (m: Moment) =>
    openReplay("The explainer agent is breaking it down…", `/api/matches/${matchId}/moments/${m.id}/explain?${query}`, (r: ReplayItem) => ({
      kind: "explain",
      language: r.language,
      items: [r],
      trace: r.trace,
    }));
  const highlightsSoFar = () =>
    openReplay(
      "Producer is picking the clips · explainers writing in parallel…",
      `/api/matches/${matchId}/highlights?${query}${state.ended ? "" : `&upto=${state.frame?.t ?? 0}`}`,
      (r: { intro: string; outro: string; items: ReplayItem[]; trace: TraceStep[]; language: string }) => ({ kind: "reel", ...r }),
    );
  const closeReplay = () => {
    setProgram(null);
    if (resumeAfterReplay.current) {
      send({ type: "control", action: "play" });
      justResumed.current = true;
    }
  };

  const updatePersona = (patch: Partial<Persona>) => {
    const next = { ...persona, ...patch };
    setPersona(next);
    send({ type: "persona", persona: next });
  };
  const setAudience = (a: Audience) => {
    setAudienceState(a);
    saveAudience(a);
    setView(AUDIENCES[a].view);
    updatePersona({ mode: AUDIENCES[a].mode });
  };

  const control = (msg: { action?: string; t?: number; speed?: number }) => {
    if (msg.action === "seek") {
      clearNarrations();
      stopVoice();
    }
    send({ type: "control", ...msg });
  };

  const { meta, frame } = state;
  if (!meta) return <div className="loading">{matchId ? "Connecting to live feed…" : "Loading match…"}</div>;

  const clock = frame ? `${Math.floor(frame.t / 60)}:${String(Math.floor(frame.t % 60)).padStart(2, "0")}` : "0:00";

  const live = !state.ended && !state.paused;
  const cfg = AUDIENCES[audience];

  return (
    <div className={`app audience-${audience}`}>
      {!kickedOff && (
        <Kickoff
          meta={meta}
          persona={persona}
          voiceAvailable={voiceAvailable}
          onLanguage={(language) => updatePersona({ language })}
          audience={audience}
          onAudience={setAudience}
          onKickoff={() => {
            setVoiceOn(voiceAvailable);
            setKickedOff(true);
            send({ type: "control", action: "play" });
          }}
        />
      )}
      <header>
        <div className="brand">
          <span className="brand-mark">◆</span> Inside the Game
        </div>
        <div className="scoreboard">
          <span className="team" style={{ color: meta.teams.home.color }}>{meta.teams.home.name}</span>
          <span className="score">
            {frame?.score.home ?? 0} - {frame?.score.away ?? 0}
          </span>
          <span className="team" style={{ color: meta.teams.away.color }}>{meta.teams.away.name}</span>
          <span className="clock">{clock}</span>
          {state.ended ? <span className="chip">FT</span> : live && <span className="live-dot">LIVE</span>}
          {!state.connected && <span className="chip warn">offline</span>}
        </div>
        <div className="segmented audience-switch" role="tablist" aria-label="Who's watching">
          {(Object.keys(AUDIENCES) as Audience[]).map((a) => (
            <button key={a} className={audience === a ? "active" : ""} onClick={() => setAudience(a)} title={AUDIENCES[a].blurb}>
              {AUDIENCES[a].icon} {AUDIENCES[a].label}
            </button>
          ))}
        </div>
        <div className="header-right">
          <span className={`ai-badge ${model ? "on" : ""}`} title="Commentary, explanations, replays and answers are written by this model">
            {model ? `AI · ${model}` : "AI offline · templates"}
          </span>
          {voiceAvailable && (
            <button
              className={`voice-toggle ${voiceOn ? "on" : ""}`}
              onClick={() => setVoiceOn((v) => !v)}
              title="Spoken AI commentary (Azure AI Speech neural voice, in your language)"
            >
              {voiceOn ? (speaking ? "🔊 Speaking…" : "🔊 Voice on") : "🔇 Voice off"}
            </button>
          )}
          <button className={`setup-btn ${setupOpen ? "on" : ""}`} onClick={() => setSetupOpen((o) => !o)} aria-expanded={setupOpen}>
            ⚙ Setup
          </button>
        </div>
      </header>
      {setupOpen && (
        <div className="setup-drawer">
          <div className="setup-group">
            <h4>Match</h4>
            <MatchPicker
              matches={matches}
              current={matchId}
              onSelect={setMatchId}
              onCreated={(list, id) => {
                setMatches(list);
                setMatchId(id);
              }}
            />
          </div>
          <div className="setup-group">
            <h4>Analytics plugins</h4>
            <div className="plugin-toggles">
              {state.available.map((p) => (
                <label key={p.name} title={p.description}>
                  <input
                    type="checkbox"
                    checked={state.enabled.includes(p.name)}
                    onChange={(e) =>
                      send({ type: "plugins", enabled: e.target.checked ? [...state.enabled, p.name] : state.enabled.filter((n) => n !== p.name) })
                    }
                  />
                  {p.name}
                </label>
              ))}
            </div>
          </div>
          <div className="setup-group">
            <h4>Commentary style</h4>
            <div className="segmented">
              {(["casual", "analyst"] as const).map((m) => (
                <button key={m} className={persona.mode === m ? "active" : ""} onClick={() => updatePersona({ mode: m })}>
                  {m === "casual" ? "Casual" : "Tactical"}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="toolbar">
        <Controls
          meta={meta}
          persona={persona}
          onPersona={updatePersona}
          paused={state.paused}
          speed={state.speed}
          t={frame?.t ?? 0}
          onControl={(m) => control(m)}
        />
        <div className="segmented view-switch">
          {cfg.views.map((v) => (
            <button key={v} className={view === v ? "active" : ""} onClick={() => setView(v)}>
              {v.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <MomentsBar
        meta={meta}
        moments={moments}
        now={frame?.t ?? 0}
        ended={state.ended}
        busy={busy}
        onExplain={explainMoment}
        onHighlights={highlightsSoFar}
      />
      {state.ended && !program && !busy && moments.length > 0 && !ftDismissed && (
        <div className="ft-prompt">
          <span>
            <b>Full time.</b> The producer can cut the match highlights now.
          </span>
          <button className="highlights-btn" onClick={highlightsSoFar}>
            🎬 Watch match highlights
          </button>
          <button className="ft-close" onClick={() => setFtDismissed(true)} aria-label="Dismiss">
            ✕
          </button>
        </div>
      )}
      {busy && (
        <div className="agent-busy">
          <span className="spinner" /> {busy}
        </div>
      )}
      {program && (
        <ReplayTheater meta={meta} program={program} voice={voiceAvailable && voiceOn} language={persona.language} onClose={closeReplay} />
      )}

      <main>
        {view === "data" && cfg.views.includes("data") && (
          <section className="views data">
            <DataView
              meta={meta}
              frame={frame}
              plugins={state.plugins}
              series={state.series}
              events={state.events}
              feed={state.feed}
              playerKmh={state.playerKmh}
              pitch={
                <>
                  <OverlayLayer meta={meta} cues={state.plugins.overlays?.active ?? []} />
                  <Pitch2D meta={meta} frame={frame} forecast={state.plugins.ball_forecast} speed={state.plugins.speed_metrics} favoritePlayer={persona.favorite_player} />
                </>
              }
            />
          </section>
        )}
        {(view !== "data" || !cfg.views.includes("data")) && (
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
        )}
        <aside>
          <AskPanel answers={state.answers} asking={state.asking} onAsk={ask} persona={persona} model={model} />
          {persona.favorite_player && (
            <PlayerFocus meta={meta} playerId={persona.favorite_player} plugins={state.plugins} narrations={state.narrations} />
          )}
          <CommentaryFeed meta={meta} narrations={state.narrations} persona={persona} model={model} moments={moments} onExplain={explainMoment} />
        </aside>
        <section className={`bottom bottom-${audience}`}>
          <StatsPanel meta={meta} plugins={state.plugins} persona={persona} />
          {audience !== "fan" && <RecapPanel matchId={meta.match_id} persona={persona} />}
          {audience !== "fan" && <AgentOps agents={state.agents} narrations={state.narrations} answers={state.answers} />}
        </section>
      </main>
    </div>
  );
}
