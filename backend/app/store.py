"""Generated matches, cached as gzipped JSON under backend/data/ so restarts are instant."""

from __future__ import annotations

import gzip
from pathlib import Path

from .generator import generate_match
from .models import Match

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class MatchStore:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._matches: dict[str, Match] = {}
        for path in sorted(self.data_dir.glob("*.json.gz")):
            match = Match.model_validate_json(gzip.decompress(path.read_bytes()))
            self._matches[match.meta.match_id] = match
        for path in sorted(self.data_dir.glob("*.json")):  # older uncompressed caches
            match = Match.model_validate_json(path.read_text())
            self._matches.setdefault(match.meta.match_id, match)

    def list(self) -> list[dict]:
        return [
            {
                "match_id": m.meta.match_id,
                "seed": m.meta.seed,
                "minutes": m.meta.minutes,
                "home": m.meta.teams["home"].name,
                "away": m.meta.teams["away"].name,
                "final_score": m.meta.final_score,
            }
            for m in self._matches.values()
        ]

    def get(self, match_id: str) -> Match | None:
        return self._matches.get(match_id)

    def generate(self, seed: int, minutes: int) -> Match:
        match_id = f"synthetic-{seed}-{minutes}m"
        if match_id in self._matches:
            return self._matches[match_id]
        match = generate_match(seed=seed, minutes=minutes, match_id=match_id)
        payload = gzip.compress(match.model_dump_json().encode(), compresslevel=6)
        (self.data_dir / f"{match_id}.json.gz").write_bytes(payload)
        self._matches[match_id] = match
        return match
