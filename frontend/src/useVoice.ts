import { useCallback, useEffect, useRef, useState } from "react";

interface Line {
  text: string;
  lang: string;
  kind?: string;
}

const PRIORITY = new Set(["goal", "answer"]);
const MAX_QUEUE = 2; // stay close to live play: drop older routine lines rather than fall behind

/**
 * Spoken commentary: each line is synthesised by the backend (Azure AI Speech neural voice)
 * and played in order. Goals and answers to the viewer's questions jump the queue.
 */
export function useVoice(enabled: boolean) {
  const queue = useRef<Line[]>([]);
  const playing = useRef(false);
  const audio = useRef<HTMLAudioElement | null>(null);
  const [speaking, setSpeaking] = useState<string | null>(null);
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  const next = useCallback(async () => {
    if (playing.current) return;
    const line = queue.current.shift();
    if (!line) return;
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
      if (!enabledRef.current) return; // muted (or a replay opened) while this line was being fetched
      const url = URL.createObjectURL(blob);
      const a = new Audio(url);
      audio.current = a;
      await new Promise<void>((resolve) => {
        a.onended = a.onerror = () => resolve();
        a.play().catch(() => resolve());
      });
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
      const line = { text, lang, kind };
      if (kind && PRIORITY.has(kind)) queue.current.unshift(line);
      else queue.current.push(line);
      while (queue.current.length > MAX_QUEUE) {
        const drop = queue.current.findIndex((l) => !PRIORITY.has(l.kind ?? ""));
        queue.current.splice(drop >= 0 ? drop : queue.current.length - 1, 1);
      }
      void next();
    },
    [enabled, next],
  );

  useEffect(() => {
    if (enabled) return;
    queue.current = [];
    audio.current?.pause();
  }, [enabled]);

  return { speak, speaking };
}
