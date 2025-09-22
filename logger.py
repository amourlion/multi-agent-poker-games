"""Structured logging helpers for game results."""

from __future__ import annotations

import csv
import json
from typing import Optional

from deck import hand_to_str
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
            fieldnames = [
                "game_id",
                "p1_hand_before",
                "p1_discards",
                "p1_hand_after",
                "p1_rank",
                "p2_hand_before",
                "p2_discards",
                "p2_hand_after",
                "p2_rank",
                "winner",
            ]
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
        player1, player2 = result.players
        winner = (
            "draw"
            if result.winner is None
            else ("p1" if result.winner == 0 else "p2")
        )
        return {
            "game_id": result.game_id,
            "p1_hand_before": " ".join(hand_to_str(player1.hand_before)),
            "p1_discards": json.dumps(player1.decision.discard_indices),
            "p1_hand_after": " ".join(hand_to_str(player1.hand_after)),
            "p1_rank": player1.final_eval.rank_name,
            "p2_hand_before": " ".join(hand_to_str(player2.hand_before)),
            "p2_discards": json.dumps(player2.decision.discard_indices),
            "p2_hand_after": " ".join(hand_to_str(player2.hand_after)),
            "p2_rank": player2.final_eval.rank_name,
            "winner": winner,
        }


__all__ = ["GameLogger"]

