import type { Frame, MatchMeta, Moment, Narration, Persona, PluginPayloads } from "../types";
import { Ball3D } from "./Ball3D";
import { Icon } from "./Icon";
import { OverlayLayer } from "./OverlayLayer";
import { Pitch2D } from "./Pitch2D";

const CHAIN = ["stats", "tactics", "narrator", "persona", "checker"];

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

export interface BroadcastProps {
  meta: MatchMeta;
  frame: Frame | null;
  plugins: PluginPayloads;
  narrations: Narration[];
  persona: Persona;
  moments: Moment[];
  paused: boolean;
  ended: boolean;
  drill: string[];
  busy: string | null;
  view: "2d" | "3d";
  onExplain: (m: Moment) => void;
  onFanCall?: (m: Moment) => void;
}

/** The key moment a commentary line is about (a goal or chance a few seconds earlier), if any. */
function momentFor(n: Narration | undefined, moments: Moment[]): Moment | undefined {
  if (!n || !["goal", "big_chance", "rocket_shot", "forecast_on_target"].includes(n.kind)) return undefined;
  return moments.find((m) => m.t <= n.t + 1 && n.t - m.t < 6);
}

/**
 * The broadcast output: the pitch with the graphics cues, the score bug, the commentary as a
 * lower-third caption, and a strip showing which agent wrote the line and by which path.
 * Used in the Watch screen and, full screen, in Studio mode.
 */
export function Broadcast({ meta, frame, plugins, narrations, persona, moments, paused, ended, drill, busy, view, onExplain, onFanCall }: BroadcastProps) {
  const latest = narrations[0];
  // The last key moment stays explainable for a while, even once the caption has moved on.
  const recent = narrations.slice(0, 8).map((n) => momentFor(n, moments)).find((m) => m && (frame?.t ?? 0) - m.t < 90);
  const moment = momentFor(latest, moments) ?? recent;
  const clock = frame ? `${Math.floor(frame.t / 60)}:${String(Math.floor(frame.t % 60)).padStart(2, "0")}` : "0:00";
  const team = latest?.team ? meta.teams[latest.team] : null;
  const steps = (latest?.trace ?? []).filter((s) => s.path !== undefined);
  const fav = persona.favorite_player ? meta.players.find((p) => p.id === persona.favorite_player) : null;

  return (
    <div className="bc">
      <div className="studio-stage">
        <div className="studio-pitch">
          <OverlayLayer meta={meta} cues={plugins.overlays?.active ?? []} />
          {view === "3d" ? (
            <div className="bc-3d">
              <Ball3D meta={meta} frame={frame} forecast={plugins.ball_forecast} focusId={persona.favorite_player} />
            </div>
          ) : (
            <Pitch2D meta={meta} frame={frame} forecast={plugins.ball_forecast} speed={plugins.speed_metrics} favoritePlayer={persona.favorite_player} />
          )}
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
                  <span className="caption-actions">
                    {onFanCall && moment.kind === "goal" && (
                      <button className="explain-btn fancall-btn" onClick={() => onFanCall(moment)} disabled={busy !== null}>
                        <Icon name="voice" size={12} /> Every fan's call
                      </button>
                    )}
                    <button className="explain-btn studio-explain" onClick={() => onExplain(moment)} disabled={busy !== null}>
                      <Icon name="play" size={12} /> Replay & explain {moment.minute}' {moment.kind}
                    </button>
                  </span>
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
            const s = [...steps].reverse().find((x) => x.agent === name); // the run step, appended last
            const down = drill.includes(name);
            return (
              <span key={name} className="studio-agent-wrap">
                {i > 0 && <span className="ops-arrow">→</span>}
                <span className={`studio-agent path-${s?.path ?? "none"} ${s && s.status !== "ok" ? "fallback" : ""} ${down ? "down" : ""}`}>
                  {down && <Icon name="bolt" size={11} />}
                  {name}
                  {s && s.path !== "skipped" && (
                    <small>
                      {name === "checker" && latest?.check
                        ? latest.check.grounded
                          ? "✓ facts"
                          : `${latest.check.flagged.length} flagged`
                        : s.path === "llm"
                          ? "LLM"
                          : s.path === "deterministic"
                            ? "rules"
                            : s.path}
                    </small>
                  )}
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
