import { useCallback, useEffect, useRef, useState } from "react";

interface Line {
  text: string;
  lang: string;
  kind?: string;
  queuedAt: number;
}

/** Spoken before anything else, and never dropped as stale. */
const PRIORITY = new Set(["goal", "answer", "big_chance", "half_time_recap", "full_time_recap"]);
const MAX_WAITING = 1; // at most one routine line waits: commentary must stay with the play
const STALE_MS = 4000; // a routine line that waited longer than this describes play that has moved on
const MAX_SPOKEN_WORDS = 32;

/** Whole sentences up to about MAX_SPOKEN_WORDS words: the screen shows the full line, the voice keeps it short. */
export function spokenVersion(text: string): string {
  const sentences = text.match(/[^.!?؟。]+[.!?؟。]+["'”’)]*\s*|[^.!?؟。]+$/g) ?? [text];
  let out = "";
  for (const s of sentences) {
    const next = (out + s).trim();
    if (out && next.split(/\s+/).length > MAX_SPOKEN_WORDS) break;
    out = next + " ";
  }
  return out.trim();
}

/**
 * Spoken commentary: each line is synthesised by the backend (Azure AI Speech) and played in order.
 * Goals, recaps and answers jump the queue; routine lines that waited too long are dropped, so the
 * voice never describes play that is no longer on screen. `stop()` silences it at once (seek, replay).
 */
export function useVoice(enabled: boolean) {
  const queue = useRef<Line[]>([]);
  const playing = useRef(false);
  const audio = useRef<HTMLAudioElement | null>(null);
  const finish = useRef<(() => void) | null>(null);
  const generation = useRef(0); // bumps on stop(): anything in flight from before is discarded
  const [speaking, setSpeaking] = useState<string | null>(null);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  const next = useCallback(async () => {
    if (playing.current) return;
    let line = queue.current.shift();
    while (line && !PRIORITY.has(line.kind ?? "") && Date.now() - line.queuedAt > STALE_MS) line = queue.current.shift();
    if (!line) return;
    const gen = generation.current;
    playing.current = true;
    setSpeaking(line.text);
    try {
      const res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: line.text, lang: line.lang, kind: line.kind }),
      });
      if (!res.ok) throw new Error(`tts ${res.status}`);
      const blob = await res.blob();
      if (!enabledRef.current || gen !== generation.current) return; // muted, seeked or a replay opened meanwhile
      if (!PRIORITY.has(line.kind ?? "") && Date.now() - line.queuedAt > STALE_MS + 2000) return; // too late now
      const url = URL.createObjectURL(blob);
      const a = new Audio(url);
      audio.current = a;
      await new Promise<void>((resolve) => {
        finish.current = resolve;
        a.onended = a.onerror = () => resolve();
        a.play().catch(() => resolve());
      });
      finish.current = null;
      audio.current = null;
      URL.revokeObjectURL(url);
    } catch {
      // A failed line is skipped; the next one still plays.
    } finally {
      playing.current = false;
      setSpeaking(null);
      void next();
    }
  }, []);

  const speak = useCallback(
    (text: string, lang: string, kind?: string) => {
      if (!enabled || !text) return;
      const line = { text: spokenVersion(text), lang, kind, queuedAt: Date.now() };
      if (kind && PRIORITY.has(kind)) {
        queue.current = [line, ...queue.current.filter((l) => PRIORITY.has(l.kind ?? ""))];
      } else {
        queue.current.push(line);
        const routine = queue.current.filter((l) => !PRIORITY.has(l.kind ?? ""));
        if (routine.length > MAX_WAITING) {
          const keep = new Set(routine.slice(-MAX_WAITING)); // newest routine line wins
          queue.current = queue.current.filter((l) => PRIORITY.has(l.kind ?? "") || keep.has(l));
        }
      }
      void next();
    },
    [enabled, next],
  );

  /** Silence now: drop the queue and cut the current line (the queue keeps working afterwards). */
  const stop = useCallback(() => {
    generation.current += 1;
    queue.current = [];
    const a = audio.current;
    const done = finish.current;
    if (!a) return;
    // A quick fade instead of cutting mid-word.
    const fade = setInterval(() => {
      a.volume = Math.max(0, a.volume - 0.2);
      if (a.volume <= 0.01) {
        clearInterval(fade);
        a.pause();
        done?.();
      }
    }, 50);
  }, []);

  /** Let the current sentence finish, but say nothing more (the match is paused). */
  const drain = useCallback(() => {
    generation.current += 1;
    queue.current = [];
  }, []);

  useEffect(() => {
    if (!enabled) stop();
  }, [enabled, stop]);

  return { speak, speaking, stop, drain };
}
