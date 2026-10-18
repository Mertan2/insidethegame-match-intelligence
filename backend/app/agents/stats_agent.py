"""Stats agent: picks the moment worth talking about and gathers grounded facts.

Deliberately deterministic: every number later agents mention comes from here,
so LLM phrasing can't invent statistics.
"""

from __future__ import annotations

from typing import Any

from .base import Agent, Blackboard

THRESHOLD = {"casual": 0.55, "analyst": 0.4}


def goal_effect(score_after: dict[str, int], scorer: str) -> str:
    """What a goal did to the game, stated outright so the model can't guess wrong."""
    other = "away" if scorer == "home" else "home"
    mine, theirs = score_after.get(scorer, 0), score_after.get(other, 0)
    if mine == theirs:
        return "equaliser"
    if mine == theirs + 1:
        return "opening goal, takes the lead" if theirs == 0 and mine == 1 else "takes the lead"
    if mine > theirs:
        return "extends the lead"
    return "pulls one back, still behind"


class StatsAgent(Agent):
    name = "stats"
    role = "Selects the key moment and the facts that support it"

    async def run(self, bb: Blackboard) -> str:
        self.run_template(bb)
        return "deterministic"

    def run_template(self, bb: Blackboard) -> None:
        persona = bb.persona

        def score(ins) -> float:
            s = ins.importance
            if persona.favorite_player and ins.player_id == persona.favorite_player:
                s += 0.2
            if persona.favorite_team and ins.team == persona.favorite_team:
                s += 0.1
            return s

        candidates = [i for i in bb.insights if score(i) >= THRESHOLD[persona.mode]]
        if not candidates:
            bb.moment = None
            return
        ins = max(candidates, key=score)
        facts: dict[str, Any] = {k: v for k, v in ins.data.items() if v is not None and not isinstance(v, (dict, list))}
        facts["score_now"] = f"{bb.team_names.get('home', 'Home')} {bb.score.get('home', 0)}-{bb.score.get('away', 0)} {bb.team_names.get('away', 'Away')}"
        if ins.kind == "goal" and ins.team in ("home", "away"):
            facts["goal_effect"] = goal_effect(bb.score, ins.team)
        stats = (bb.snapshots.get("stats") or {}).get("teams", {})
        if ins.team and ins.team in stats:
            team = stats[ins.team]
            facts.update(
                team_shots=team.get("shots"),
                team_xg=team.get("xg"),
                team_possession_pct=team.get("possession_pct"),
                team_pass_accuracy_pct=team.get("pass_accuracy_pct"),
            )
        bb.moment = {
            "kind": ins.kind,
            "headline": ins.headline,
            "importance": round(score(ins), 2),
            "team": ins.team,
            "team_name": bb.team_names.get(ins.team or "", ""),
            "player_id": ins.player_id,
            "player": bb.name(ins.player_id),
            "source": ins.source,
            "facts": facts,
        }
