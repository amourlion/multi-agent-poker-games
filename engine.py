"""Game engine orchestrating multi-agent Five-card draw matches with betting."""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Optional, Sequence

from deck import Card, Deck, hand_to_str
from game_types import (
    BetDecision,
    BettingAction,
    BettingContext,
    DecisionContext,
    DecisionRules,
    DiscardDecision,
)
from hand_eval import HandEvaluation, compare_hands, evaluate_hand


def _rank_value(rank: str) -> int:
    order = "23456789TJQKA"
    return order.index(rank) + 2


def _conservative_fallback(hand: List[Card], rules: DecisionRules) -> DiscardDecision:
    max_allowed = min(rules.max_discards, 3)
    if max_allowed <= 0:
        return DiscardDecision([])
    values = [_rank_value(card.rank) for card in hand]
    counts: Dict[int, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    keep_indices = {
        index for index, value in enumerate(values) if counts[value] >= 2
    }
    discard_candidates = [
        (values[index], index) for index in range(len(hand)) if index not in keep_indices
    ]
    discard_candidates.sort()
    chosen = [index for _, index in discard_candidates[:max_allowed]]
    return DiscardDecision(sorted(chosen), rationale="Fallback: keep made pairs")


def _apply_discard(hand: List[Card], discard_indices: Iterable[int], deck: Deck) -> List[Card]:
    discard_set = set(discard_indices)
    keep = [card for idx, card in enumerate(hand) if idx not in discard_set]
    drawn = deck.draw(len(discard_set)) if discard_set else []
    return keep + drawn


@dataclass
class BettingEvent:
    action: BettingAction
    amount: int
    rationale: Optional[str]
    pot_after: int
    stack_after: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "amount": self.amount,
            "rationale": self.rationale,
            "pot_after": self.pot_after,
            "stack_after": self.stack_after,
        }


@dataclass
class PlayerResult:
    player_id: int
    name: str
    hand_before: List[Card]
    hand_after: List[Card]
    decision: DiscardDecision
    initial_eval: HandEvaluation
    final_eval: Optional[HandEvaluation]
    folded: bool
    initial_stack: int
    final_stack: int
    stack_change: int
    betting_history: List[BettingEvent]

    def to_dict(self) -> dict:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "hand_before": hand_to_str(self.hand_before),
            "hand_after": hand_to_str(self.hand_after),
            "discard_indices": list(self.decision.discard_indices),
            "rationale": self.decision.rationale,
            "initial_rank": self.initial_eval.rank_name,
            "final_rank": self.final_eval.rank_name if self.final_eval else None,
            "folded": self.folded,
            "initial_stack": self.initial_stack,
            "final_stack": self.final_stack,
            "stack_change": self.stack_change,
            "betting_history": [event.to_dict() for event in self.betting_history],
        }


@dataclass
class GameResult:
    game_id: int
    players: List[PlayerResult]
    pot: int
    winners: List[int]
    bankrolls: Dict[int, int]

    @property
    def winner(self) -> Optional[int]:
        if len(self.winners) == 1:
            return self.winners[0]
        return None

    @property
    def is_draw(self) -> bool:
        return len(self.winners) > 1

    def to_dict(self) -> dict:
        payload = {
            "game_id": self.game_id,
            "pot": self.pot,
            "winners": self.winners,
            "bankrolls": self.bankrolls,
        }
        payload["players"] = [player.to_dict() for player in self.players]
        return payload


@dataclass
class PlayerSeat:
    player_id: int
    name: str
    agent: Any
    stack: int


@dataclass
class _RoundPlayer:
    seat: PlayerSeat
    hand: List[Card]
    starting_stack: int
    current_bet: int = 0
    committed: int = 0
    folded: bool = False
    all_in: bool = False
    betting_history: List[BettingEvent] = field(default_factory=list)
    discard_decision: DiscardDecision = field(default_factory=DiscardDecision)
    hand_after: List[Card] = field(default_factory=list)
    initial_eval: Optional[HandEvaluation] = None
    final_eval: Optional[HandEvaluation] = None

    @property
    def player_id(self) -> int:
        return self.seat.player_id


