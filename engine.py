"""Game engine orchestrating two-player Five-card draw matches."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, List, Optional

from deck import Card, Deck, hand_to_str
from game_types import DecisionContext, DecisionRules, DiscardDecision
from hand_eval import HandEvaluation, compare_hands, evaluate_hand


def _rank_value(rank: str) -> int:
    order = "23456789TJQKA"
    return order.index(rank) + 2


def _conservative_fallback(hand: List[Card], rules: DecisionRules) -> DiscardDecision:
    max_allowed = min(rules.max_discards, 3)
    if max_allowed <= 0:
        return DiscardDecision([])
    values = [_rank_value(card.rank) for card in hand]
    counts = {value: values.count(value) for value in set(values)}
    keep_indices = {
        index for index, value in enumerate(values) if counts[value] >= 2
    }
    discard_candidates = [
        (values[index], index) for index in range(len(hand)) if index not in keep_indices
    ]
    discard_candidates.sort()
    chosen = [index for _, index in discard_candidates[:max_allowed]]
    return DiscardDecision(sorted(chosen), rationale="Engine fallback: keep pairs")


def _validate_decision(decision: DiscardDecision, hand_size: int, rules: DecisionRules) -> bool:
    indices = decision.discard_indices
    if len(indices) > rules.max_discards:
        return False
    if len(set(indices)) != len(indices):
        return False
    return all(0 <= index < hand_size for index in indices)


def _apply_discard(hand: List[Card], discard_indices: Iterable[int], deck: Deck) -> List[Card]:
    discard_set = set(discard_indices)
    keep = [card for idx, card in enumerate(hand) if idx not in discard_set]
    drawn = deck.draw(len(discard_set)) if discard_set else []
    return keep + drawn


@dataclass
class PlayerResult:
    player_id: int
    hand_before: List[Card]
    hand_after: List[Card]
    decision: DiscardDecision
    initial_eval: HandEvaluation
    final_eval: HandEvaluation

    def to_dict(self) -> dict:
        return {
            "hand_before": hand_to_str(self.hand_before),
            "hand_after": hand_to_str(self.hand_after),
            "discard_indices": list(self.decision.discard_indices),
            "rationale": self.decision.rationale,
            "initial_rank": self.initial_eval.rank_name,
            "final_rank": self.final_eval.rank_name,
        }


@dataclass
class GameResult:
    game_id: int
    players: List[PlayerResult]
    winner: Optional[int]

    @property
    def is_draw(self) -> bool:
        return self.winner is None

    def to_dict(self) -> dict:
        payload = {
            "game_id": self.game_id,
            "winner": self.winner,
            "draw": self.is_draw,
        }
        for idx, player in enumerate(self.players, start=1):
            payload[f"p{idx}"] = player.to_dict()
        return payload


class FiveCardDrawEngine:
    """Engine coordinating two-player Five-card draw with logging support."""

    def __init__(self, agent_a, agent_b, *, rng: Optional[random.Random] = None) -> None:
        self.agents = [agent_a, agent_b]
        self.rng = rng or random.Random()

    def play_game(self, game_id: int, rules: Optional[DecisionRules] = None) -> GameResult:
        rules = rules or DecisionRules()
        deck = Deck(rng=self.rng)
        deck.shuffle()
        hands = deck.deal(2, 5)
        players: List[PlayerResult] = []

        for player_id, (agent, initial_hand) in enumerate(zip(self.agents, hands)):
            context = DecisionContext(game_id=game_id, player_id=player_id, rng=self.rng)
            hand_before = list(initial_hand)
            initial_eval = evaluate_hand(hand_before)
            decision = self._obtain_decision(agent, hand_before, rules, context)
            hand_after = _apply_discard(hand_before, decision.discard_indices, deck)
            final_eval = evaluate_hand(hand_after)
            players.append(
                PlayerResult(
                    player_id=player_id,
                    hand_before=hand_before,
                    hand_after=hand_after,
                    decision=decision,
                    initial_eval=initial_eval,
                    final_eval=final_eval,
                )
            )

        comparison = compare_hands(players[0].hand_after, players[1].hand_after)
        if comparison > 0:
            winner: Optional[int] = 0
        elif comparison < 0:
            winner = 1
        else:
            winner = None
        return GameResult(game_id=game_id, players=players, winner=winner)

    def _obtain_decision(
        self,
        agent,
        hand: List[Card],
        rules: DecisionRules,
        context: DecisionContext,
    ) -> DiscardDecision:
        try:
            decision = agent.decide_discard(hand, rules, context)
        except Exception:
            decision = None
        if not isinstance(decision, DiscardDecision):
            decision = DiscardDecision([])
        if not _validate_decision(decision, len(hand), rules):
            decision = _conservative_fallback(hand, rules)
        decision.discard_indices.sort()
        return decision


__all__ = ["FiveCardDrawEngine", "GameResult", "PlayerResult"]

