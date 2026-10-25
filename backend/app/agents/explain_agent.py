"""Explain and highlights agents.

ExplainAgent is the studio analyst at the telestrator: given one moment (the move, the key pass,
the shot and what the tracking showed at that instant) it writes one spoken beat per step the
replay will stop on, plus a headline and, for a full explanation, a verdict on why it worked.
Beats are tied to steps, so each line is said while that step is drawn on the pitch.

ProducerAgent cuts the highlights package: it ranks moments, sends one ExplainAgent per clip in
parallel (fan-out), then writes the intro and outro over what came back (fan-in).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from .base import Agent, Persona
from .orchestrator import run_step

LANGUAGE_NAMES = {"en": "English", "tr": "Turkish", "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese", "ar": "Arabic"}
MAX_PASS_BEATS = {"full": 3, "short": 1}


@dataclass
class ExplainBoard:
    """Shared state for one explanation (or one highlights package)."""

    moment: dict[str, Any]
    names: dict[str, str]
    team_names: dict[str, str]
    persona: Persona
    mode: str = "full"  # full: explain this moment; short: one clip in the highlights
    beats: list[dict[str, Any]] = field(default_factory=list)  # chosen steps, then their text
    output: dict[str, Any] | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)


def _zone(team: str, x: float) -> str:
    gain = x if team == "home" else 105.0 - x
    return "their own half" if gain < 45 else ("midfield" if gain < 70 else "the final third")


def choose_beats(moment: dict[str, Any], mode: str, from_t: float | None = None) -> list[dict[str, Any]]:
    """The steps the replay stops on: how the ball was won, the passes that mattered, the shot."""
    steps = [s for s in moment["steps"] if from_t is None or s["t"] >= from_t or s["type"] == "shot"]
    passes = [s for s in steps if s["type"] == "pass"]
    key = [s for s in passes if s["key_pass"]]
    notable = sorted(
        (s for s in passes if not s["key_pass"]),
        key=lambda s: (s["bypassed"], s["progress_m"]),
        reverse=True,
    )
    keep_passes = key + [s for s in notable if s["bypassed"] >= 2 or s["progress_m"] >= 12]
    keep_passes = keep_passes[: MAX_PASS_BEATS[mode]]
    chosen = [s for s in steps if s["type"] == "regain"][: 1 if mode == "full" else 0]
    chosen += sorted(keep_passes, key=lambda s: s["t"])
    chosen += [s for s in steps if s["type"] == "shot"]
    return [{"step": s, "t": s["t"]} for s in chosen]


def _fact(step: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    """A step with player names, the way the model and the templates see it."""
    out = {k: v for k, v in step.items() if k not in ("x", "y", "end_x", "end_y", "blocker_ids", "keeper")}
    for key in ("player_id", "receiver_id", "nearest_defender_id"):
        if step.get(key):
            out[key.replace("_id", "")] = names.get(step[key], step[key])
            out.pop(key, None)
    if step.get("keeper"):
        out["keeper_off_line_m"] = step["keeper"]["off_line_m"]
    return out


def _quality(xg: float) -> str:
    return "a big chance" if xg >= 0.35 else ("a decent chance" if xg >= 0.15 else "a long shot")


class ExplainAgent(Agent):
    name = "explainer"
    role = "Breaks a moment down step by step for the replay telestrator"
    instructions = (
        "You are a TV football analyst at the telestrator, breaking down a replay. "
        "Write exactly one short spoken line per beat (max 16 words), in the same order, each about only that beat. "
        "Sound like live TV: who, what, and why it matters. At most one number per line, never a list of stats. "
        "Use only the facts given; never invent players, numbers or events. Metres, km/h, xG 0-1. "
        "Reply with a JSON object: {\"headline\": str, \"beats\": {\"1\": str, \"2\": str, ...}, \"verdict\": str}, "
        "with exactly one entry in beats per numbered beat you were given, same numbers. "
        "headline: max 8 words. verdict: one or two sentences on why the move worked or failed (empty for short mode)."
    )

    def _facts(self, bb: ExplainBoard) -> dict[str, Any]:
        m = bb.moment
        return {
            "minute": m["minute"],
            "kind": m["kind"],
            "team": bb.team_names[m["team"]],
            "opponent": bb.team_names["away" if m["team"] == "home" else "home"],
            "score_after": {bb.team_names[k]: v for k, v in m["score_after"].items()},
            "result": self._result(bb),
            "passes_in_move": m["passes"],
            "beats": {str(i + 1): _fact(b["step"], bb.names) for i, b in enumerate(bb.beats)},
        }

    @staticmethod
    def _result(bb: ExplainBoard) -> str:
        """One unambiguous sentence on who did what, so the model can't credit the wrong team."""
        m = bb.moment
        shooter = bb.names.get(m["player_id"], "")
        team = bb.team_names[m["team"]]
        other = bb.team_names["away" if m["team"] == "home" else "home"]
        keeper = bb.names.get(((m["steps"][-1].get("keeper") or {}).get("player_id")) or "", "the keeper")
        return {
            "goal": f"{shooter} scores for {team}.",
            "save": f"{shooter} ({team}) shoots; {keeper}, {other}'s goalkeeper, saves it.",
            "miss": f"{shooter} ({team}) shoots wide; no goal.",
        }[m["kind"]]

    def run_template(self, bb: ExplainBoard) -> None:
        m = bb.moment
        team = bb.team_names[m["team"]]
        lines = []
        for b in bb.beats:
            s = b["step"]
            who = bb.names.get(s.get("player_id") or "", "")
            if s["type"] == "regain":
                how = {"interception": "intercepts", "tackle": "wins the tackle", "kickoff": "kicks off",
                       "goal_kick": "restarts with the goal kick", "save": "claims it", "header": "wins the header"}
                lines.append(f"It starts with {who}: {how.get(s.get('cause') or '', 'wins it')} in {_zone(m['team'], s['x'])}.")
            elif s["type"] == "pass":
                to = bb.names.get(s.get("receiver_id") or "", "a teammate")
                past = f", taking {s['bypassed']} defender{'s' if s['bypassed'] > 1 else ''} out" if s["bypassed"] else ""
                lead = "The key pass: " if s["key_pass"] else ""
                lines.append(f"{lead}{who} finds {to}, {s['length_m']:.0f} metres{past}.")
            else:
                gap = f"nearest defender {s['nearest_defender_m']} m away" if s.get("nearest_defender_m") is not None else "no one close"
                end = {"goal": "and scores", "saved": "and the keeper saves", "off_target": "and it goes wide"}[s["outcome"]]
                lines.append(f"{who} shoots from {s['distance_m']:.0f} metres, xG {s['xg']:.2f}, {gap}, {end}.")
        for b, text in zip(bb.beats, lines):
            b["text"] = text
        shot = m["steps"][-1]
        scorer = bb.names.get(m["player_id"], "")
        headline = {"goal": f"{scorer} scores for {team}", "save": f"{scorer} denied", "miss": f"{scorer} goes close"}[m["kind"]]
        verdict = ""
        if bb.mode == "full":
            reasons = []
            if m["passes"] >= 5:
                reasons.append(f"a patient {m['passes']}-pass move")
            key = next((s for s in m["steps"] if s.get("key_pass")), None)
            if key and key["bypassed"]:
                reasons.append(f"a key pass that took {key['bypassed']} defenders out")
            if (shot.get("nearest_defender_m") or 0) >= 2:
                reasons.append(f"{shot['nearest_defender_m']} m of space at the shot")
            if shot.get("defenders_in_the_way", 0) >= 2:
                reasons.append(f"despite {shot['defenders_in_the_way']} defenders between ball and goal")
            reasons.append(f"{_quality(shot.get('xg') or 0)} (xG {shot.get('xg') or 0:.2f})")
            verdict = "Why: " + ", ".join(reasons) + "."
        bb.output = {"headline": headline, "verdict": verdict, "language": "en"}

    async def run_llm(self, bb: ExplainBoard) -> None:
        facts = self._facts(bb)
        prompt = json.dumps({
            "language": LANGUAGE_NAMES.get(bb.persona.language, "English"),
            "audience": "analyst: tactical terms and numbers" if bb.persona.mode == "analyst" else "casual fan: vivid, plain words",
            "mode": bb.mode,
            "moment": facts,
        }, default=str)
        language = LANGUAGE_NAMES.get(bb.persona.language, "English")
        keys = [str(i + 1) for i in range(len(bb.beats))]
        prompt = f"Write in {language}. Beats to write: {', '.join(keys)}.\n{prompt}"
        for attempt in range(2):  # one retry: a malformed reply is rare with JSON mode, but costs only ~1 s
            try:
                data = json.loads(await self.ask(prompt, max_tokens=420, json_mode=True))
                raw = data.get("beats") or {}
                if isinstance(raw, list):
                    raw = {str(i + 1): v for i, v in enumerate(raw)}
                beats = [str(raw.get(k) or "").strip() for k in keys]
                if not all(beats):
                    raise ValueError(f"missing beats: wanted {keys}, got {sorted(raw)}")
                break
            except (ValueError, AttributeError):  # JSONDecodeError is a ValueError
                if attempt:
                    raise
        for b, line in zip(bb.beats, beats):
            b["text"] = line
        bb.output = {
            "headline": str(data.get("headline") or "").strip(),
            "verdict": str(data.get("verdict") or "").strip() if bb.mode == "full" else "",
            "language": bb.persona.language,
        }


