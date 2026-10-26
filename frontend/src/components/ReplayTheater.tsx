import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Beat, Frame, MatchMeta, MomentStep, Program, ReplayFrame, ReplayItem } from "../types";
import { Pitch2D } from "./Pitch2D";
import { Icon } from "./Icon";

const L = 105;
const GOAL_HALF = 3.66;
const CARD_MS = 1900;
const SLOW_BEFORE_SHOT = 1.3; // seconds of slow motion around the shot
const SLOW_AFTER_SHOT = 0.9;
const REEL_TAIL_S = 2.4; // highlights cut away soon after the shot
const RECENT_PASSES = 4; // older passes fade so the move stays readable

type Segment =
  | { kind: "say"; card: "intro" | "outro"; text: string }
  | { kind: "card"; item: number }
  | { kind: "clip"; item: number }
  | { kind: "verdict"; item: number };

interface Props {
  meta: MatchMeta;
  program: Program;
  voice: boolean;
  language: string;
  onClose: () => void;
}

/** Linear interpolation between the 10 Hz tracking frames, so the replay moves smoothly at 60 fps. */
function frameAt(frames: ReplayFrame[], t: number): Frame {
  const t0 = frames[0].t;
  const pos = Math.max(0, Math.min(frames.length - 1.001, (t - t0) * 10));
  const i = Math.floor(pos);
  const a = frames[i];
  const b = frames[Math.min(i + 1, frames.length - 1)];
  const k = pos - i;
  const lerp = (u: number, v: number) => u + (v - u) * k;
  const bp = new Map(b.players.map(([id, x, y]) => [id, [x, y]]));
  return {
    f: i,
    t,
    ball: [lerp(a.ball[0], b.ball[0]), lerp(a.ball[1], b.ball[1]), lerp(a.ball[2], b.ball[2])],
    players: a.players.map(([id, x, y]) => {
      const n = bp.get(id) ?? [x, y];
      return [id, lerp(x, n[0]), lerp(y, n[1])] as [string, number, number];
    }),
    owner: k < 0.5 ? a.owner : b.owner,
    score: a.score,
  };
}

/** Text-to-speech for one line; resolves when it has finished playing (or straight away when it fails). */
function useNarrator(voice: boolean, language: string) {
  const cache = useRef(new Map<string, Promise<string | null>>());
  const audio = useRef<HTMLAudioElement | null>(null);
  const cut = useRef<(() => void) | null>(null);

  const load = useCallback(
    (text: string) => {
      if (!voice || !text) return Promise.resolve(null);
      if (!cache.current.has(text)) {
        cache.current.set(
          text,
          fetch("/api/tts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text, lang: language, kind: "analysis" }),
          })
            .then((r) => (r.ok ? r.blob() : null))
            .then((b) => (b ? URL.createObjectURL(b) : null))
            .catch(() => null),
        );
      }
      return cache.current.get(text)!;
    },
    [voice, language],
  );

  /** Speak a line; without voice, hold long enough to read it. */
  const say = useCallback(
    async (text: string, minMs = 0) => {
      const started = performance.now();
      const url = await load(text);
      await new Promise<void>((resolve) => {
        cut.current = resolve;
        if (url) {
          const a = new Audio(url);
          audio.current = a;
          a.onended = a.onerror = () => resolve();
          a.play().catch(() => setTimeout(resolve, readingMs(text)));
        } else {
          setTimeout(resolve, readingMs(text));
        }
      });
      cut.current = null;
      const left = minMs - (performance.now() - started);
      if (left > 0) await new Promise((r) => setTimeout(r, left));
    },
    [load],
  );

  const stop = useCallback(() => {
    audio.current?.pause();
    cut.current?.();
  }, []);

  useEffect(() => () => {
    audio.current?.pause();
    for (const p of cache.current.values()) void p.then((u) => u && URL.revokeObjectURL(u));
  }, []);

  return { load, say, stop };
}

function readingMs(text: string) {
  return Math.max(1600, text.split(/\s+/).length * 330);
}

