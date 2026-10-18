"""Narrator agent: turns the moment into a live commentary line."""

from __future__ import annotations

import json

from .base import Agent, Blackboard

SYSTEM = (
    "You are a live football TV commentator. Write ONE energetic commentary line (max 25 words) "
    "for the moment described. Use only the provided names and numbers. Follow the 'brief' instruction: "
    "for play-by-play describe what viewers see right now; for a fun fact deliver it like a commentator's aside; "
    "for a recap sum up the match so far. "
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
    "play_by_play": "{on_screen}.",
    "fun_fact": "Here's one for you: {fun_fact}.",
    "recap": "{recap}",
    "half_time_recap": "That's half time. {recap}",
    "full_time_recap": "Full time! {recap}",
}

BRIEFS = {
    "play_by_play": ("play-by-play in a lively TV-commentator voice, never copying the brief word for word and "
                     "no brackets: who has the ball and where (on_screen), plus the last pass from recent_play if "
                     "there is one. Max 15 words. Only events in the brief: no invented dribbles, shots or tackles"),
    "fun_fact": "fun fact: deliver it as a commentator's aside (max 22 words)",
    "recap": "recap: summarise the match so far in max 2 short sentences",
    "half_time_recap": "half-time recap: summarise the first half in max 2 short sentences",
    "full_time_recap": "full-time recap: summarise the match in max 2 short sentences",
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
        brief = BRIEFS.get(bb.moment["kind"], "key moment: react to it")
        prompt = json.dumps({"brief": brief, "clock": bb.clock, "score": bb.score, "moment": bb.moment})
        bb.line = await self.ask(prompt, max_tokens=80)
