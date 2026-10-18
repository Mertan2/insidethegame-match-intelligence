"""Tactics agent: explains *why* the moment matters using momentum, chaos and pressure."""

from __future__ import annotations

import json

from .base import Agent, Blackboard

SYSTEM = (
    "You are a football tactics analyst. Explain in at most two sentences why the moment matters. "
    "Use only the numbers provided. No invented facts. "
    "Units: distances are metres (never yards), speeds km/h, xG 0-1."
)


# Director briefs (play-by-play, fun facts, recaps) carry their own content; analysing them would only
# slow live commentary down.
BRIEF_KINDS = {"play_by_play", "fun_fact", "recap", "half_time_recap", "full_time_recap"}


class TacticsAgent(Agent):
    name = "tactics"
    role = "Explains why the moment matters (momentum, control vs chaos, pressure)"
    instructions = SYSTEM

    async def run(self, bb: Blackboard) -> str:
        if (bb.moment or {}).get("kind") in BRIEF_KINDS:
            bb.why = {"text": "", "factors": []}
            return "skipped"
        return await super().run(bb)

    def _factors(self, bb: Blackboard) -> list[str]:
        m = bb.moment or {}
        factors: list[str] = []
        mom = bb.snapshots.get("momentum") or {}
        if mom:
            side = m.get("team")
            signed = mom.get("momentum", 0.0) * (1 if side == "home" else -1)
            if side and signed > 0.3:
                factors.append(f"{m.get('team_name')} have dominated the last five minutes (momentum {signed:+.2f})")
            elif side and signed < -0.3:
                factors.append(f"it comes against the run of play (momentum {signed:+.2f})")
            regime = mom.get("regime")
            if regime == "chaos":
                factors.append(f"the game is chaotic: {mom.get('possession_changes_per_min')} possession changes per minute")
            elif regime == "control":
                factors.append("the game is controlled, with long spells of possession")
        facts = m.get("facts", {})
        if "xg" in facts:
            xg = facts["xg"]
            quality = "a big chance" if xg >= 0.3 else "a half-chance" if xg >= 0.1 else "a speculative effort"
            factors.append(f"it was {quality} (xG {xg:.2f}) from {facts.get('distance')} m")
        if "difficulty" in facts:
            factors.append(
                f"the pass rated {facts['difficulty']}/100 for difficulty, covering {facts.get('distance_m')} m "
                f"and gaining {facts.get('progress_m')} m"
            )
        forecast = bb.snapshots.get("ball_forecast") or {}
        acc = forecast.get("accuracy") or {}
        if m.get("kind") in ("shot", "big_chance", "goal") and acc.get("mean_error_m") is not None:
            factors.append(
                f"ball-flight forecasts are within {acc['mean_error_m']} m of reality {acc.get('horizon_s', 1.0)} s ahead"
            )
        return factors

    def run_template(self, bb: Blackboard) -> None:
        if bb.moment is None:
            return
        factors = self._factors(bb)
        text = (factors[0][0].upper() + factors[0][1:] + ".") if factors else ""
        if len(factors) > 1:
            text += " Also, " + factors[1] + "."
        bb.why = {"text": text, "factors": factors}

    async def run_llm(self, bb: Blackboard) -> None:
        if bb.moment is None:
            return
        factors = self._factors(bb)
        prompt = json.dumps({"moment": bb.moment, "factors": factors, "clock": bb.clock})
        text = await self.ask(prompt, max_tokens=120)
        bb.why = {"text": text, "factors": factors}
