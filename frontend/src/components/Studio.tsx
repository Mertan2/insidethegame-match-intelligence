import { useEffect } from "react";
import type { MatchMeta, Frame, Moment, Narration, Persona, PluginPayloads } from "../types";
import { OverlayLayer } from "./OverlayLayer";
import { Pitch2D } from "./Pitch2D";

const CHAIN = ["stats", "tactics", "narrator", "persona"];

const KICKER: Record<string, string> = {
  goal: "GOAL",
  big_chance: "BIG CHANCE",
  rocket_shot: "SHOT",
  forecast_on_target: "ON TARGET",
  play_by_play: "LIVE",
  fun_fact: "DID YOU KNOW",
  recap: "RECAP",
  half_time_recap: "HALF TIME",
  full_time_recap: "FULL TIME",
};

interface Props {
  meta: MatchMeta;
  frame: Frame | null;
  plugins: PluginPayloads;
  narrations: Narration[];
  persona: Persona;
  moments: Moment[];
  paused: boolean;
  ended: boolean;
  speed: number;
  speaking: boolean;
  voiceOn: boolean;
  voiceAvailable: boolean;
  drill: string[];
  busy: string | null;
  onControl: (msg: { action?: string; speed?: number }) => void;
  onVoice: () => void;
  onExplain: (m: Moment) => void;
  onHighlights: () => void;
  onExit: () => void;
}

/** The key moment a commentary line is about (a goal or chance a few seconds earlier), if any. */
function momentFor(n: Narration | undefined, moments: Moment[]): Moment | undefined {
  if (!n || !["goal", "big_chance", "rocket_shot", "forecast_on_target"].includes(n.kind)) return undefined;
  return moments.find((m) => m.t <= n.t + 1 && n.t - m.t < 6);
}

/**
 * Studio mode: the output as a broadcast or stream would carry it. Full-screen pitch, the score bug,
 * the graphics cues from the overlays plugin, the commentary as a lower-third caption, and a small
 * strip showing which agent wrote the line and how. No dashboard chrome.
 */
export function Studio(props: Props) {
  const { meta, frame, plugins, narrations, persona, moments, paused, ended, speed, speaking, voiceOn, voiceAvailable, drill, busy } = props;
  const latest = narrations[0];
  // The last key moment stays explainable for a while, even once the caption has moved on.
  const recent = narrations.slice(0, 8).map((n) => momentFor(n, moments)).find((m) => m && (frame?.t ?? 0) - m.t < 90);
  const moment = momentFor(latest, moments) ?? recent;
  const clock = frame ? `${Math.floor(frame.t / 60)}:${String(Math.floor(frame.t % 60)).padStart(2, "0")}` : "0:00";
  const team = latest?.team ? meta.teams[latest.team] : null;
  const steps = (latest?.trace ?? []).filter((s) => s.path !== undefined);
  const fav = persona.favorite_player ? meta.players.find((p) => p.id === persona.favorite_player) : null;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") props.onExit();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="studio" role="region" aria-label="Studio output">
      <div className="studio-bar">
        <span className="studio-brand">◆ INSIDE THE GAME · STUDIO</span>
        <span className="studio-bar-gap" />
        <button onClick={() => props.onControl({ action: paused ? "play" : "pause" })} disabled={ended}>
          {paused ? "▶ Play" : "⏸ Pause"}
        </button>
        <select value={speed} onChange={(e) => props.onControl({ speed: Number(e.target.value) })} aria-label="Speed">
          {[1, 2, 4, 8, 16, 32].map((s) => (
            <option key={s} value={s}>
              {s}x
            </option>
          ))}
        </select>
        {voiceAvailable && (
          <button className={`voice-toggle ${voiceOn ? "on" : ""}`} onClick={props.onVoice}>
            {voiceOn ? (speaking ? "🔊 Speaking…" : "🔊 Voice on") : "🔇 Voice off"}
          </button>
        )}
        <button className="highlights-btn" onClick={props.onHighlights} disabled={busy !== null || moments.filter((m) => m.t <= (frame?.t ?? 0)).length === 0}>
          🎬 {ended ? "Match highlights" : "Highlights so far"}
        </button>
        <button className="studio-exit" onClick={props.onExit} title="Back to the dashboard (Esc)">
          ✕ Exit studio
        </button>
      </div>

      <div className="studio-stage">
        <div className="studio-pitch">
          <OverlayLayer meta={meta} cues={plugins.overlays?.active ?? []} />
          <Pitch2D meta={meta} frame={frame} forecast={plugins.ball_forecast} speed={plugins.speed_metrics} favoritePlayer={persona.favorite_player} />
          <div className="studio-bug">
            <span className="studio-bug-team" style={{ background: meta.teams.home.color }}>
              {meta.teams.home.short}
            </span>
            <span className="studio-bug-score">
              {frame?.score.home ?? 0} - {frame?.score.away ?? 0}
            </span>
            <span className="studio-bug-team" style={{ background: meta.teams.away.color }}>
              {meta.teams.away.short}
            </span>
            <span className="studio-bug-clock">{clock}</span>
            {ended ? <span className="studio-bug-ft">FT</span> : !paused && <span className="live-dot">LIVE</span>}
          </div>
          {fav && (
            <div className="studio-follow">
              <span className="studio-follow-num" style={{ background: meta.teams[fav.team].color }}>
                {fav.number}
              </span>
              Following {fav.name}
            </div>
          )}
        </div>
      </div>

      <div className="studio-lower">
        <div className={`studio-caption ${latest?.kind ?? ""}`} key={latest ? `${latest.t}-${latest.kind}` : "none"} style={{ borderColor: team?.color ?? "#8b6cff" }}>
          {latest ? (
            <>
              <div className="studio-caption-head">
                <span className="studio-kicker" style={{ color: team?.color ?? "#ffe65a" }}>
                  {KICKER[latest.kind] ?? latest.kind.replace(/_/g, " ").toUpperCase()}
                </span>
                <span className="studio-clock">{latest.clock}</span>
                {team && <span className="studio-team">{team.name}</span>}
                {moment && (
                  <button className="explain-btn studio-explain" onClick={() => props.onExplain(moment)} disabled={busy !== null}>
                    ▶ Replay & explain {moment.minute}' {moment.kind}
                  </button>
                )}
              </div>
              <p>{latest.text}</p>
            </>
          ) : (
            <p className="muted">The agents are watching. The first line comes at the next key moment.</p>
          )}
        </div>
        <div className="studio-agents" title="How the last line was made: one chip per agent, lit for the path it took">
          <span className="studio-agents-label">AGENT TEAM</span>
          {CHAIN.map((name, i) => {
            const s = steps.find((x) => x.agent === name);
            const down = drill.includes(name);
            return (
              <span key={name} className="studio-agent-wrap">
                {i > 0 && <span className="ops-arrow">→</span>}
                <span className={`studio-agent path-${s?.path ?? "none"} ${s && s.status !== "ok" ? "fallback" : ""} ${down ? "down" : ""}`}>
                  {down ? "⚡ " : ""}
                  {name}
                  {s && s.path !== "skipped" && <small>{s.path === "llm" ? "LLM" : s.path === "deterministic" ? "rules" : s.path}</small>}
                </span>
              </span>
            );
          })}
          {drill.length > 0 && <span className="studio-drill">outage drill · {drill.join(", ")} down · still on air</span>}
        </div>
      </div>
    </div>
  );
}
