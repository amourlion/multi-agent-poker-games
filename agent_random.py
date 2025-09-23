"""Baseline random agent for Five-card draw."""

from __future__ import annotations

from typing import List

from deck import Card
from game_types import (
    BetDecision,
    BettingAction,
    BettingContext,
    DecisionContext,
    DecisionRules,
    DiscardDecision,
)


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

    def decide_bet(
        self, hand: List[Card], context: BettingContext
    ) -> BetDecision:
        actions = list(context.available_actions)
        choice = context.rng.choice(actions)

        if choice == BettingAction.CHECK:
            return BetDecision(action=choice, rationale="Random: check")

        if choice == BettingAction.FOLD:
            return BetDecision(action=choice, rationale="Random: fold")

        if choice == BettingAction.CALL:
            amount = min(context.to_call, context.stack)
            return BetDecision(action=choice, amount=amount, rationale="Random: call")

        # Betting or raising: pick smallest legal amount for simplicity
        if choice == BettingAction.BET:
            amount = max(context.min_bet, 0)
            amount = min(amount, context.stack)
            return BetDecision(action=choice, amount=amount, rationale="Random: bet")

        # Raise
        raise_amount = max(context.min_raise, 0)
        target = context.to_call + raise_amount
        target = min(target, context.stack)
        return BetDecision(action=choice, amount=target, rationale="Random: raise")


__all__ = ["RandomAgent"]
