import { useEffect, useRef, useState } from "react";
import { AgentOps } from "./components/AgentOps";
import { AskPanel } from "./components/AskPanel";
import { Broadcast } from "./components/Broadcast";
import { CommentaryFeed } from "./components/CommentaryFeed";
import { DataView } from "./components/DataView";
import { FanCall, type FanCallData } from "./components/FanCall";
import { BrandMark, Icon } from "./components/Icon";
import { Kickoff } from "./components/Kickoff";
import { MatchPicker, type MatchSummary } from "./components/MatchPicker";
import { MetricFocus } from "./components/MetricFocus";
import { MomentsBar } from "./components/MomentsBar";
import { OverlayLayer } from "./components/OverlayLayer";
import { Pitch2D } from "./components/Pitch2D";
import { PlayerFocus } from "./components/PlayerFocus";
import { RecapPanel } from "./components/RecapPanel";
import { ReplayTheater } from "./components/ReplayTheater";
import { StatsPanel } from "./components/StatsPanel";
import { Studio } from "./components/Studio";
import { AUDIENCES, loadAudience, saveAudience, type Audience } from "./audience";
import { FOCUS_METRICS, type FocusMetric, type Moment, type Persona, type Program, type ReplayItem, type Side, type TraceStep } from "./types";
import { useLiveMatch } from "./useLiveMatch";
import { useVoice } from "./useVoice";

const START_AUDIENCE = loadAudience();
const DEFAULT_PERSONA: Persona = { mode: AUDIENCES[START_AUDIENCE].mode, language: "en", favorite_team: null, favorite_player: null };

const LANGUAGES = [
  ["en", "English"],
  ["es", "Español"],
  ["tr", "Türkçe"],
  ["fr", "Français"],
  ["de", "Deutsch"],
  ["pt", "Português"],
  ["ar", "العربية"],
];

type Screen = "watch" | "crew" | "data";

