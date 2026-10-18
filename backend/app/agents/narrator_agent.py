"""Narrator agent: turns the moment into a live commentary line."""

from __future__ import annotations

import json

from .base import Agent, Blackboard

SYSTEM = (
    "You are a live football commentator. Write ONE energetic commentary line (max 25 words) "
    "for the moment described. Use only the provided names and numbers. "
    "Units: distances are metres (never yards), speeds km/h, xG 0-1."
)

TEMPLATES = {
    "goal": "GOAL! {player} scores for {team}! It's {home}-{away}.",
    "big_chance": "What a chance for {player}! {outcome_phrase}",
    "shot": "{player} lets fly from {distance} metres. {outcome_phrase}",
    "difficult_pass": "Brilliant from {player}, a {distance_m}-metre pass that cuts through the lines.",
    "rocket_shot": "{player} absolutely leathers it, {speed_kmh} km/h!",
    "momentum_swing": "The tide is turning. {team} are taking over this game.",
    "regime_chaos": "End to end stuff now, nobody can keep the ball!",
    "regime_control": "Things have settled down, one side is dictating the tempo.",
}

OUTCOME = {
    "saved": "The keeper gets down to save!",
    "blocked": "Blocked!",
    "off_target": "Wide of the target.",
    "rebound_teammate": "It falls kindly to a teammate.",
}


class NarratorAgent(Agent):
    name = "narrator"
    role = "Writes the live commentary line"
    instructions = SYSTEM

    def run_template(self, bb: Blackboard) -> None:
        m = bb.moment
        if m is None:
            return
        facts = m.get("facts", {})
        template = TEMPLATES.get(m["kind"], m["headline"])
        values = {
            "player": m.get("player") or m.get("team_name"),
            "team": m.get("team_name"),
            "home": bb.score.get("home", 0),
            "away": bb.score.get("away", 0),
            "outcome_phrase": OUTCOME.get(str(facts.get("outcome")), ""),
            **facts,
        }
        try:
            bb.line = template.format(**values).strip()
        except (KeyError, ValueError):
            bb.line = m["headline"]

    async def run_llm(self, bb: Blackboard) -> None:
        if bb.moment is None:
            return
        prompt = json.dumps({"clock": bb.clock, "score": bb.score, "moment": bb.moment})
        bb.line = await self.ask(prompt, max_tokens=80)
