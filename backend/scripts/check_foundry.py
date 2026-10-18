"""Live check against a real Foundry / Azure OpenAI deployment.

Usage (from backend/):  .venv/bin/python scripts/check_foundry.py [--env-file .env]

1. One raw FoundryLLM completion.
2. One narration per language (en, tr, es) through the Agent Framework workflow, printing the trace.
Exits non-zero if any LLM agent fell back to its template or a translation stayed English.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from app.agents import Orchestrator, Persona, get_llm  # noqa: E402
from app.agents.llm import FoundryLLM  # noqa: E402
from app.generator import generate_match  # noqa: E402
from app.plugins import Insight  # noqa: E402


async def main(env_file: str) -> int:
    load_dotenv(env_file)
    llm = get_llm()
    if not isinstance(llm, FoundryLLM):
        print("AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY / AZURE_OPENAI_DEPLOYMENT not set")
        return 2
    print("deployment url:", llm.url)
    print("raw:", await llm.complete("Reply with exactly: pong", "ping", max_tokens=10))

    match = generate_match(seed=3, minutes=6)
    player = match.meta.players[9]
    insight = Insight(t=600.0, kind="big_chance", importance=0.75, source="stats", team="home", player_id=player.id,
                      headline="Big chance", data={"xg": 0.42, "outcome": "saved", "distance": 9.5})
    ok = True
    for lang in ("en", "tr", "es"):
        orch = Orchestrator(match.meta, llm)
        out = await orch.narrate(600.0, {"home": 0, "away": 0}, [insight], {}, Persona(mode="analyst", language=lang))
        print(f"\n[{lang}] {out['text']}")
        for step in out["trace"]:
            print("   ", step)
        paths = {s["agent"]: s.get("path") for s in out["trace"] if "path" in s}
        ok &= all(paths[a] == "llm" for a in ("tactics", "narrator", "persona")) and out["language"] == lang
    print("\nPASS" if ok else "\nFAIL: an agent fell back to its template (see trace)")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", default=".env")
    sys.exit(asyncio.run(main(ap.parse_args().env_file)))
