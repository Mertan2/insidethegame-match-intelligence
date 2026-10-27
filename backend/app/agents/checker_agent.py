"""Fact-checker agent: every number in the line on air must come from the stats agent.

Last in the chain. Deliberately deterministic, so it cannot itself invent anything: it pulls
every number out of the final line (any language, Arabic-Indic digits, decimal commas) and
checks each one against the facts the stats agent put on the blackboard, the score and the
match clock. The line goes out either way; the verdict travels with it, so a producer (or the
UI) can see at a glance whether a line is fully grounded.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .base import Agent, Blackboard

# Small whole numbers are counts ("2 shots", "three-pass move") and shirt numbers; not worth flagging.
SMALL = 11
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def numbers_in(text: str) -> list[tuple[str, float]]:
    """(as written, value) for every number in `text`. A comma followed by 1-2 digits is a decimal
    comma (0,56); followed by 3 digits it groups thousands (2,436)."""
    out = []
    for raw in _NUM.findall(text.translate(_DIGITS).replace("٫", ".")):
        s = raw
        if "," in s and "." not in s:
            head, _, tail = s.rpartition(",")
            s = f"{head.replace(',', '')}.{tail}" if len(tail) <= 2 else s.replace(",", "")
        else:
            s = s.replace(",", "")
        if s.count(".") > 1:  # 1.000.000 style grouping
            s = s.replace(".", "")
        try:
            out.append((raw, float(s)))
        except ValueError:
            continue
    return out


def _decimals(written: str) -> int:
    m = re.search(r"[.,](\d{1,2})$", written)
    return len(m.group(1)) if m else 0


def grounded(value: float, written: str, allowed: set[float]) -> bool:
    """`value` is grounded if it is a fact, or a fact rounded to the precision it was written with
    (0.6 for 0.56), or a metres fact said in kilometres (2.4 km for 2436 m)."""
    if value.is_integer() and 0 <= value <= SMALL:
        return True
    tol = 0.5 * 10 ** -_decimals(written) + 1e-9
    for a in allowed:
        if abs(value - a) <= tol or abs(value - round(a)) <= tol:
            return True
        if a >= 100 and abs(value - a / 1000) <= max(tol, 0.051):
            return True
    return False


def allowed_numbers(bb: Blackboard) -> set[float]:
    """Everything the line may quote: the stats agent's moment and facts, the score, the clock."""
    minute = int(bb.t // 60)
    pool = json.dumps(bb.moment or {}, default=str) + json.dumps(bb.score)
    return {v for _, v in numbers_in(pool)} | {float(minute), float(minute + 1)}


class CheckerAgent(Agent):
    name = "checker"
    role = "Fact-checks every number on air against the stats agent's facts"

    async def run(self, bb: Blackboard) -> str:
        self.run_template(bb)
        return "deterministic"

    def run_template(self, bb: Blackboard) -> None:
        if bb.output is None:
            return
        allowed = allowed_numbers(bb)
        found = numbers_in(bb.output.get("text", ""))
        flagged = [w for w, v in found if not grounded(v, w, allowed)]
        check: dict[str, Any] = {"numbers": len(found), "flagged": flagged, "grounded": not flagged}
        bb.output["check"] = check