class FiveCardDrawEngine:
    """Engine coordinating multi-agent Five-card draw with betting support."""

    def __init__(self, players: Sequence[PlayerSeat], *, rng: Optional[random.Random] = None) -> None:
        if len(players) < 2:
            raise ValueError("At least two players are required")
        self.rng = rng or random.Random()
        self._seats: List[PlayerSeat] = [
            replace(player, player_id=index) for index, player in enumerate(players)
        ]

    def play_game(self, game_id: int, rules: Optional[DecisionRules] = None) -> GameResult:
        rules = rules or DecisionRules()
        active_seats = [seat for seat in self._seats if seat.stack > 0]
        if len(active_seats) < 2:
            bankrolls = {seat.player_id: seat.stack for seat in self._seats}
            return GameResult(game_id=game_id, players=[], pot=0, winners=[], bankrolls=bankrolls)

        deck = Deck(rng=self.rng)
        deck.shuffle()

        hands = deck.deal(len(active_seats), 5)
        round_players: List[_RoundPlayer] = []
        pot = 0

        for seat, hand in zip(active_seats, hands):
            player = _RoundPlayer(
                seat=seat,
                hand=list(hand),
                hand_after=list(hand),
                starting_stack=seat.stack,
                current_bet=0,
                committed=0,
                folded=False,
                all_in=False,
                initial_eval=evaluate_hand(list(hand)),
            )
            if rules.ante > 0 and seat.stack > 0:
                ante = min(rules.ante, seat.stack)
                seat.stack -= ante
                player.current_bet += ante
                player.committed += ante
                pot += ante
                player.betting_history.append(
                    BettingEvent(
                        action=BettingAction.BET,
                        amount=ante,
                        rationale="Ante",
                        pot_after=pot,
                        stack_after=seat.stack,
                    )
                )
                if seat.stack == 0:
                    player.all_in = True
            round_players.append(player)

        pot = self._betting_round(round_players, rules, game_id, pot)

        active_after_bet = [p for p in round_players if not p.folded]
        if len(active_after_bet) == 1:
            winners = [active_after_bet[0]]
        else:
            for player in active_after_bet:
                context = DecisionContext(game_id=game_id, player_id=player.player_id, rng=self.rng)
                decision = self._obtain_discard(player.seat.agent, player.hand_after, rules, context)
                player.discard_decision = decision
                player.hand_after = _apply_discard(player.hand_after, decision.discard_indices, deck)
                player.final_eval = evaluate_hand(player.hand_after)

            winners = self._determine_winners([p for p in round_players if not p.folded])

        if len(winners) > 0:
            share, remainder = divmod(pot, len(winners))
            remaining = pot
            for idx, player in enumerate(winners):
                payout = share + (1 if idx < remainder else 0)
                player.seat.stack += payout
                remaining -= payout
                player.betting_history.append(
                    BettingEvent(
                        action=BettingAction.CALL,
                        amount=payout,
                        rationale="Payout",
                        pot_after=max(remaining, 0),
                        stack_after=player.seat.stack,
                    )
                )
                player.final_eval = player.final_eval or player.initial_eval
        else:
            # No winners implies everyone folded? Nothing to distribute.
            winners = []

        players_result: List[PlayerResult] = []
        for player in round_players:
            final_eval = player.final_eval if not player.folded else None
            result = PlayerResult(
                player_id=player.player_id,
                name=player.seat.name,
                hand_before=player.hand,
                hand_after=player.hand_after,
                decision=player.discard_decision,
                initial_eval=player.initial_eval,
                final_eval=final_eval,
                folded=player.folded,
                initial_stack=player.starting_stack,
                final_stack=player.seat.stack,
                stack_change=player.seat.stack - player.starting_stack,
                betting_history=player.betting_history,
            )
            players_result.append(result)

        bankrolls = {seat.player_id: seat.stack for seat in self._seats}
        winner_ids = [player.player_id for player in winners]
        return GameResult(
            game_id=game_id,
            players=players_result,
            pot=pot,
            winners=winner_ids,
            bankrolls=bankrolls,
        )

    def _available_actions(
        self,
        player: _RoundPlayer,
        to_call: int,
        rules: DecisionRules,
        raises: int,
    ) -> List[BettingAction]:
        if player.folded:
            return []
        actions: List[BettingAction] = []
        if to_call <= 0:
            actions.append(BettingAction.CHECK)
            if player.seat.stack > 0 and rules.min_bet > 0:
                actions.append(BettingAction.BET)
        else:
            if player.seat.stack > 0:
                actions.append(BettingAction.CALL)
                if (
                    player.seat.stack > to_call
                    and player.seat.stack - to_call >= rules.min_bet
                    and raises < rules.max_raises
                ):
                    actions.append(BettingAction.RAISE)
            actions.append(BettingAction.FOLD)
            if player.seat.stack <= to_call:
                actions = [action for action in actions if action != BettingAction.RAISE]
        if not actions and to_call <= 0:
            actions.append(BettingAction.CHECK)
        if BettingAction.CALL not in actions and to_call > 0 and player.seat.stack > 0:
            actions.append(BettingAction.CALL)
        if BettingAction.FOLD not in actions and to_call > 0:
            actions.append(BettingAction.FOLD)
        return actions

    def _betting_round(
        self,
        players: List[_RoundPlayer],
        rules: DecisionRules,
        game_id: int,
        pot: int,
    ) -> int:
        current_bet = max((p.current_bet for p in players), default=0)
        raises = 0
        players_needed = {
            player.player_id
            for player in players
            if not player.folded and not player.all_in
        }
        index = 0
        total_players = len(players)

        def active_non_folded() -> int:
            return sum(1 for p in players if not p.folded)

        while players_needed and active_non_folded() > 1:
            player = players[index % total_players]
            index += 1
            if player.folded or player.all_in:
                players_needed.discard(player.player_id)
                continue

            to_call = max(0, current_bet - player.current_bet)
            available_actions = self._available_actions(player, to_call, rules, raises)
            if not available_actions:
                players_needed.discard(player.player_id)
                continue

            context = BettingContext(
                game_id=game_id,
                player_id=player.player_id,
                round_id=0,
                pot=pot,
                to_call=to_call,
                current_bet=current_bet,
                min_bet=rules.min_bet,
                min_raise=rules.min_bet,
                stack=player.seat.stack,
                committed=player.current_bet,
                available_actions=tuple(available_actions),
                rng=self.rng,
            )
            decision = self._obtain_bet(player.seat.agent, player.hand_after, context)
            decision = self._normalize_bet(decision, context)
            action = decision.action
            amount = decision.amount if decision.amount else 0

            if action == BettingAction.CHECK:
                player.betting_history.append(
                    BettingEvent(action, 0, decision.rationale, pot, player.seat.stack)
                )
                players_needed.discard(player.player_id)
                continue

            if action == BettingAction.FOLD:
                player.folded = True
                player.betting_history.append(
                    BettingEvent(action, 0, decision.rationale, pot, player.seat.stack)
                )
                players_needed.discard(player.player_id)
                if active_non_folded() <= 1:
                    break
                continue

            if action == BettingAction.BET:
                pay = min(max(amount, rules.min_bet), player.seat.stack)
                if pay <= 0:
                    pay = min(player.seat.stack, rules.min_bet)
                player.seat.stack -= pay
                player.current_bet += pay
                player.committed += pay
                pot += pay
                current_bet = player.current_bet
                raises = 1
                player.betting_history.append(
                    BettingEvent(action, pay, decision.rationale, pot, player.seat.stack)
                )
                players_needed = {
                    p.player_id
                    for p in players
                    if not p.folded and not p.all_in and p.player_id != player.player_id
                }
                if player.seat.stack == 0:
                    player.all_in = True
                continue

            if action == BettingAction.CALL:
                pay = min(max(amount, to_call), player.seat.stack)
                player.seat.stack -= pay
                player.current_bet += pay
                player.committed += pay
                pot += pay
                if player.current_bet < current_bet:
                    player.all_in = True
                player.betting_history.append(
                    BettingEvent(action, pay, decision.rationale, pot, player.seat.stack)
                )
                players_needed.discard(player.player_id)
                continue

            if action == BettingAction.RAISE:
                minimum_total = to_call + rules.min_bet
                pay = min(max(amount, minimum_total), player.seat.stack)
                player.seat.stack -= pay
                player.current_bet += pay
                player.committed += pay
                pot += pay
                current_bet = player.current_bet
                raises += 1
                player.betting_history.append(
                    BettingEvent(action, pay, decision.rationale, pot, player.seat.stack)
                )
                players_needed = {
                    p.player_id
                    for p in players
                    if not p.folded and not p.all_in and p.player_id != player.player_id
                }
                if player.seat.stack == 0:
                    player.all_in = True
                continue

        return pot

    def _determine_winners(self, players: List[_RoundPlayer]) -> List[_RoundPlayer]:
        if not players:
            return []
        contenders = [player for player in players if not player.folded]
        if not contenders:
            return []
        best = contenders[0]
        winners = [best]
        for player in contenders[1:]:
            comparison = compare_hands(player.hand_after, winners[0].hand_after)
            if comparison > 0:
                winners = [player]
            elif comparison == 0:
                winners.append(player)
        return winners

    def _obtain_discard(
        self,
        agent: Any,
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
        indices = list(decision.discard_indices)
        indices.sort()
        if not self._validate_discard(indices, len(hand), rules):
            decision = _conservative_fallback(hand, rules)
        else:
            decision.discard_indices = indices
        return decision

    def _validate_discard(self, indices: List[int], hand_size: int, rules: DecisionRules) -> bool:
        if any(idx < 0 or idx >= hand_size for idx in indices):
            return False
        if len(set(indices)) != len(indices):
            return False
        if len(indices) > rules.max_discards:
            return False
        return True

    def _obtain_bet(
        self,
        agent: Any,
        hand: List[Card],
        context: BettingContext,
    ) -> BetDecision:
        decision: Optional[BetDecision] = None
        method = getattr(agent, "decide_bet", None)
        if callable(method):
            try:
                decision = method(hand, context)
            except Exception:
                decision = None
        if not isinstance(decision, BetDecision):
            decision = self._default_bet_decision(context)
        return decision

    def _default_bet_decision(self, context: BettingContext) -> BetDecision:
        actions = set(context.available_actions)
        if BettingAction.CHECK in actions:
            return BetDecision(BettingAction.CHECK)
        if BettingAction.CALL in actions:
            return BetDecision(BettingAction.CALL, min(context.to_call, context.stack))
        if BettingAction.BET in actions:
            return BetDecision(BettingAction.BET, min(context.min_bet, context.stack))
        if BettingAction.RAISE in actions:
            return BetDecision(
                BettingAction.RAISE,
                min(context.to_call + context.min_raise, context.stack),
            )
        return BetDecision(BettingAction.FOLD)

    def _normalize_bet(self, decision: BetDecision, context: BettingContext) -> BetDecision:
        if decision.action not in context.available_actions:
            return self._default_bet_decision(context)
        action = decision.action
        amount = max(decision.amount, 0)
        if action in {BettingAction.CHECK, BettingAction.FOLD}:
            return BetDecision(action, 0, decision.rationale)
        if action == BettingAction.CALL:
            amount = min(max(amount, context.to_call), context.stack)
            return BetDecision(action, amount, decision.rationale)
        if action == BettingAction.BET:
            minimum = min(context.stack, max(context.min_bet, 1))
            amount = min(max(amount, minimum), context.stack)
            return BetDecision(action, amount, decision.rationale)
        if action == BettingAction.RAISE:
            minimum_total = context.to_call + max(context.min_raise, 1)
            amount = min(max(amount, minimum_total), context.stack)
            return BetDecision(action, amount, decision.rationale)
        return decision


__all__ = [
    "FiveCardDrawEngine",
    "GameResult",
    "PlayerResult",
    "PlayerSeat",
    "BettingEvent",
]
