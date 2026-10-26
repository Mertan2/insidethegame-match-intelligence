"""Persona agent: shapes the same intelligence for each viewer (mode, favourites, language)."""

from __future__ import annotations

import json

from .base import Agent, Blackboard

SYSTEM = (
    "You adapt football commentary for a specific viewer. Rewrite the text for the given persona "
    "and translate it into the target language. Keep every number unchanged. Return only the text. "
    "Casual mode: at most two short sentences, plain words. Analyst mode: at most three short sentences "
    "(about 45 words), the commentary line first, then the key reason with at most two numbers. "
    "If the persona has focus_metric and the text mentions viewer_metric facts, keep that one metric in: it is "
    "what this viewer tuned in for. "
    "Units: distances are metres (never yards), speeds km/h, xG 0-1."
)


class PersonaAgent(Agent):
    name = "persona"
    role = "Personalises output: casual vs analyst, favourite club/player, language"
    instructions = SYSTEM

    def _compose(self, bb: Blackboard) -> tuple[str, list[str]]:
        m = bb.moment or {}
        p = bb.persona
        prefix = ""
        if p.favorite_player and m.get("player_id") == p.favorite_player:
            prefix = "Your player! "
        elif p.favorite_team and m.get("team") == p.favorite_team:
            prefix = "Good news for your team: " if m.get("kind") != "goal" else ""
        why = (bb.why or {}).get("text", "")
        f = m.get("facts") or {}
        metric = ""
        if p.focus_metric and f.get("viewer_metric"):
            if f.get("viewer_metric_this_player") and m.get("player"):
                metric = f" {m['player']}: {f['viewer_metric_this_player']} {f['viewer_metric']} so far."
            elif f.get("viewer_metric_leaders"):
                metric = f" {f['viewer_metric'].capitalize()} leaders: {f['viewer_metric_leaders']}."
        if p.mode == "casual":
            text = f"{prefix}{bb.line or m.get('headline', '')}"
            if why:
                text += " " + why.split(". ")[0].rstrip(".") + "."
            return text + metric, []
        facts = [f"{k.replace('_', ' ')}: {v}" for k, v in (m.get("facts") or {}).items()]
        # Analysts get the reason too, kept short because it is read out live: whole sentences up to ~30 words.
        reason = ""
        for sentence in (x.strip().rstrip(".") for x in why.split(". ") if x.strip()):
            if reason and len((reason + " " + sentence).split()) > 30:
                break
            reason = f"{reason} {sentence}." if reason else f"{sentence}."
        return f"{prefix}{bb.line or m.get('headline', '')} {reason}".strip() + metric, facts

    def _output(self, bb: Blackboard, text: str, facts: list[str], translated: bool) -> None:
        m = bb.moment or {}
        bb.output = {
            "t": bb.t,
            "clock": bb.clock,
            "kind": m.get("kind"),
            "importance": m.get("importance"),
            "team": m.get("team"),
            "player_id": m.get("player_id"),
            "headline": m.get("headline"),
            "text": text,
            "why": (bb.why or {}).get("factors", []),
            "facts": facts,
            "language": bb.persona.language if translated else "en",
            "requested_language": bb.persona.language,
            "mode": bb.persona.mode,
        }

    def run_template(self, bb: Blackboard) -> None:
        if bb.moment is None:
            return
        text, facts = self._compose(bb)
        # Translation needs an LLM; without one we keep English and say so.
        self._output(bb, text, facts, translated=bb.persona.language == "en")

    async def run_llm(self, bb: Blackboard) -> None:
        if bb.moment is None:
            return
        text, facts = self._compose(bb)
        if bb.persona.language != "en" or bb.persona.mode == "casual":
            prompt = json.dumps({"persona": bb.persona.model_dump(), "language": bb.persona.language, "text": text})
            text = await self.ask(prompt, max_tokens=160)
        self._output(bb, text, facts, translated=True)
