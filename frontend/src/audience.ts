import type { Persona } from "./types";

export type Audience = "fan" | "broadcaster" | "analyst";
export type View = "2d" | "3d" | "both" | "data";

/** Who is watching decides the commentary style, the default view and which panels are on screen. */
export const AUDIENCES: Record<
  Audience,
  { label: string; icon: string; blurb: string; mode: Persona["mode"]; view: View; views: View[] }
> = {
  fan: {
    label: "Fan",
    icon: "🏟️",
    blurb: "Spoken commentary, ask anything, follow your player, instant highlights",
    mode: "casual",
    view: "both",
    views: ["2d", "3d", "both"],
  },
  broadcaster: {
    label: "Broadcaster",
    icon: "🎙️",
    blurb: "On-air graphics cues, talking points with the why, a highlights package in one click",
    mode: "analyst",
    view: "2d",
    views: ["2d", "3d", "both"],
  },
  analyst: {
    label: "Analyst",
    icon: "📊",
    blurb: "Raw feed, live metrics, every agent step and the tracking data",
    mode: "analyst",
    view: "2d",
    views: ["2d", "3d", "both", "data"],
  },
};

const KEY = "itg.audience";

export function loadAudience(): Audience {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "fan" || v === "broadcaster" || v === "analyst") return v;
  } catch {
    // storage blocked: fall back to the default
  }
  return "fan";
}

export function saveAudience(a: Audience) {
  try {
    localStorage.setItem(KEY, a);
  } catch {
    // not essential
  }
}
