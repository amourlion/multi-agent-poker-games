"""Shared dataclasses describing decisions, contexts, and betting state."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class DecisionRules:
    """Constraints that govern draw and betting decisions."""

    max_discards: int = 5
    min_bet: int = 10
    ante: int = 0
    max_raises: int = 3


@dataclass(frozen=True)
class DecisionContext:
    """Runtime context passed to agents when they must decide on a discard."""

    game_id: int
    player_id: int
    rng: random.Random


class BettingAction(str, Enum):
    """Legal betting actions available during a round."""

    CHECK = "check"
    BET = "bet"
    CALL = "call"
    RAISE = "raise"
    FOLD = "fold"


@dataclass(frozen=True)
class BettingContext:
    """Context supplied to agents for betting decisions."""

    game_id: int
    player_id: int
    round_id: int
    pot: int
    to_call: int
    current_bet: int
    min_bet: int
    min_raise: int
    stack: int
    committed: int
    available_actions: Tuple[BettingAction, ...]
    rng: random.Random


@dataclass
class BetDecision:
    """The result of an agent's betting decision."""

    action: BettingAction
    amount: int = 0
    rationale: Optional[str] = None


@dataclass
class DiscardDecision:
    """The result of an agent's draw decision."""

    discard_indices: List[int] = field(default_factory=list)
    rationale: Optional[str] = None


__all__ = [
    "DecisionContext",
    "DecisionRules",
    "BettingAction",
    "BettingContext",
    "BetDecision",
    "DiscardDecision",
]
