"""Unit tests for hand evaluation and comparison logic."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from deck import hand_from_strs
from hand_eval import HAND_RANKS, compare_hands, evaluate_hand


def make_hand(cards: str):
    tokens = cards.split()
    return hand_from_strs(tokens)


EVALUATION_CASES = [
    ("AS KD QC 7H 4C", "High Card"),
    ("9S 8D 6C 4H 2C", "High Card"),
    ("AH AD 7C 5D 3S", "One Pair"),
    ("KH KD QC 7S 4H", "One Pair"),
    ("QS QH 7D 7C 5S", "Two Pair"),
    ("9S 9D 4C 4H 2S", "Two Pair"),
    ("KH KD KS 9C 4D", "Three of a Kind"),
    ("7S 7D 7C QH 2C", "Three of a Kind"),
    ("5S 4D 3C 2H AD", "Straight"),
    ("TC 9D 8S 7H 6C", "Straight"),
    ("AS QS 9S 5S 2S", "Flush"),
    ("KD QD 9D 6D 3D", "Flush"),
    ("QH QD QS 9C 9S", "Full House"),
    ("6C 6D 6S 3H 3S", "Full House"),
    ("9S 9D 9C 9H 3D", "Four of a Kind"),
    ("5H 5D 5C 5S 2D", "Four of a Kind"),
    ("6S 5S 4S 3S 2S", "Straight Flush"),
    ("TD JD QD KD AD", "Straight Flush"),
]


@pytest.mark.parametrize("cards, expected", EVALUATION_CASES)
def test_evaluate_hand_rank(cards: str, expected: str) -> None:
    hand = make_hand(cards)
    evaluation = evaluate_hand(hand)
    assert HAND_RANKS[evaluation.rank_id] == expected


COMPARISON_CASES = [
    # High card comparisons (5 cases)
    ("AS KD QC 7H 4C", "KS QD JC 9H 3C", 1),
    ("QH JD 9C 6S 4D", "QH JD 8S 6C 5D", 1),
    ("TH 9D 7C 5S 3D", "TH 9D 7C 5S 2D", 1),
    ("9H 8D 6C 4S 2D", "9H 8D 6C 4S 2C", 0),
    ("8H 7D 5C 3S 2D", "9H 7D 5C 3S 2D", -1),
    # One pair comparisons (6 cases)
    ("AH AD 9C 7S 3D", "KH KD QC 7S 4D", 1),
    ("KH KD JC 9S 4D", "KH KD JC 8S 5D", 1),
    ("QH QD JC 9S 4D", "QH QD JC 8S 5D", 1),
    ("JH JD 9C 8S 4D", "JH JD 9C 8S 3D", 1),
    ("TH TD 9C 8S 4D", "JH JD 9C 8S 4D", -1),
    ("8H 8D 7C 6S 4D", "8H 8D 7C 6S 3D", 1),
    # Two pair comparisons (6 cases)
    ("AH AD KH KD 3C", "QH QD JH JD 3C", 1),
    ("KH KD QH QD 3C", "KH KD JH JD 3C", 1),
    ("QH QD JH JD 3C", "QH QD JH JD 2C", 1),
    ("TH TD 9H 9D 4C", "TH TD 8H 8D 4C", 1),
    ("9H 9D 8H 8D 4C", "9H 9D 8H 8D 3C", 1),
    ("7H 7D 6H 6D 4C", "8H 8D 5H 5D 4C", -1),
    # Three of a kind comparisons (5 cases)
    ("AH AD AC 9S 4D", "KH KD KC QS 4D", 1),
    ("KH KD KC QS 4D", "KH KD KC JS 4D", 1),
    ("QH QD QC 9S 4D", "QH QD QC 8S 4D", 1),
    ("JH JD JC 9S 4D", "JH JD JC 9S 3D", 1),
    ("TH TD TC 9S 4D", "JH JD JC 9S 4D", -1),
    # Straight comparisons (5 cases)
    ("5S 4D 3C 2H AD", "6S 5D 4C 3H 2D", -1),
    ("9S 8D 7C 6H 5D", "8S 7D 6C 5H 4D", 1),
    ("TS 9D 8C 7H 6D", "JS TD 9C 8H 7D", -1),
    ("AS KS QS JS TS", "KD QD JD TD 9D", 1),
    ("6S 5D 4C 3H 2D", "6H 5C 4D 3S 2C", 0),
    # Flush comparisons (4 cases)
    ("AS QS 9S 5S 2S", "KS QS 9S 5S 2S", 1),
    ("KS QS 9S 5S 2S", "KS QS 8S 5S 2S", 1),
    ("QS 9S 8S 6S 3S", "QS 9S 7S 6S 3S", 1),
    ("JS 9S 7S 6S 3S", "QS 9S 7S 6S 3S", -1),
    # Full house comparisons (4 cases)
    ("AH AD AC 9S 9D", "KH KD KC 9S 9D", 1),
    ("KH KD KC QS QD", "KH KD KC JS JD", 1),
    ("QH QD QC 8S 8D", "QH QD QC 7S 7D", 1),
    ("JH JD JC 9S 9D", "QH QD QC 9S 9D", -1),
    # Four of a kind comparisons (4 cases)
    ("AH AD AC AS 9D", "KH KD KC KS 9D", 1),
    ("KH KD KC KS 9D", "KH KD KC KS 8D", 1),
    ("QH QD QC QS 9D", "QH QD QC QS 8D", 1),
    ("JH JD JC JS 9D", "QH QD QC QS 9D", -1),
    # Straight flush comparisons (4 cases)
    ("6S 5S 4S 3S 2S", "7H 6H 5H 4H 3H", -1),
    ("9S 8S 7S 6S 5S", "8H 7H 6H 5H 4H", 1),
    ("TS 9S 8S 7S 6S", "TS 9S 8S 7S 6S", 0),
    ("AS KS QS JS TS", "KS QS JS TS 9S", 1),
]


@pytest.mark.parametrize("first, second, expected", COMPARISON_CASES)
def test_compare_hands(first: str, second: str, expected: int) -> None:
    hand_a = make_hand(first)
    hand_b = make_hand(second)
    result = compare_hands(hand_a, hand_b)
    assert result == expected

