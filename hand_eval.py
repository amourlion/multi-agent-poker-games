"""Five-card hand evaluation and comparison utilities."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from deck import Card, RANKS


RANK_VALUE = {rank: index for index, rank in enumerate(RANKS, start=2)}
HAND_RANKS: Sequence[str] = (
    "High Card",
    "One Pair",
    "Two Pair",
    "Three of a Kind",
    "Straight",
    "Flush",
    "Full House",
    "Four of a Kind",
    "Straight Flush",
)


@dataclass(frozen=True)
class HandEvaluation:
    """Represents the evaluated strength of a five-card hand."""

    rank_id: int
    tiebreak: Tuple[int, ...]

    @property
    def rank_name(self) -> str:
        return HAND_RANKS[self.rank_id]


def _sorted_ranks(cards: Sequence[Card]) -> List[int]:
    values = sorted((RANK_VALUE[card.rank] for card in cards), reverse=True)
    return values


def _is_straight(values: Sequence[int]) -> Tuple[bool, int]:
    unique = sorted(set(values))
    if len(unique) != 5:
        return False, 0
    high = max(unique)
    low = min(unique)
    if high - low == 4:
        return True, high
    # Wheel straight A-2-3-4-5
    if set(unique) == {14, 5, 4, 3, 2}:
        return True, 5
    return False, 0


def evaluate_hand(cards: Sequence[Card]) -> HandEvaluation:
    if len(cards) != 5:
        raise ValueError("Five-card evaluation requires exactly 5 cards")
    values = _sorted_ranks(cards)
    counts = Counter(values)
    by_count = sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))
    suits = {card.suit for card in cards}
    is_flush = len(suits) == 1
    is_straight, straight_high = _is_straight(values)

    if is_straight and is_flush:
        return HandEvaluation(8, (straight_high,))

    if by_count[0][1] == 4:
        four = by_count[0][0]
        kicker = by_count[1][0]
        return HandEvaluation(7, (four, kicker))

    if by_count[0][1] == 3 and by_count[1][1] == 2:
        triple = by_count[0][0]
        pair = by_count[1][0]
        return HandEvaluation(6, (triple, pair))

    if is_flush:
        return HandEvaluation(5, tuple(values))

    if is_straight:
        return HandEvaluation(4, (straight_high,))

    if by_count[0][1] == 3:
        triple = by_count[0][0]
        kickers = [kv[0] for kv in by_count[1:]]
        return HandEvaluation(3, (triple, *kickers))

    if by_count[0][1] == 2 and by_count[1][1] == 2:
        pair_high, pair_low = by_count[0][0], by_count[1][0]
        kicker = by_count[2][0]
        return HandEvaluation(2, (pair_high, pair_low, kicker))

    if by_count[0][1] == 2:
        pair = by_count[0][0]
        kickers = [kv[0] for kv in by_count[1:]]
        return HandEvaluation(1, (pair, *kickers))

    return HandEvaluation(0, tuple(values))


def compare_hands(hand_a: Sequence[Card], hand_b: Sequence[Card]) -> int:
    eval_a = evaluate_hand(hand_a)
    eval_b = evaluate_hand(hand_b)
    if eval_a.rank_id != eval_b.rank_id:
        return (eval_a.rank_id > eval_b.rank_id) - (eval_a.rank_id < eval_b.rank_id)
    if eval_a.tiebreak != eval_b.tiebreak:
        return (eval_a.tiebreak > eval_b.tiebreak) - (eval_a.tiebreak < eval_b.tiebreak)
    return 0


def describe_hand(hand: Sequence[Card]) -> str:
    evaluation = evaluate_hand(hand)
    cards = " ".join(str(card) for card in hand)
    return f"{cards} ({evaluation.rank_name})"


__all__ = [
    "HAND_RANKS",
    "HandEvaluation",
    "compare_hands",
    "describe_hand",
    "evaluate_hand",
]

