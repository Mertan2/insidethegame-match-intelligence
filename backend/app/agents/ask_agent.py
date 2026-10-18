"""Ask agent: answers a viewer's free-form question about the live match.

The model gets tools over the live match state (scoreboard, team and player stats,
recent events, forecast, passing) and decides which to call; it may only answer from
what the tools return. Without a model, a few common questions get rule-based answers.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..models import Event, MatchMeta
from .base import Persona

MAX_TOOL_ROUNDS = 4

SYSTEM = (
    "You are the live match analyst inside a football broadcast app. Answer the viewer's question about the "
    "match being played right now. Always call the tools to get facts; never guess numbers, names or events. "
    "If the tools don't have the answer, say so briefly. Answer in {language_name}, in at most 3 short "
    "sentences{style}. Units: metres, km/h, xG 0-1. Times are match minutes."
)

LANGUAGE_NAMES = {"en": "English", "es": "Spanish", "tr": "Turkish", "fr": "French", "de": "German", "pt": "Portuguese", "ar": "Arabic"}


@dataclass
class LiveContext:
    """Snapshot of one viewer's live session at question time."""

    meta: MatchMeta
    t: float
    score: dict[str, int]
    snapshots: dict[str, Any]
    events: list[Event]
    favorite_player: str | None = None
    players: dict[str, Any] = field(init=False)

    def __post_init__(self) -> None:
        self.players = {p.id: p for p in self.meta.players}

    def clock(self, t: float | None = None) -> str:
        return f"{int((self.t if t is None else t) // 60) + 1}'"

    def team_key(self, team: str) -> str | None:
        t = team.strip().lower()
        for side, tm in self.meta.teams.items():
            if t in (side, tm.name.lower(), tm.short.lower()) or t in tm.name.lower():
                return side
        return None

    def find_player(self, query: str) -> Any | None:
        q = query.strip().lower().lstrip("#")
        for p in self.meta.players:
            if q in (p.id.lower(), p.name.lower()) or q in p.name.lower().split():
                return p
        if q.isdigit():
            hits = [p for p in self.meta.players if p.number == int(q)]
            return hits[0] if len(hits) == 1 else None
        return None


# ----------------------------------------------------------------------------- tools
def _match_state(ctx: LiveContext, **_: Any) -> dict[str, Any]:
    teams = (ctx.snapshots.get("stats") or {}).get("teams", {})
    mom = ctx.snapshots.get("momentum") or {}
    return {
        "clock": ctx.clock(),
        "home": ctx.meta.teams["home"].name,
        "away": ctx.meta.teams["away"].name,
        "score": ctx.score,
        "possession_pct": {s: teams.get(s, {}).get("possession_pct") for s in ("home", "away")},
        "shots": {s: teams.get(s, {}).get("shots") for s in ("home", "away")},
        "xg": {s: teams.get(s, {}).get("xg") for s in ("home", "away")},
        "momentum": mom.get("momentum"),
        "momentum_note": "positive favours home, negative favours away",
        "game_state": mom.get("regime"),
    }


def _team_stats(ctx: LiveContext, team: str = "home", **_: Any) -> dict[str, Any]:
    side = ctx.team_key(team)
    if side is None:
        return {"error": f"unknown team '{team}'"}
    stats = ((ctx.snapshots.get("stats") or {}).get("teams") or {}).get(side, {})
    passing = ((ctx.snapshots.get("pass_quality") or {}).get("teams") or {}).get(side, {})
    return {"team": ctx.meta.teams[side].name, **stats, "pass_quality": passing}


def _player(ctx: LiveContext, name: str = "", **_: Any) -> dict[str, Any]:
    p = ctx.find_player(name) if name else (ctx.players.get(ctx.favorite_player or ""))
    if p is None:
        return {"error": f"no player matching '{name}'", "players": [f"{q.name} (#{q.number}, {ctx.meta.teams[q.team].short})" for q in ctx.meta.players]}
    row = next((r for r in (ctx.snapshots.get("stats") or {}).get("players", []) if r["player_id"] == p.id), {})
    involvement = [
        {"clock": ctx.clock(e.t), "type": e.type, **{k: v for k, v in e.data.items() if k in ("outcome", "xg", "speed_kmh", "body_part")}}
        for e in ctx.events if e.player_id == p.id and e.type in ("shot", "goal", "tackle")
    ][-8:]
    return {"name": p.name, "number": p.number, "team": ctx.meta.teams[p.team].name, "role": p.role,
            "preferred_foot": p.preferred_foot, **{k: v for k, v in row.items() if k not in ("player_id", "name", "team")},
            "key_actions": involvement}


def _recent_events(ctx: LiveContext, minutes: float = 5, type: str = "", **_: Any) -> dict[str, Any]:
    since = ctx.t - float(minutes) * 60
    keep = {"goal", "shot", "tackle", "possession_change", "corner", "goal_kick", "throw_in"}
    out = []
    for e in ctx.events:
        if e.t < since or e.type not in keep or (type and e.type != type):
            continue
        who = ctx.players[e.player_id].name if e.player_id in ctx.players else None
        out.append({"clock": ctx.clock(e.t), "type": e.type, "team": ctx.meta.teams[e.team].name if e.team else None, "player": who,
                    **{k: v for k, v in e.data.items() if k in ("outcome", "xg", "speed_kmh", "body_part", "cause", "success")}})
    return {"since": ctx.clock(since), "events": out[-25:]}


def _forecast(ctx: LiveContext, **_: Any) -> dict[str, Any]:
    f = ctx.snapshots.get("ball_forecast") or {}
    return {k: v for k, v in f.items() if k != "trajectory"}


