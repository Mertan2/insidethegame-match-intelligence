import { useEffect, useRef } from "react";
import type { ForecastPayload, Frame, MatchMeta, SpeedPayload } from "../types";

const L = 105;
const W = 68;

interface Props {
  meta: MatchMeta;
  frame: Frame | null;
  forecast?: ForecastPayload;
  speed?: SpeedPayload;
  favoritePlayer: string | null;
}

/** Bird's-eye tactical view drawn on canvas. Ball height is shown by lifting the ball off its shadow. */
export function Pitch2D({ meta, frame, forecast, speed, favoritePlayer }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    const cssW = c.clientWidth;
    const cssH = (cssW * W) / L;
    if (c.width !== Math.round(cssW * dpr)) {
      c.width = Math.round(cssW * dpr);
      c.height = Math.round(cssH * dpr);
      c.style.height = `${cssH}px`;
    }
    const ctx = c.getContext("2d")!;
    const s = (cssW / L) * dpr;
    const X = (x: number) => x * s;
    const Y = (y: number) => y * s;

    ctx.fillStyle = "#1f6b3a";
    ctx.fillRect(0, 0, c.width, c.height);
    for (let i = 0; i < 10; i++) {
      if (i % 2) continue;
      ctx.fillStyle = "#237541";
      ctx.fillRect(X((i * L) / 10), 0, X(L / 10), c.height);
    }
    drawLines(ctx, X, Y, s);

    if (!frame) return;
    const players = new Map(meta.players.map((p) => [p.id, p]));

    // Forecast path (ground projection) and landing marker.
    if (forecast?.active && forecast.trajectory) {
      ctx.setLineDash([4 * dpr, 4 * dpr]);
      ctx.strokeStyle = "rgba(255,230,90,0.9)";
      ctx.lineWidth = 2 * dpr;
      ctx.beginPath();
      forecast.trajectory.forEach(([x, y], i) => (i ? ctx.lineTo(X(x), Y(y)) : ctx.moveTo(X(x), Y(y))));
      ctx.stroke();
      ctx.setLineDash([]);
      if (forecast.landing) {
        const lx = X(forecast.landing.x);
        const ly = Y(forecast.landing.y);
        ctx.strokeStyle = "#ffe65a";
        ctx.beginPath();
        ctx.moveTo(lx - 5 * dpr, ly - 5 * dpr);
        ctx.lineTo(lx + 5 * dpr, ly + 5 * dpr);
        ctx.moveTo(lx + 5 * dpr, ly - 5 * dpr);
        ctx.lineTo(lx - 5 * dpr, ly + 5 * dpr);
        ctx.stroke();
      }
    }

    const tagged = new Map((speed?.tags ?? []).map((t) => [t.player_id, t]));
    for (const [id, x, y] of frame.players) {
      const p = players.get(id);
      if (!p) continue;
      const r = 1.3 * s;
      ctx.beginPath();
      ctx.arc(X(x), Y(y), r, 0, Math.PI * 2);
      ctx.fillStyle = p.role === "GK" ? "#f2d14b" : meta.teams[p.team].color;
      ctx.fill();
      if (id === frame.owner || id === favoritePlayer) {
        ctx.lineWidth = 2 * dpr;
        ctx.strokeStyle = id === favoritePlayer ? "#ff4fd8" : "#ffffff";
        ctx.stroke();
      }
      ctx.fillStyle = "#0b1d12";
      ctx.font = `bold ${1.4 * s}px system-ui`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(p.number), X(x), Y(y) + 0.5);
      const tag = tagged.get(id);
      if (tag || id === favoritePlayer) {
        const label = tag ? `${p.name} · ${tag.speed_kmh} km/h` : p.name;
        ctx.font = `${1.5 * s}px system-ui`;
        const tw = ctx.measureText(label).width + 8 * dpr;
        ctx.fillStyle = "rgba(10,16,24,0.8)";
        ctx.fillRect(X(x) - tw / 2, Y(y) - 4.2 * s, tw, 2.2 * s);
        ctx.fillStyle = tag ? "#ffe65a" : "#ff9cf0";
        ctx.fillText(label, X(x), Y(y) - 3.1 * s);
      }
    }

    // Ball: shadow at ground position, ball lifted by height.
    const [bx, by, bz] = frame.ball;
    ctx.beginPath();
    ctx.ellipse(X(bx), Y(by), 0.7 * s, 0.45 * s, 0, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(0,0,0,0.35)";
    ctx.fill();
    ctx.beginPath();
    ctx.arc(X(bx), Y(by) - bz * s * 0.6, (0.6 + bz * 0.06) * s, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    ctx.strokeStyle = "#111";
    ctx.lineWidth = 1 * dpr;
    ctx.stroke();
  }, [meta, frame, forecast, speed, favoritePlayer]);

  return <canvas ref={canvas} className="pitch2d" />;
}

function drawLines(ctx: CanvasRenderingContext2D, X: (v: number) => number, Y: (v: number) => number, s: number) {
  ctx.strokeStyle = "rgba(255,255,255,0.85)";
  ctx.lineWidth = Math.max(1, s * 0.15);
  ctx.strokeRect(X(0.5), Y(0.5), X(L - 1), Y(W - 1));
  ctx.beginPath();
  ctx.moveTo(X(L / 2), Y(0.5));
  ctx.lineTo(X(L / 2), Y(W - 0.5));
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(X(L / 2), Y(W / 2), 9.15 * s, 0, Math.PI * 2);
  ctx.stroke();
  for (const left of [true, false]) {
    const x0 = left ? 0.5 : L - 0.5;
    const dir = left ? 1 : -1;
    const box = (depth: number, width: number) =>
      ctx.strokeRect(X(Math.min(x0, x0 + dir * depth)), Y(W / 2 - width / 2), X(depth), Y(width));
    box(16.5, 40.32);
    box(5.5, 18.32);
    ctx.fillStyle = "rgba(255,255,255,0.85)";
    ctx.fillRect(X(left ? 0 : L - 0.5), Y(W / 2 - 3.66), X(0.5), Y(7.32));
  }
}
