"""Recap agent: automated full-time match report from all insights and final stats."""

from __future__ import annotations

import json

from .base import Agent, Blackboard

SYSTEM = (
    "You write concise football match reports (max 180 words) for the given persona and language. "
    "Use only the facts provided. "
    "Units: distances are metres (never yards), speeds km/h, xG 0-1."
)


class RecapAgent(Agent):
    name = "recap"
    role = "Writes the automated full-time match report"
    instructions = SYSTEM

    def _facts(self, bb: Blackboard) -> dict:
        stats = bb.snapshots.get("stats") or {}
        teams = stats.get("teams", {})
        goals = [
            {"minute": int(i.t // 60) + 1, "team": bb.team_names.get(i.team or "", ""), "player": bb.name(i.player_id) or "own goal"}
            for i in bb.insights
            if i.kind == "goal"
        ]
        swings = sorted((i for i in bb.insights if i.kind == "momentum_swing"), key=lambda i: -abs(i.data.get("to", 0) - i.data.get("from", 0)))
        players = stats.get("players", [])
        star = max(players, key=lambda p: p["xg"] * 10 + p["passes_completed"] * 0.2, default=None)
        fav = next((p for p in players if p["player_id"] == bb.persona.favorite_player), None)
        return {
            "home": bb.team_names["home"],
            "away": bb.team_names["away"],
            "score": bb.score,
            "goals": goals,
            "teams": teams,
            "turning_point": {"minute": int(swings[0].t // 60) + 1, "team": bb.team_names.get(swings[0].team or "", "")}
            if swings
            else None,
            "star": star,
            "favorite_player": fav,
        }

    def run_template(self, bb: Blackboard) -> None:
        f = self._facts(bb)
        h, a = f["score"]["home"], f["score"]["away"]
        title = f"{f['home']} {h}-{a} {f['away']}"
        paras: list[str] = []
        if f["goals"]:
            paras.append("Goals: " + "; ".join(f"{g['player']} ({g['team']}, {g['minute']}')" for g in f["goals"]) + ".")
        else:
            paras.append("A goalless contest.")
        th, ta = f["teams"].get("home", {}), f["teams"].get("away", {})
        if th and ta:
            paras.append(
                f"{f['home']} had {th['possession_pct']}% possession, {th['shots']} shots and {th['xg']} xG; "
                f"{f['away']} managed {ta['shots']} shots and {ta['xg']} xG."
            )
        if f["turning_point"]:
            tp = f["turning_point"]
            paras.append(f"The turning point came around minute {tp['minute']} as momentum swung to {tp['team']}.")
        if f["star"]:
            s = f["star"]
            paras.append(f"Standout: {s['name']}, {s['passes_completed']} completed passes, {s['xg']} xG, {s['distance_m']} m covered.")
        if f["favorite_player"]:
            p = f["favorite_player"]
            paras.append(f"Your player {p['name']}: {p['passes_completed']}/{p['passes']} passes, top speed {p['top_speed_kmh']} km/h.")
        bb.output = {"title": title, "paragraphs": paras, "facts": f, "language": "en", "requested_language": bb.persona.language}

    async def run_llm(self, bb: Blackboard) -> None:
        f = self._facts(bb)
        prompt = json.dumps({"persona": bb.persona.model_dump(), "facts": f}, default=str)
        text = await self.ask(prompt, max_tokens=400)
        h, a = f["score"]["home"], f["score"]["away"]
        bb.output = {
            "title": f"{f['home']} {h}-{a} {f['away']}",
            "paragraphs": [p for p in text.split("\n") if p.strip()],
            "facts": f,
            "language": bb.persona.language,
            "requested_language": bb.persona.language,
        }
