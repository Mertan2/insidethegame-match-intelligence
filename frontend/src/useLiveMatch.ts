import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentInfo, Frame, MatchEvent, MatchMeta, Narration, Persona, PluginInfo, PluginPayloads } from "./types";

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
};

/**
 * Connects to the live WebSocket. Messages land in a ref and React re-renders at
 * most once per animation frame, so high replay speeds don't flood the renderer.
 */
export function useLiveMatch(matchId: string | null, initialPersona: Persona, initialSpeed: number) {
  const [state, setState] = useState<LiveState>(INITIAL);
  const live = useRef<LiveState>(INITIAL);
  const ws = useRef<WebSocket | null>(null);
  const dirty = useRef(false);

  useEffect(() => {
    if (!matchId) return;
    live.current = { ...INITIAL, speed: initialSpeed };
    const params = new URLSearchParams({ speed: String(initialSpeed), mode: initialPersona.mode, lang: initialPersona.language });
    if (initialPersona.favorite_team) params.set("favorite_team", initialPersona.favorite_team);
    if (initialPersona.favorite_player) params.set("favorite_player", initialPersona.favorite_player);
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${proto}://${location.host}/ws/live/${matchId}?${params}`);
    ws.current = socket;

    const update = (patch: Partial<LiveState>) => {
      live.current = { ...live.current, ...patch };
      dirty.current = true;
    };

    socket.onopen = () => update({ connected: true });
    socket.onclose = () => update({ connected: false });
    socket.onmessage = (msg) => {
      const data = JSON.parse(msg.data);
      const cur = live.current;
      switch (data.type) {
        case "meta":
          update({ meta: data.meta, enabled: data.enabled, available: data.plugins, agents: data.agents, speed: data.speed });
          break;
        case "tick": {
          const plugins = { ...cur.plugins, ...data.plugins };
          // Disabled plugins stop sending; drop their stale payloads.
          for (const k of Object.keys(plugins)) if (!cur.enabled.includes(k)) delete plugins[k as keyof PluginPayloads];
          const events = data.events.length ? [...data.events.reverse(), ...cur.events].slice(0, 60) : cur.events;
          update({ frame: data.frame, plugins, events, ended: false });
          break;
        }
        case "narration":
          update({ narrations: [data as Narration, ...cur.narrations].slice(0, 50) });
          break;
        case "plugins_ack":
          update({ enabled: data.enabled });
          break;
        case "control_ack":
          update({ paused: data.paused, speed: data.speed });
          break;
        case "end":
          update({ ended: true });
          break;
      }
    };

    let raf = 0;
    const loop = () => {
      if (dirty.current) {
        dirty.current = false;
        setState(live.current);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      socket.close();
    };
    // Persona/speed changes after connect go over the socket, not via reconnect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matchId]);

  const send = useCallback((msg: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(msg));
  }, []);

  const clearNarrations = useCallback(() => {
    live.current = { ...live.current, narrations: [], events: [] };
    dirty.current = true;
  }, []);

  return { state, send, clearNarrations };
}