/**
 * The replay theatre: plays tracking for a moment (or a whole highlights package) on the pitch,
 * freezes on each step the explainer agent wrote a beat for, draws it like a TV telestrator
 * (the regain, passes, the key pass, the shot, pressure and the shooting window) and says the
 * beat out loud. Captions and voice come from the agents; every drawing comes from tracking.
 */
export function ReplayTheater({ meta, program, voice, language, onClose }: Props) {
  const [seg, setSeg] = useState(0);
  const [t, setT] = useState(0);
  const [beat, setBeat] = useState<Beat | null>(null);
  const [paused, setPaused] = useState(false);
  const pausedRef = useRef(false);
  const skipRef = useRef(false);
  const { load, say, stop } = useNarrator(voice, language);
  const names = useMemo(() => new Map(meta.players.map((p) => [p.id, p])), [meta]);

  const segments = useMemo<Segment[]>(() => {
    const out: Segment[] = [];
    if (program.intro) out.push({ kind: "say", card: "intro", text: program.intro });
    program.items.forEach((_, i) => {
      if (program.kind === "reel") out.push({ kind: "card", item: i });
      out.push({ kind: "clip", item: i });
      if (program.kind === "explain" && program.items[i].verdict) out.push({ kind: "verdict", item: i });
    });
    if (program.outro) out.push({ kind: "say", card: "outro", text: program.outro });
    return out;
  }, [program]);

  // Ask for every spoken line up front, so voice is ready when the replay reaches it.
  useEffect(() => {
    const lines = [program.intro, ...program.items.flatMap((i) => [...i.beats.map((b) => b.text), i.verdict]), program.outro];
    lines.forEach((l) => l && void load(l));
  }, [program, load]);

  useEffect(() => {
    let cancelled = false;
    const waitWhilePaused = async () => {
      while (pausedRef.current && !cancelled && !skipRef.current) await new Promise((r) => setTimeout(r, 100));
    };
    const playClip = async (item: ReplayItem) => {
      const m = item.moment;
      const start = program.kind === "reel" ? m.clip_start : m.start;
      const beats = item.beats.filter((b) => b.t >= start - 0.01).sort((a, b) => a.t - b.t);
      const end = program.kind === "reel" ? Math.min(m.end, m.t + REEL_TAIL_S) : m.end;
      let next = 0;
      let now = start;
      setT(now);
      setBeat(null);
      let last = performance.now();
      while (!cancelled && !skipRef.current && now < end) {
        await new Promise((r) => setTimeout(r, 30)); // timer, not rAF: keeps time when the tab is throttled
        await waitWhilePaused();
        const tick = performance.now();
        const dt = Math.min(0.25, (tick - last) / 1000);
        last = tick;
        const slow = now > m.t - SLOW_BEFORE_SHOT && now < m.t + SLOW_AFTER_SHOT;
        now += dt * (slow ? 0.45 : 1);
        if (next < beats.length && now >= beats[next].t) {
          now = beats[next].t;
          setT(now);
          setBeat(beats[next]);
          await say(beats[next].text, 900); // freeze frame while the analyst talks
          next += 1;
          last = performance.now();
          continue;
        }
        setT(now);
      }
    };
    (async () => {
      for (let i = 0; i < segments.length && !cancelled; i++) {
        skipRef.current = false;
        setSeg(i);
        const s = segments[i];
        if (s.kind === "say") await say(s.text, 1800);
        else if (s.kind === "card") await new Promise((r) => setTimeout(r, CARD_MS));
        else if (s.kind === "clip") await playClip(program.items[s.item]);
        else if (s.kind === "verdict") await say(program.items[s.item].verdict, 1500);
        await waitWhilePaused();
      }
      if (!cancelled) setSeg(segments.length);
    })();
    return () => {
      cancelled = true;
      stop();
    };
  }, [segments, program, say, stop]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === " ") {
        e.preventDefault();
        togglePause();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const togglePause = () => {
    pausedRef.current = !pausedRef.current;
    setPaused(pausedRef.current);
  };
  const skip = () => {
    skipRef.current = true;
    stop();
  };

  const done = seg >= segments.length;
  const current = segments[Math.min(seg, segments.length - 1)];
  const itemIndex = current && "item" in current ? current.item : current?.kind === "say" && current.card === "outro" ? program.items.length - 1 : 0;
  const item = program.items[itemIndex];
  const frame = item ? frameAt(item.frames, current?.kind === "card" ? (program.kind === "reel" ? item.moment.clip_start : item.moment.start) : t) : null;
  const showCard = current?.kind === "card" || current?.kind === "say";
  const caption = current?.kind === "verdict" ? item.verdict : current?.kind === "clip" ? beat?.text : null;
  const llmSteps = program.trace.filter((s) => s.path === "llm").length;
  const agentSteps = program.trace.filter((s) => s.path).length;
  const title = program.kind === "reel" ? "AI highlights" : "Explain this moment";

  return (
    <div className="theater" role="dialog" aria-label={title}>
      <div className="theater-top">
        <div className="theater-title">
          <span className="theater-kicker"><Icon name="film" size={13} /> {title}</span>
          <b>
            {meta.teams.home.name} {item?.moment.score_after.home ?? ""}–{item?.moment.score_after.away ?? ""} {meta.teams.away.name}
          </b>
        </div>
        <div className="theater-agents" title="Agent steps that produced this replay">
          {program.kind === "reel" ? (
            <>
              <span className="chip ai">producer</span> → <span className="chip ai">{program.items.length}× explainer in parallel</span> →{" "}
              <span className="chip ai">producer</span>
            </>
          ) : (
            <span className="chip ai">explainer</span>
          )}
          <span className="muted">
            {" "}
            {llmSteps}/{agentSteps} LLM
          </span>
        </div>
        <div className="theater-actions">
          <button onClick={togglePause}>{paused ? <><Icon name="play" /> Play</> : <><Icon name="pause" /> Pause</>}</button>
          {program.items.length > 1 && <button onClick={skip}><Icon name="next" /> Next</button>}
          <button onClick={onClose} aria-label="Close replay"><Icon name="close" /></button>
        </div>
      </div>

      <div className="theater-stage">
        <div className="theater-pitch">
          {item && frame && (
            <>
              <Pitch2D meta={meta} frame={frame} favoritePlayer={null} />
              <Telestrator meta={meta} item={item} from={program.kind === "reel" ? item.moment.clip_start : item.moment.start} t={current?.kind === "card" ? -1 : t} beat={current?.kind === "verdict" ? null : beat} final={current?.kind === "verdict" || current?.kind === "say"} />
            </>
          )}
          {showCard && current && (
            <div className={`theater-card ${current.kind === "say" ? "wide" : ""}`}>
              {current.kind === "card" && item && <ClipCard meta={meta} item={item} index={itemIndex} total={program.items.length} names={names} />}
              {current.kind === "say" && (
                <>
                  <div className="theater-card-kicker">{current.card === "intro" ? "Highlights" : program.items.length ? "Final word" : ""}</div>
                  <p>{current.text}</p>
                </>
              )}
            </div>
          )}
          {caption && (
            <div className={`theater-caption ${current?.kind === "verdict" ? "verdict" : ""}`} key={caption}>
              {item && current?.kind === "clip" && <div className="theater-caption-head">{item.headline}</div>}
              {caption}
            </div>
          )}
          {done && (
            <div className="theater-card wide">
              <p>That's the package.</p>
              <button className="kickoff-go" onClick={onClose}>
                Back to live
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="theater-progress">
        {program.items.map((it, i) => (
          <span key={it.moment.id} className={`dot ${it.moment.kind} ${i === itemIndex ? "on" : i < itemIndex ? "past" : ""}`}>
            {it.moment.minute}' <Icon name={it.moment.kind === "goal" ? "goal" : it.moment.kind === "save" ? "save" : "shot"} size={12} />
          </span>
        ))}
      </div>
    </div>
  );
}

function ClipCard({ meta, item, index, total, names }: { meta: MatchMeta; item: ReplayItem; index: number; total: number; names: Map<string, { name: string }> }) {
  const m = item.moment;
  const team = meta.teams[m.team];
  const label = m.kind === "goal" ? "GOAL" : m.kind === "save" ? "SAVED" : "CHANCE";
  return (
    <>
      <div className="theater-card-kicker">
        Clip {index + 1} of {total} · {m.minute}'
      </div>
      <div className={`theater-card-label ${m.kind}`}>{label}</div>
      <div className="theater-card-player" style={{ color: team.color }}>
        {names.get(m.player_id)?.name} · {team.short}
      </div>
      <div className="muted">
        {meta.teams.home.short} {m.score_after.home}–{m.score_after.away} {meta.teams.away.short} · xG {m.xg.toFixed(2)} · {m.passes}-pass move
      </div>
    </>
  );
}

/** Annotation layer over the pitch, drawn from the moment's steps up to replay time t. */
function Telestrator({ meta, item, from, t, beat, final }: { meta: MatchMeta; item: ReplayItem; from: number; t: number; beat: Beat | null; final: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const names = useMemo(() => new Map(meta.players.map((p) => [p.id, p])), [meta]);

  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth;
    const h = c.clientHeight;
    if (c.width !== Math.round(w * dpr)) {
      c.width = Math.round(w * dpr);
      c.height = Math.round(h * dpr);
    }
    const ctx = c.getContext("2d")!;
    ctx.clearRect(0, 0, c.width, c.height);
    if (t < 0) return;
    const s = (w / L) * dpr;
    const X = (x: number) => x * s;
    const Y = (y: number) => y * s;
    const m = item.moment;
    const color = meta.teams[m.team].color;
    const steps = m.steps.filter((st) => st.t >= from - 0.01 || st.type === "shot");
    const shot = steps[steps.length - 1];
    const shown = steps.filter((st) => st.type === "pass" && (final || st.t <= t));
    const recent = new Set(shown.slice(-RECENT_PASSES));
    const beatStep = beat ? steps.find((st) => Math.abs(st.t - beat.t) < 0.01 && st.type === beat.type) : null;
    const label = (text: string, x: number, y: number, fg = "#0a0f17", bg = "#ffe65a") => {
      ctx.font = `600 ${1.55 * s}px system-ui`;
      const tw = ctx.measureText(text).width + 10 * dpr;
      const lh = 2.3 * s;
      const lx = Math.max(2, Math.min(c.width - tw - 2, X(x) - tw / 2));
      const ly = Math.max(2, Y(y) - lh - 1.6 * s);
      ctx.fillStyle = bg;
      ctx.beginPath();
      ctx.roundRect(lx, ly, tw, lh, 4 * dpr);
      ctx.fill();
      ctx.fillStyle = fg;
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(text, lx + 5 * dpr, ly + lh / 2);
    };
    const arrow = (x0: number, y0: number, x1: number, y1: number, k: number, stroke: string, width: number, dashed = false) => {
      const xe = x0 + (x1 - x0) * k;
      const ye = y0 + (y1 - y0) * k;
      ctx.strokeStyle = stroke;
      ctx.fillStyle = stroke;
      ctx.lineWidth = width * dpr;
      ctx.setLineDash(dashed ? [5 * dpr, 4 * dpr] : []);
      ctx.beginPath();
      ctx.moveTo(X(x0), Y(y0));
      ctx.lineTo(X(xe), Y(ye));
      ctx.stroke();
      ctx.setLineDash([]);
      if (k > 0.2) {
        const ang = Math.atan2(Y(ye) - Y(y0), X(xe) - X(x0));
        const hl = (6 + width * 2) * dpr;
        ctx.beginPath();
        ctx.moveTo(X(xe), Y(ye));
        ctx.lineTo(X(xe) - hl * Math.cos(ang - 0.45), Y(ye) - hl * Math.sin(ang - 0.45));
        ctx.lineTo(X(xe) - hl * Math.cos(ang + 0.45), Y(ye) - hl * Math.sin(ang + 0.45));
        ctx.closePath();
        ctx.fill();
      }
    };
    const ring = (x: number, y: number, r: number, stroke: string, width = 2) => {
      ctx.strokeStyle = stroke;
      ctx.lineWidth = width * dpr;
      ctx.beginPath();
      ctx.arc(X(x), Y(y), r * s, 0, Math.PI * 2);
      ctx.stroke();
    };

    // Shooting window: ball to both posts, shown as the shot approaches.
    const gx = shot.end_x !== undefined && (shot.end_x < 1 || shot.end_x > L - 1) ? (shot.end_x < 1 ? 0 : L) : m.team === "home" ? L : 0;
    if (t >= shot.t - 1.2 || final) {
      ctx.fillStyle = "rgba(255,255,255,0.10)";
      ctx.beginPath();
      ctx.moveTo(X(shot.x), Y(shot.y));
      ctx.lineTo(X(gx), Y(34 - GOAL_HALF));
      ctx.lineTo(X(gx), Y(34 + GOAL_HALF));
      ctx.closePath();
      ctx.fill();
    }

    for (const st of steps) {
      if (st.t > t && !final) break;
      const k = final ? 1 : Math.min(1, (t - st.t) / 0.6 + 0.05);
      const focus = beatStep === st;
      if (st.type === "regain") {
        ring(st.x, st.y, 2.2, focus ? "#ffe65a" : "rgba(255,255,255,0.8)", focus ? 3 : 2);
        if (focus || final) label(`WON IT · ${names.get(st.player_id ?? "")?.name ?? ""}`, st.x, st.y, "#0a0f17", "#ffffff");
      } else if (st.type === "pass") {
        const key = Boolean(st.key_pass);
        ctx.globalAlpha = key || focus || recent.has(st) ? 1 : 0.3;
        arrow(st.x, st.y, st.end_x ?? st.x, st.end_y ?? st.y, k, key ? "#ffe65a" : focus ? "#ffffff" : "rgba(255,255,255,0.6)", key || focus ? 3 : 1.6, !key && !focus);
        ctx.fillStyle = key ? "#ffe65a" : color;
        ctx.beginPath();
        ctx.arc(X(st.x), Y(st.y), 0.55 * s, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1;
        if (focus) {
          const extra = st.bypassed ? ` · ${st.bypassed} OUT` : st.progress_m && st.progress_m > 8 ? ` · +${Math.round(st.progress_m)} m` : "";
          label(`${key ? "KEY PASS" : "PASS"}${extra}`, (st.x + (st.end_x ?? st.x)) / 2, (st.y + (st.end_y ?? st.y)) / 2);
        }
      } else {
        drawShot(st, focus || final);
      }
    }

    function drawShot(st: MomentStep, focus: boolean) {
      const k = final ? 1 : Math.min(1, (t - st.t) / 0.35 + 0.05);
      const col = st.outcome === "goal" ? "#3dff8f" : st.outcome === "saved" ? "#7cc7ff" : "#ff6b6b";
      if (st.nearest_defender_m != null) {
        ring(st.x, st.y, Math.max(1.2, st.nearest_defender_m), "rgba(255,107,107,0.9)", 2);
      }
      for (const id of st.blocker_ids ?? []) {
        const p = item.frames[0] && frameAt(item.frames, st.t).players.find((q) => q[0] === id);
        if (p) ring(p[1], p[2], 1.8, "rgba(255,107,107,0.7)", 1.5);
      }
      arrow(st.x, st.y, st.end_x ?? gx, st.end_y ?? 34, k, col, 3.2);
      if (focus) {
        const gap = st.nearest_defender_m != null ? ` · ${st.nearest_defender_m} m space` : "";
        label(`SHOT · xG ${(st.xg ?? 0).toFixed(2)}${gap}`, st.x, st.y, "#0a0f17", col);
      }
    }
  }, [item, from, t, beat, final, meta, names]);

  return <canvas ref={ref} className="telestrator" />;
}
