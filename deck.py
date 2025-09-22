"""Utilities for working with a standard 52-card deck."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence


RANKS: Sequence[str] = tuple("23456789TJQKA")
SUITS: Sequence[str] = tuple("SHDC")  # Spades, Hearts, Diamonds, Clubs


@dataclass(frozen=True)
class Card:
    """Representation of a single playing card."""

    rank: str
    suit: str

    def __post_init__(self) -> None:  # pragma: no cover - trivial dataclass validation
        if self.rank not in RANKS:
            raise ValueError(f"Unknown rank: {self.rank}")
        if self.suit not in SUITS:
            raise ValueError(f"Unknown suit: {self.suit}")

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"


def card_from_str(card: str) -> Card:
    """Create a :class:`Card` from a compact string representation."""

    if len(card) != 2:
        raise ValueError(f"Card string must be length 2, got {card!r}")
    return Card(rank=card[0], suit=card[1])


def hand_from_strs(cards: Iterable[str]) -> List[Card]:
    """Parse multiple card strings into a list of :class:`Card` objects."""

    return [card_from_str(token) for token in cards]


def hand_to_str(hand: Sequence[Card]) -> List[str]:
    """Convert a hand to its string representation."""

    return [str(card) for card in hand]


class Deck:
    """A standard 52-card deck with deterministic shuffling support."""

    def __init__(self, *, rng=None) -> None:
        import random

        self._rng = rng or random.Random()
        self._cards: List[Card] = []
        self.reset()

    def reset(self) -> None:
        """Reset the deck to an ordered set of 52 cards."""

        self._cards = [Card(rank, suit) for suit in SUITS for rank in RANKS]

    def shuffle(self) -> None:
        """Shuffle the deck in-place using the configured RNG."""

        self._rng.shuffle(self._cards)

    def draw(self, count: int = 1) -> List[Card]:
        """Draw ``count`` cards from the top of the deck."""

        if count < 0:
            raise ValueError("count must be non-negative")
        if count > len(self._cards):
            raise ValueError("Not enough cards remaining in the deck")
        drawn = self._cards[:count]
        self._cards = self._cards[count:]
        return list(drawn)

    def remaining(self) -> int:
        """Return the number of cards left in the deck."""

        return len(self._cards)

    def deal(self, num_players: int, cards_per_player: int) -> List[List[Card]]:
        """Deal ``cards_per_player`` cards to ``num_players`` players."""

        if num_players <= 0:
            raise ValueError("num_players must be positive")
        if cards_per_player <= 0:
            raise ValueError("cards_per_player must be positive")
        total_needed = num_players * cards_per_player
        if total_needed > len(self._cards):
            raise ValueError("Not enough cards to deal")
        hands = []
        for _ in range(num_players):
            hands.append(self.draw(cards_per_player))
        return hands


__all__ = [
    "Card",
    "Deck",
    "RANKS",
    "SUITS",
    "card_from_str",
    "hand_from_strs",
    "hand_to_str",
]

