"""Replays a stored match as if it were a live feed, with pause/seek/speed control."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from .models import Frame, Match


class ReplayEngine:
    def __init__(self, match: Match, speed: float = 1.0):
        self.match = match
        self.frames = match.frames
        self.dt = 1.0 / match.meta.fps
        self.cursor = 0
        self.speed = 1.0
        self.set_speed(speed)
        self.paused = False
        self._seek_to: int | None = None

    def set_speed(self, speed: float) -> None:
        self.speed = float(min(max(speed, 0.1), 32.0))

    @property
    def pending_seek(self) -> int | None:
        return self._seek_to

    def seek(self, t: float) -> int:
        self._seek_to = max(0, min(len(self.frames) - 1, int(t / self.dt)))
        return self._seek_to

    async def ticks(self) -> AsyncIterator[tuple[Frame, bool]]:
        """Yields (frame, seeked) paced at fps * speed.

        `seeked` is True for the first frame after a seek, so the consumer can rebuild
        derived state. Uses a deadline clock so pacing doesn't drift.
        """
        next_deadline = time.monotonic()
        while self.cursor < len(self.frames) or self._seek_to is not None:
            seeked = False
            if self._seek_to is not None:
                self.cursor, self._seek_to = self._seek_to, None
                seeked = True
                next_deadline = time.monotonic()
            elif self.paused:
                await asyncio.sleep(0.05)
                next_deadline = time.monotonic()
                continue
            frame = self.frames[self.cursor]
            self.cursor += 1
            yield frame, seeked
            next_deadline += self.dt / self.speed
            delay = next_deadline - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                next_deadline = time.monotonic()
                await asyncio.sleep(0)
