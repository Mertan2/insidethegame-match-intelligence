import { useCallback, useEffect, useRef, useState } from "react";
import type { MatchMeta, Moment, Narration, Persona } from "../types";
import { Icon } from "./Icon";

export interface FanCallData {
  moment: Moment;
  ms: number;
  viewers: (Narration & { label: string; persona: Persona })[];
}

const CHAIN = ["stats", "tactics", "narrator", "persona"];

interface Props {
  meta: MatchMeta;
  data: FanCallData;
  voice: boolean;
  onClose: () => void;
}

/**
 * Every fan's call: the same moment narrated for three viewers at once (the scoring side's fan,
 * the other side's fan, a neutral analyst), each by its own agent chain, run in parallel.
 * With voice on, the three calls are read out one after another.
 */
export function FanCall({ meta, data, voice, onClose }: Props) {
  const { moment, viewers } = data;
  const [playing, setPlaying] = useState<number | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const run = useRef(0);
  const scorer = meta.players.find((p) => p.id === moment.player_id);
  const team = meta.teams[moment.team];

  const stop = useCallback(() => {
    run.current += 1;
    audio.current?.pause();
    audio.current = null;
    setPlaying(null);
  }, []);

  const playFrom = useCallback(
    async (start: number, only = false) => {
      stop();
      const id = run.current;
      for (let i = start; i < viewers.length; i++) {
        if (id !== run.current) return;
        const v = viewers[i];
        setPlaying(i);
        try {
          const res = await fetch("/api/tts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: v.text, lang: v.language, kind: "goal" }),
          });
          if (!res.ok || id !== run.current) break;
          const url = URL.createObjectURL(await res.blob());
          const a = new Audio(url);
          audio.current = a;
          await new Promise<void>((resolve) => {
            a.onended = a.onerror = () => resolve();
            a.onpause = () => resolve();
            a.play().catch(() => resolve());
          });
          URL.revokeObjectURL(url);
        } catch {
          // a failed clip is skipped
        }
        if (only) break;
        if (id === run.current) await new Promise((r) => setTimeout(r, 450));
      }
      if (id === run.current) setPlaying(null);
    },
    [viewers, stop],
  );

  useEffect(() => {
    if (voice) void playFrom(0);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="fancall" role="dialog" aria-label="Every fan's call">
      <div className="fancall-top">
        <div className="fancall-title">
          <span className="fancall-kicker">EVERY FAN'S CALL</span>
          <b>
            <span style={{ color: team.color }}>{moment.minute}' {moment.kind.toUpperCase()}</span> · {scorer?.name ?? ""} · {meta.teams.home.short}{" "}
            {moment.score_after.home}-{moment.score_after.away} {meta.teams.away.short}
          </b>
          <span className="muted">
            One moment, three viewers. {viewers.length} agent chains ran in parallel in {(data.ms / 1000).toFixed(1)} s.
          </span>
        </div>
        <div className="fancall-actions">
          {voice && (
            <button onClick={() => (playing === null ? playFrom(0) : stop())}>
              {playing === null ? <><Icon name="voice" /> Play all three</> : <><Icon name="pause" /> Stop</>}
            </button>
          )}
          <button onClick={onClose} aria-label="Close">
            <Icon name="close" />
          </button>
        </div>
      </div>

      <div className="fancall-cards">
        {viewers.map((v, i) => {
          const fav = v.persona.favorite_team ? meta.teams[v.persona.favorite_team] : null;
          const steps = v.trace.filter((s) => s.path !== undefined);
          return (
            <div key={v.label} className={`fancall-card ${playing === i ? "on" : ""}`} style={{ borderTopColor: fav?.color ?? "var(--ai)" }}>
              <div className="fancall-who">
                <span className="fancall-dot" style={{ background: fav?.color ?? "var(--ai)" }} />
                <b>{v.label}</b>
                <span className="muted">{v.persona.mode === "analyst" ? "tactical" : "casual"}</span>
              </div>
              <p className="fancall-text" lang={v.language} dir={v.language === "ar" ? "rtl" : undefined}>
                {v.text}
              </p>
              <div className="fancall-foot">
                <div className="fancall-chain">
                  {CHAIN.map((name) => {
                    const s = [...steps].reverse().find((x) => x.agent === name);
                    return (
                      <span key={name} className={`studio-agent path-${s?.path ?? "none"} ${s && s.status !== "ok" ? "fallback" : ""}`}>
                        {name}
                        {s && <small>{s.path === "llm" ? "LLM" : s.path === "deterministic" ? "rules" : s.path}</small>}
                      </span>
                    );
                  })}
                </div>
                {voice && (
                  <button className="fancall-play" onClick={() => playFrom(i, true)} aria-label={`Play ${v.label}`}>
                    <Icon name={playing === i ? "voice" : "play"} size={14} />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <div className="fancall-note muted">
        Same facts from the stats agent for everyone; the persona agent changes who it is for: club, language, style.
      </div>
    </div>
  );
}
