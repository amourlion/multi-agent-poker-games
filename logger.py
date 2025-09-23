"""Structured logging helpers for game results."""

from __future__ import annotations

import csv
import json
from typing import Optional

from engine import GameResult


class GameLogger:
    def __init__(self, path: str, *, fmt: str = "jsonl") -> None:
        self.path = path
        self.format = fmt.lower()
        mode = "w"
        newline = "\n" if self.format == "csv" else ""
        self._handle = open(path, mode, encoding="utf-8", newline=newline)
        self._writer: Optional[csv.DictWriter] = None
        if self.format == "csv":
            fieldnames = ["game_id", "pot", "winners", "players"]
            self._writer = csv.DictWriter(self._handle, fieldnames=fieldnames)
            self._writer.writeheader()

    def __enter__(self) -> "GameLogger":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def log(self, result: GameResult) -> None:
        if self.format == "jsonl":
            json.dump(result.to_dict(), self._handle, ensure_ascii=False)
            self._handle.write("\n")
        elif self.format == "csv":
            assert self._writer is not None
            self._writer.writerow(self._as_csv_row(result))
        else:  # pragma: no cover - defensive branch
            raise ValueError(f"Unsupported log format: {self.format}")
        self._handle.flush()

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.close()

    def _as_csv_row(self, result: GameResult) -> dict:
        player_payload = [player.to_dict() for player in result.players]
        winners = ",".join(str(winner) for winner in result.winners) or "none"
        return {
            "game_id": result.game_id,
            "pot": result.pot,
            "winners": winners,
            "players": json.dumps(player_payload, ensure_ascii=False),
        }


__all__ = ["GameLogger"]