def _top_players(ctx: LiveContext, metric: str = "distance_m", **_: Any) -> dict[str, Any]:
    rows = (ctx.snapshots.get("stats") or {}).get("players", [])
    if not rows or metric not in rows[0]:
        return {"error": f"unknown metric '{metric}'", "metrics": sorted(rows[0].keys()) if rows else []}
    top = sorted(rows, key=lambda r: (r.get(metric) or 0), reverse=True)[:5]
    return {"metric": metric, "top": [{"name": r["name"], "team": ctx.meta.teams[r["team"]].short, metric: r.get(metric)} for r in top]}


TOOLS: dict[str, tuple[Callable[..., dict[str, Any]], dict[str, Any]]] = {
    "get_match_state": (_match_state, {"description": "Clock, score, possession, shots, xG, momentum and game state right now.",
                                       "parameters": {"type": "object", "properties": {}}}),
    "get_team_stats": (_team_stats, {"description": "Full stats for one team: passes, accuracy, shots, xG, tackles, pressures, pass quality.",
                                     "parameters": {"type": "object", "properties": {"team": {"type": "string", "description": "'home', 'away' or the team name"}}, "required": ["team"]}}),
    "get_player": (_player, {"description": "One player's live stats (distance, top speed, passes, shots, xG, feet, headers, fatigue) and key actions. Empty name = the viewer's favourite player.",
                             "parameters": {"type": "object", "properties": {"name": {"type": "string", "description": "player name, surname or shirt number"}}}}),
    "get_recent_events": (_recent_events, {"description": "Recent match events (goals, shots, tackles, turnovers, set pieces).",
                                           "parameters": {"type": "object", "properties": {"minutes": {"type": "number"}, "type": {"type": "string", "description": "optional filter, e.g. 'shot' or 'goal'"}}}}),
    "get_ball_forecast": (_forecast, {"description": "Physics forecast of the ball in flight (landing point, goal-line crossing, on target) and its measured accuracy.",
                                      "parameters": {"type": "object", "properties": {}}}),
    "get_top_players": (_top_players, {"description": "Top 5 players by a metric: distance_m, top_speed_kmh, passes_completed, shots, xg, headers, fatigue_pct.",
                                       "parameters": {"type": "object", "properties": {"metric": {"type": "string"}}, "required": ["metric"]}}),
}


def tool_specs() -> list[dict[str, Any]]:
    return [{"type": "function", "function": {"name": name, **spec}} for name, (_, spec) in TOOLS.items()]


def run_tool(ctx: LiveContext, name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name not in TOOLS:
        return {"error": f"unknown tool {name}"}
    try:
        return TOOLS[name][0](ctx, **args)
    except Exception as exc:  # noqa: BLE001 - tool errors go back to the model
        return {"error": f"{type(exc).__name__}: {exc}"}


# ----------------------------------------------------------------------------- agent
class AskAgent:
    name = "ask"
    role = "Answers viewer questions live, calling match-data tools"

    def __init__(self, llm: Any):
        self.llm = llm

    async def answer(self, question: str, ctx: LiveContext, persona: Persona) -> dict[str, Any]:
        started = time.perf_counter()
        calls: list[dict[str, Any]] = []
        if getattr(self.llm, "available", False) and hasattr(self.llm, "chat"):
            try:
                text = await self._llm_answer(question, ctx, persona, calls)
                path = "llm"
            except Exception as exc:  # noqa: BLE001 - fall back rather than leave the viewer hanging
                text, path = self._template(question, ctx), f"template ({type(exc).__name__})"
        else:
            text, path = self._template(question, ctx), "template"
        return {"question": question, "answer": text, "tools": calls, "path": path,
                "clock": ctx.clock(), "ms": round((time.perf_counter() - started) * 1000)}

    async def _llm_answer(self, question: str, ctx: LiveContext, persona: Persona, calls: list[dict[str, Any]]) -> str:
        style = ", with the key numbers" if persona.mode == "analyst" else ", plain words for a casual fan"
        system = SYSTEM.format(language_name=LANGUAGE_NAMES.get(persona.language, "English"), style=style)
        if persona.favorite_player and persona.favorite_player in ctx.players:
            system += f" The viewer's favourite player is {ctx.players[persona.favorite_player].name}."
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": question}]
        for _ in range(MAX_TOOL_ROUNDS):
            msg = await self.llm.chat(messages, tool_specs())
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                if msg.get("content"):
                    return msg["content"].strip()
                break
            messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls})
            for tc in tool_calls:
                fn = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = run_tool(ctx, fn, args)
                calls.append({"tool": fn, "args": args})
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(result, default=str)[:6000]})
        raise RuntimeError("no answer after tool rounds")

    def _template(self, question: str, ctx: LiveContext) -> str:
        q = question.lower()
        s = _match_state(ctx)
        h, a = ctx.meta.teams["home"].name, ctx.meta.teams["away"].name
        if any(w in q for w in ("possession", "ball", "topa")):
            p = s["possession_pct"]
            return f"Possession: {h} {p['home']}%, {a} {p['away']}%."
        if "xg" in q or "chance" in q:
            return f"xG so far: {h} {s['xg']['home']}, {a} {s['xg']['away']}."
        if any(w in q for w in ("who", "best", "fastest", "most")):
            top = _top_players(ctx, "distance_m")["top"][:3]
            return "Most ground covered: " + ", ".join(f"{r['name']} ({r['distance_m']} m)" for r in top) + "."
        return f"{ctx.clock()}: {h} {ctx.score['home']}-{ctx.score['away']} {a}. Shots {s['shots']['home']}-{s['shots']['away']}."
