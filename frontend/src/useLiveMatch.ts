import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentInfo, Answer, Frame, MatchEvent, MatchMeta, Narration, Persona, PluginInfo, PluginPayloads, SeriesPoint } from "./types";

export interface FeedStats {
  msgsPerSec: number;
  kbPerSec: number;
  totalMsgs: number;
  totalKb: number;
}

export interface LiveState {
  connected: boolean;
  ended: boolean;
  meta: MatchMeta | null;
  frame: Frame | null;
  plugins: PluginPayloads;
  enabled: string[];
  available: PluginInfo[];
  agents: AgentInfo[];
  narrations: Narration[];
  events: MatchEvent[];
  paused: boolean;
  speed: number;
  series: SeriesPoint[];
  feed: FeedStats;
  playerKmh: Record<string, number>;
  answers: Answer[];
  asking: boolean;
  /** Agents taken down in the outage drill (the broadcast must carry on through their fallbacks). */
  drill: string[];
}

const INITIAL: LiveState = {
  connected: false,
  ended: false,
  meta: null,
  frame: null,
  plugins: {},
  enabled: [],
  available: [],
  agents: [],
  narrations: [],
  events: [],
  paused: false,
  speed: 4,
  series: [],
  feed: { msgsPerSec: 0, kbPerSec: 0, totalMsgs: 0, totalKb: 0 },
  playerKmh: {},
  answers: [],
  asking: false,
  drill: [],
};

/**
 * Connects to the live WebSocket. Messages land in a ref and React re-renders at
 * most once per animation frame, so high replay speeds don't flood the renderer.
 * Besides the latest state it keeps per-second time series for the live charts,
 * feed throughput, and per-player speed from consecutive tracking frames.
 */
export function useLiveMatch(matchId: string | null, initialPersona: Persona, initialSpeed: number, startPaused = false) {
  const [state, setState] = useState<LiveState>(INITIAL);
  const live = useRef<LiveState>(INITIAL);
  const ws = useRef<WebSocket | null>(null);
  const dirty = useRef(false);

  useEffect(() => {
    if (!matchId) return;
    live.current = { ...INITIAL, speed: initialSpeed, paused: startPaused };
    const params = new URLSearchParams({ speed: String(initialSpeed), mode: initialPersona.mode, lang: initialPersona.language });
    if (initialPersona.favorite_team) params.set("favorite_team", initialPersona.favorite_team);
    if (initialPersona.favorite_player) params.set("favorite_player", initialPersona.favorite_player);
    if (startPaused) params.set("paused", "true");
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${proto}://${location.host}/ws/live/${matchId}?${params}`);
    ws.current = socket;

    const update = (patch: Partial<LiveState>) => {
      live.current = { ...live.current, ...patch };
      dirty.current = true;
    };

    // Throughput counters, folded into `feed` once per wall-clock second.
    let winMsgs = 0;
    let winBytes = 0;
    const meter = setInterval(() => {
      const f = live.current.feed;
      update({
        feed: {
          msgsPerSec: winMsgs,
          kbPerSec: Math.round(winBytes / 102.4) / 10,
          totalMsgs: f.totalMsgs + winMsgs,
          totalKb: Math.round((f.totalKb + winBytes / 1024) * 10) / 10,
        },
      });
      winMsgs = 0;
      winBytes = 0;
    }, 1000);

    socket.onopen = () => update({ connected: true });
    socket.onclose = () => update({ connected: false });
    socket.onmessage = (msg) => {
      winMsgs += 1;
      winBytes += (msg.data as string).length;
      const data = JSON.parse(msg.data);
      const cur = live.current;
      switch (data.type) {
        case "meta":
          update({ meta: data.meta, enabled: data.enabled, available: data.plugins, agents: data.agents, speed: data.speed });
          break;
        case "tick": {
          const frame: Frame = data.frame;
          const plugins = { ...cur.plugins, ...data.plugins };
          // Disabled plugins stop sending; drop their stale payloads.
          for (const k of Object.keys(plugins)) if (!cur.enabled.includes(k)) delete plugins[k as keyof PluginPayloads];
          const events = data.events.length ? [...data.events.reverse(), ...cur.events].slice(0, 200) : cur.events;
          update({
            frame,
            plugins,
            events,
            ended: false,
            playerKmh: speeds(cur.frame, frame, cur.playerKmh),
            series: extendSeries(cur.series, frame, plugins),
          });
          break;
        }
        case "narration":
          update({ narrations: [data as Narration, ...cur.narrations].slice(0, 50) });
          break;
        case "answer":
          update({ answers: [data as Answer, ...cur.answers].slice(0, 20), asking: false });
          break;
        case "plugins_ack":
          update({ enabled: data.enabled });
          break;
        case "control_ack":
          update({ paused: data.paused, speed: data.speed });
          break;
        case "drill_ack":
          update({ drill: data.agents });
          break;
        case "end":
          update({ ended: true });
          break;
      }
    };

    let raf = 0;
    const flush = () => {
      if (dirty.current) {
        dirty.current = false;
        setState(live.current);
      }
    };
    const loop = () => {
      flush();
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    // Browsers pause animation frames in background or hidden views; keep state current there too.
    const slow = setInterval(flush, 250);
    return () => {
      cancelAnimationFrame(raf);
      clearInterval(slow);
      clearInterval(meter);
      socket.close();
    };
    // Persona/speed changes after connect go over the socket, not via reconnect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matchId]);

  const send = useCallback((msg: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(msg));
  }, []);

  const ask = useCallback(
    (question: string) => {
      live.current = { ...live.current, asking: true };
      dirty.current = true;
      send({ type: "ask", question });
    },
    [send],
  );

  const clearNarrations = useCallback(() => {
    live.current = { ...live.current, narrations: [], events: [] };
    dirty.current = true;
  }, []);

  return { state, send, ask, clearNarrations };
}

/** Player speeds (km/h) from two consecutive frames, lightly smoothed; restart jumps are ignored. */
function speeds(prev: Frame | null, next: Frame, last: Record<string, number>): Record<string, number> {
  if (!prev) return last;
  const dt = next.t - prev.t;
  if (dt <= 0 || dt > 1) return last;
  const before = new Map(prev.players.map(([id, x, y]) => [id, [x, y]]));
  const out: Record<string, number> = {};
  for (const [id, x, y] of next.players) {
    const p = before.get(id);
    if (!p) continue;
    const kmh = (Math.hypot(x - p[0], y - p[1]) / dt) * 3.6;
    if (kmh > 45) continue;
    out[id] = Math.round(((last[id] ?? kmh) * 0.6 + kmh * 0.4) * 10) / 10;
  }
  return out;
}

/** One point per match second; seeking back trims the future. */
function extendSeries(series: SeriesPoint[], frame: Frame, plugins: PluginPayloads): SeriesPoint[] {
  const sec = Math.floor(frame.t);
  let s = series;
  if (s.length && s[s.length - 1].t > sec) s = s.filter((p) => p.t < sec);
  if (s.length && s[s.length - 1].t === sec) return s;
  const teams = plugins.stats?.teams;
  const point: SeriesPoint = {
    t: sec,
    possHome: teams?.home.possession_pct ?? null,
    xgHome: teams?.home.xg ?? 0,
    xgAway: teams?.away.xg ?? 0,
    momentum: plugins.momentum?.momentum ?? 0,
    ballKmh: plugins.speed_metrics?.ball_speed_kmh ?? 0,
    goalsHome: frame.score.home,
    goalsAway: frame.score.away,
  };
  return [...s, point].slice(-1800);
}
