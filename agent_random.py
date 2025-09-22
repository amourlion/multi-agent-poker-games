"""Baseline random agent for Five-card draw."""

from __future__ import annotations

from typing import List

from deck import Card
from game_types import DecisionContext, DecisionRules, DiscardDecision


class RandomAgent:
    """Agent that discards up to three random cards."""

    def __init__(self, *, max_discards: int = 3) -> None:
        self._max_discards = max_discards

    def decide_discard(
        self, hand: List[Card], rules: DecisionRules, context: DecisionContext
    ) -> DiscardDecision:
        max_allowed = min(len(hand), rules.max_discards, self._max_discards)
        if max_allowed <= 0:
            return DiscardDecision([])
        count = context.rng.randint(0, max_allowed)
        if count == 0:
            return DiscardDecision([])
        indices = list(range(len(hand)))
        context.rng.shuffle(indices)
        discard = sorted(indices[:count])
        return DiscardDecision(discard, rationale="Random baseline")


__all__ = ["RandomAgent"]

