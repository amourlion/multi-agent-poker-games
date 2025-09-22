"""Shared dataclasses describing decisions and contexts."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class DecisionRules:
    """Constraints that govern a player's draw decision."""

    max_discards: int = 5


@dataclass(frozen=True)
class DecisionContext:
    """Runtime context passed to agents when they must decide on a discard."""

    game_id: int
    player_id: int
    rng: random.Random


@dataclass
class DiscardDecision:
    """The result of an agent's draw decision."""

    discard_indices: List[int] = field(default_factory=list)
    rationale: Optional[str] = None


__all__ = [
    "DecisionContext",
    "DecisionRules",
    "DiscardDecision",
]