export default function App() {
  const [matchId, setMatchId] = useState<string | null>(null);
  const [persona, setPersona] = useState<Persona>(DEFAULT_PERSONA);
  const [audience, setAudienceState] = useState<Audience>(START_AUDIENCE);
  const [screen, setScreen] = useState<Screen>("watch");
  const [view, setView] = useState<"2d" | "3d">("2d");
  const [setupOpen, setSetupOpen] = useState(false);
  const [studio, setStudio] = useState(false);
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
  const [fanCall, setFanCall] = useState<FanCallData | null>(null);
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
  const { speak, speaking, stop: stopVoice, drain: drainVoice } = useVoice(voiceOn && program === null && fanCall === null);
  const latestNarration = state.narrations[0];
  const latestAnswer = state.answers[0];
  // Speak each new AI commentary line and each answer as it arrives.
  useEffect(() => {
    // Above 2x the play outruns any voice: only key moments are spoken then.
    const key = ["goal", "big_chance", "half_time_recap", "full_time_recap"].includes(latestNarration?.kind ?? "");
    // A line still being written when the match was paused arrives late: stay quiet.
    if (latestNarration && !state.paused && (state.speed <= 2 || key)) speak(latestNarration.text, latestNarration.language, latestNarration.kind);
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
  const openFanCall = async (m: Moment) => {
    setBusy("Three agent teams are writing the same moment for three fans…");
    resumeAfterReplay.current = (!state.paused || justResumed.current) && !state.ended;
    send({ type: "control", action: "pause" });
    try {
      const res = await fetch(`/api/matches/${matchId}/moments/${m.id}/viewers`);
      if (!res.ok) throw new Error(String(res.status));
      setFanCall((await res.json()) as FanCallData);
    } catch {
      if (resumeAfterReplay.current) send({ type: "control", action: "play" });
    } finally {
      setBusy(null);
    }
  };
  const closeFanCall = () => {
    setFanCall(null);
    if (resumeAfterReplay.current) {
      send({ type: "control", action: "play" });
      justResumed.current = true;
    }
  };
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
    updatePersona({ mode: AUDIENCES[a].mode });
  };

  const control = (msg: { action?: string; t?: number; speed?: number }) => {
    if (msg.action === "seek") {
      clearNarrations();
      stopVoice(); // the play has jumped: cut the line
    }
    if (msg.action === "pause") drainVoice(); // finish the sentence, then quiet
    send({ type: "control", ...msg });
  };

  const { meta, frame } = state;
  if (!meta) return <div className="loading">{matchId ? "Connecting to live feed…" : "Loading match…"}</div>;

  const clock = frame ? `${Math.floor(frame.t / 60)}:${String(Math.floor(frame.t % 60)).padStart(2, "0")}` : "0:00";
  const live = !state.ended && !state.paused;
  const t = frame?.t ?? 0;
  const total = meta.minutes * 60;

  const broadcastProps = {
    meta,
    frame,
    plugins: state.plugins,
    narrations: state.narrations,
    persona,
    moments,
    paused: state.paused,
    ended: state.ended,
    drill: state.drill,
    busy,
    view,
    onExplain: explainMoment,
    onFanCall: openFanCall,
  };

  const transport = (
    <div className="transport">
      <button className="transport-play" onClick={() => control({ action: state.paused ? "play" : "pause" })} disabled={state.ended}>
        {state.paused ? <><Icon name="play" /> Play</> : <><Icon name="pause" /> Pause</>}
      </button>
      <select value={state.speed} onChange={(e) => control({ speed: Number(e.target.value) })} aria-label="Speed">
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
        onChange={(e) => control({ action: "seek", t: Number(e.target.value) })}
        className="seek"
        aria-label="Match clock"
      />
      <span className="muted seek-label">
        {Math.floor(t / 60)}' / {meta.minutes}'
      </span>
      <span className="transport-gap" />
      <div className="segmented view-switch">
        {(["2d", "3d"] as const).map((v) => (
          <button key={v} className={view === v ? "active" : ""} onClick={() => setView(v)}>
            {v.toUpperCase()}
          </button>
        ))}
      </div>
      <button className="studio-btn" onClick={() => setStudio(true)} title="Full-screen broadcast output (Esc to come back)">
        <Icon name="studio" /> Studio
      </button>
    </div>
  );

  return (
    <div className={`app audience-${audience} screen-${screen}`}>
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
          <BrandMark /> Inside the Game
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
        <nav className="nav" aria-label="Screens">
          {(
            [
              ["watch", "Watch", "The broadcast, personalised for you"],
              ["crew", "Crew", "The agent team at work: handoffs, traces, outage drill"],
              ["data", "Data", "The raw feed, live metrics and tracking"],
            ] as [Screen, string, string][]
          ).map(([s, label, title]) => (
            <button key={s} className={screen === s ? "active" : ""} onClick={() => setScreen(s)} title={title}>
              {label}
            </button>
          ))}
        </nav>
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
              <Icon name={voiceOn ? "voice" : "voiceOff"} /> {voiceOn ? (speaking ? "Speaking…" : "Voice on") : "Voice off"}
            </button>
          )}
          <button className={`setup-btn ${setupOpen ? "on" : ""}`} onClick={() => setSetupOpen((o) => !o)} aria-expanded={setupOpen} title="Match, analytics plugins, commentary style">
            <Icon name="settings" /> Setup
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

      {state.ended && !program && !busy && moments.length > 0 && !ftDismissed && (
        <div className="ft-prompt">
          <span>
            <b>Full time.</b> The producer can cut the match highlights now.
          </span>
          <button className="highlights-btn" onClick={highlightsSoFar}>
            <Icon name="film" /> Watch match highlights
          </button>
          <button className="ft-close" onClick={() => setFtDismissed(true)} aria-label="Dismiss">
            <Icon name="close" />
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
      {fanCall && <FanCall meta={meta} data={fanCall} voice={voiceAvailable && voiceOn} onClose={closeFanCall} />}
      {studio && kickedOff && (
        <Studio
          {...broadcastProps}
          speed={state.speed}
          speaking={speaking !== null}
          voiceOn={voiceOn}
          voiceAvailable={voiceAvailable}
          onControl={control}
          onVoice={() => setVoiceOn((v) => !v)}
          onHighlights={highlightsSoFar}
          onExit={() => setStudio(false)}
        />
      )}

      {screen === "watch" && (
        <main className="watch">
          <section className="watch-stage">
            <Broadcast {...broadcastProps} />
            {transport}
            <MomentsBar meta={meta} moments={moments} now={t} ended={state.ended} busy={busy} onExplain={explainMoment} onHighlights={highlightsSoFar} />
          </section>
          <aside className="rail">
            <div className="panel you">
              <h3>
                You
                <span className="ops-sum">{AUDIENCES[audience].blurb}</span>
              </h3>
              <div className="segmented audience-switch" role="tablist" aria-label="Who's watching">
                {(Object.keys(AUDIENCES) as Audience[]).map((a) => (
                  <button key={a} className={audience === a ? "active" : ""} onClick={() => setAudience(a)} title={AUDIENCES[a].blurb}>
                    <Icon name={AUDIENCES[a].icon} /> {AUDIENCES[a].label}
                  </button>
                ))}
              </div>
              <div className="you-grid">
                <label>
                  <span>Language</span>
                  <select value={persona.language} onChange={(e) => updatePersona({ language: e.target.value })}>
                    {LANGUAGES.map(([code, label]) => (
                      <option key={code} value={code}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Your club</span>
                  <select value={persona.favorite_team ?? ""} onChange={(e) => updatePersona({ favorite_team: (e.target.value || null) as Side | null })}>
                    <option value="">No favourite club</option>
                    <option value="home">{meta.teams.home.name}</option>
                    <option value="away">{meta.teams.away.name}</option>
                  </select>
                </label>
                <label>
                  <span>Your player</span>
                  <select value={persona.favorite_player ?? ""} onChange={(e) => updatePersona({ favorite_player: e.target.value || null })}>
                    <option value="">Follow a player…</option>
                    {meta.players.map((p) => (
                      <option key={p.id} value={p.id}>
                        {meta.teams[p.team].short} #{p.number} {p.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Your metric</span>
                  <select
                    value={persona.focus_metric ?? ""}
                    onChange={(e) => updatePersona({ focus_metric: (e.target.value || null) as FocusMetric | null })}
                    title="The one metric you care about: it stays on screen and in the commentary"
                  >
                    <option value="">Metric I care about…</option>
                    {FOCUS_METRICS.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </div>
            {persona.focus_metric && <MetricFocus meta={meta} metric={persona.focus_metric} plugins={state.plugins} favoritePlayer={persona.favorite_player} />}
            {persona.favorite_player && (
              <PlayerFocus meta={meta} playerId={persona.favorite_player} plugins={state.plugins} narrations={state.narrations} />
            )}
            <AskPanel answers={state.answers} asking={state.asking} onAsk={ask} persona={persona} model={model} />
            <CommentaryFeed meta={meta} narrations={state.narrations} persona={{ ...persona, mode: "casual" }} model={model} moments={moments} onExplain={explainMoment} />
          </aside>
        </main>
      )}

      {screen === "crew" && (
        <main className="crew">
          <section className="crew-main">
            <AgentOps
              agents={state.agents}
              narrations={state.narrations}
              answers={state.answers}
              drill={state.drill}
              onDrill={(agents) => send({ type: "drill", agents })}
            />
            <div className="panel a2a">
              <h3>
                A2A: this analyst as a service
                <span className="ops-sum">Agent Framework A2AExecutor</span>
              </h3>
              <p className="muted small">
                Other agents call the same team over the Agent2Agent protocol: ask a question, explain a moment, fetch the highlights package.
              </p>
              <div className="a2a-rows">
                <a href="/.well-known/agent-card.json" target="_blank" rel="noreferrer">
                  <code>GET /.well-known/agent-card.json</code> agent card
                </a>
                <span>
                  <code>POST /a2a</code> JSON-RPC: "explain the goal in the 8th minute", "highlights", "who is tiring?"
                </span>
                <span>
                  <code>GET /api/matches/{"{id}"}/overlays</code> timed, machine-readable graphics cues
                </span>
              </div>
            </div>
            <StatsPanel meta={meta} plugins={state.plugins} persona={persona} />
            <RecapPanel matchId={meta.match_id} persona={persona} />
          </section>
          <aside className="rail">
            <CommentaryFeed meta={meta} narrations={state.narrations} persona={{ ...persona, mode: "analyst" }} model={model} moments={moments} onExplain={explainMoment} />
          </aside>
        </main>
      )}

      {screen === "data" && (
        <main className="data-screen">
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
          {transport}
        </main>
      )}
    </div>
  );
}
