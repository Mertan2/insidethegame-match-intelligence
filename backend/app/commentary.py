"""Live commentary cadence: what the narrator says next, and when.

Every insight (key moments from the analytics plugins, play-by-play / fun facts / recaps from
the director) is offered here. Key moments go straight to the narrator; otherwise the best
waiting brief is picked roughly every LINE_GAP_S of wall-clock time, so commentary is continuous,
paced for a voice to read it, never overlapping, and never about stale play.
"""

from __future__ import annotations

import asyncio
import time

from .plugins import Insight

LINE_GAP_S = 5.0  # wall-clock seconds between routine lines (about one spoken sentence)
KEY_IMPORTANCE = 0.8  # goals, big chances, half/full-time recaps: say them now
MAX_AGE_S = {"play_by_play": 3.0}  # game seconds a brief stays relevant
DEFAULT_MAX_AGE_S = 25.0
RANK = {"fun_fact": 3, "recap": 4, "play_by_play": 1}  # tie-break after importance


class CommentaryScheduler:
    def __init__(self, line_gap_s: float = LINE_GAP_S, clock=time.monotonic):
        self.line_gap_s = line_gap_s
        self.clock = clock
        self.pending: list[Insight] = []
        self.last_line = -1e9
        self.in_flight: asyncio.Task | None = None

    def clear(self) -> None:
        self.pending.clear()

    def started(self, task: asyncio.Task) -> None:
        self.in_flight = task
        self.last_line = self.clock()

    def offer(self, insights: list[Insight], t: float) -> Insight | None:
        """Add this tick's insights; return the one to narrate now, if any."""
        for ins in insights:
            if ins.kind == "play_by_play":  # only the latest view of the pitch matters
                self.pending = [p for p in self.pending if p.kind != "play_by_play"]
            self.pending.append(ins)
        self.pending = [p for p in self.pending if t - p.t <= MAX_AGE_S.get(p.kind, DEFAULT_MAX_AGE_S)]
        if not self.pending:
            return None
        busy = self.in_flight is not None and not self.in_flight.done()
        best = max(self.pending, key=lambda p: (p.importance, RANK.get(p.kind, 2), p.t))
        key = best.importance >= KEY_IMPORTANCE
        if busy or (not key and self.clock() - self.last_line < self.line_gap_s):
            return None
        self.pending.remove(best)
        if key:
            # A key moment supersedes routine chatter that queued up around it.
            self.pending = [p for p in self.pending if p.importance >= KEY_IMPORTANCE or p.kind in ("fun_fact", "recap")]
        return best