class ProducerAgent(Agent):
    name = "producer"
    role = "Cuts the highlights package: picks the clips, then writes the intro and outro"
    instructions = (
        "You are a football highlights producer. Given the clips of a match (in order) and the score, "
        "write a spoken intro (max 25 words) that sets up the package without giving away the result, and an "
        "outro (max 30 words) that sums up the match. Use only the facts given. "
        "Reply with a JSON object: {\"intro\": str, \"outro\": str}."
    )

    def _facts(self, bb: ExplainBoard) -> dict[str, Any]:
        return bb.moment  # the package: teams, score, clip headlines

    def run_template(self, bb: ExplainBoard) -> None:
        f = bb.moment
        h, a = f["home"], f["away"]
        goals = sum(1 for c in f["clips"] if c["kind"] == "goal")
        intro = f"{h} against {a}: {len(f['clips'])} moments{', ' + str(goals) + ' goals' if goals else ''}. Here's how it unfolded."
        sh, sa = f["score"]["home"], f["score"]["away"]
        state = "Full time" if f["finished"] else f"After {f['minute']} minutes"
        outro = f"{state}: {h} {sh}, {a} {sa}."
        bb.output = {"intro": intro, "outro": outro, "language": "en"}

    async def run_llm(self, bb: ExplainBoard) -> None:
        language = LANGUAGE_NAMES.get(bb.persona.language, "English")
        prompt = f"Write in {language}.\n" + json.dumps({"package": bb.moment}, default=str)
        data = json.loads(await self.ask(prompt, max_tokens=200, json_mode=True))
        if not data.get("intro") or not data.get("outro"):
            raise ValueError("missing intro/outro")
        bb.output = {"intro": str(data["intro"]).strip(), "outro": str(data["outro"]).strip(), "language": bb.persona.language}


def _names(meta) -> dict[str, str]:
    return {p.id: p.name for p in meta.players}


async def explain(llm, meta, moment: dict[str, Any], persona: Persona, mode: str = "full",
                  from_t: float | None = None, agent: ExplainAgent | None = None) -> dict[str, Any]:
    """One moment broken down into beats (with text), headline and verdict, plus the agent trace."""
    bb = ExplainBoard(moment=moment, names=_names(meta), team_names={k: v.name for k, v in meta.teams.items()},
                      persona=persona, mode=mode)
    bb.beats = choose_beats(moment, mode, from_t)
    await run_step(agent or ExplainAgent(llm), bb, timeout=12.0)
    out = bb.output or {}
    return {
        "moment": moment,
        "beats": [{"t": b["t"], "type": b["step"]["type"], "text": b.get("text", "")} for b in bb.beats],
        "headline": out.get("headline", ""),
        "verdict": out.get("verdict", ""),
        "language": out.get("language", "en"),
        "trace": bb.trace,
    }


async def highlights(llm, meta, clips: list[dict[str, Any]], score: dict[str, int], minute: int, finished: bool,
                     persona: Persona) -> dict[str, Any]:
    """Fan out one explainer per clip in parallel, then the producer writes around them."""
    explainer = ExplainAgent(llm)
    items = await asyncio.gather(
        *(explain(llm, meta, c, persona, "short", from_t=c["clip_start"], agent=explainer) for c in clips)
    )
    package = {
        "home": meta.teams["home"].name,
        "away": meta.teams["away"].name,
        "score": score,
        "minute": minute,
        "finished": finished,
        "clips": [{"minute": i["moment"]["minute"], "kind": i["moment"]["kind"], "headline": i["headline"]} for i in items],
    }
    bb = ExplainBoard(moment=package, names={}, team_names={}, persona=persona)
    await run_step(ProducerAgent(llm), bb, timeout=10.0)
    trace = [{**t, "clip": n} for n, item in enumerate(items) for t in item["trace"]] + bb.trace
    return {"intro": bb.output["intro"], "outro": bb.output["outro"], "items": items, "trace": trace,
            "language": bb.output.get("language", "en")}
