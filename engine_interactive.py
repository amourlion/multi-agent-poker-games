"""Interactive Five-card draw engine suitable for human-in-the-loop play."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from deck import Card, Deck
from engine import BettingEvent, GameResult, PlayerResult, PlayerSeat
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


def _validate_discard(indices: Iterable[int], hand_size: int, rules: DecisionRules) -> bool:
    seen = set()
    count = 0
    for index in indices:
        if not isinstance(index, int):
            return False
        if index < 0 or index >= hand_size:
            return False
        if index in seen:
            return False
        seen.add(index)
        count += 1
    return count <= rules.max_discards


def _apply_discard(hand: List[Card], discard_indices: Iterable[int], deck: Deck) -> List[Card]:
    discard_set = set(discard_indices)
    keep = [card for idx, card in enumerate(hand) if idx not in discard_set]
    drawn = deck.draw(len(discard_set)) if discard_set else []
    return keep + drawn


def _available_actions(
    player: "_RoundPlayer",
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


@dataclass
class InteractiveEvent:
    """Represents a single event emitted from an interactive hand."""

    type: str
    payload: Dict[str, object]


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


class InteractiveHand:
    """Represents a single hand in progress."""

    PHASE_BETTING = "betting"
    PHASE_DRAW = "draw"
    PHASE_SHOWDOWN = "showdown"
    PHASE_COMPLETE = "complete"

    def __init__(
        self,
        engine: "InteractiveFiveCardDrawEngine",
        game_id: int,
        seats: Sequence[PlayerSeat],
    ) -> None:
        self._engine = engine
        self.game_id = game_id
        self.rules = engine.rules
        self.rng = engine.rng
        self.deck = Deck(rng=self.rng)
        self.deck.shuffle()
        hands = self.deck.deal(len(seats), 5)
        self.players: List[_RoundPlayer] = []
        self.pot = 0
        self.events: List[InteractiveEvent] = []

        for seat, hand in zip(seats, hands):
            player = _RoundPlayer(
                seat=seat,
                hand=list(hand),
                hand_after=list(hand),
                starting_stack=seat.stack,
                initial_eval=evaluate_hand(list(hand)),
            )
            if self.rules.ante > 0 and seat.stack > 0:
                ante = min(self.rules.ante, seat.stack)
                seat.stack -= ante
                player.current_bet += ante
                player.committed += ante
                self.pot += ante
                player.betting_history.append(
                    BettingEvent(
                        action=BettingAction.BET,
                        amount=ante,
                        rationale="Ante",
                        pot_after=self.pot,
                        stack_after=seat.stack,
                    )
                )
                if seat.stack == 0:
                    player.all_in = True
            self.players.append(player)

        self.phase = self.PHASE_BETTING
        self._current_bet = max((p.current_bet for p in self.players), default=0)
        self._raises = 0
        self._players_needed = {
            player.player_id
            for player in self.players
            if not player.folded and not player.all_in
        }
        self._turn_index = 0
        self.events.append(
            InteractiveEvent(
                "hand_start",
                {
                    "game_id": game_id,
                    "players": [
                        {
                            "player_id": player.player_id,
                            "hand": [str(card) for card in player.hand],
                            "stack": player.seat.stack,
                        }
                        for player in self.players
                    ],
                    "pot": self.pot,
                },
            )
        )

    # ------------------------------------------------------------------
    # Betting helpers
    # ------------------------------------------------------------------

    def current_actor(self) -> Optional[_RoundPlayer]:
        if self.phase != self.PHASE_BETTING:
            return None
        total = len(self.players)
        for _ in range(total):
            player = self.players[self._turn_index % total]
            self._turn_index += 1
            if player.folded or player.all_in:
                self._players_needed.discard(player.player_id)
                continue
            if player.player_id not in self._players_needed:
                continue
            return player
        return None

    def peek_current_actor(self) -> Optional[_RoundPlayer]:
        if self.phase != self.PHASE_BETTING:
            return None
        total = len(self.players)
        idx = self._turn_index
        needed = set(self._players_needed)
        for _ in range(total):
            player = self.players[idx % total]
            idx += 1
            if player.folded or player.all_in:
                needed.discard(player.player_id)
                continue
            if player.player_id not in needed:
                continue
            return player
        return None

    def betting_context(self, player: _RoundPlayer) -> BettingContext:
        to_call = max(0, self._current_bet - player.current_bet)
        available = _available_actions(player, to_call, self.rules, self._raises)
        return BettingContext(
            game_id=self.game_id,
            player_id=player.player_id,
            round_id=0,
            pot=self.pot,
            to_call=to_call,
            current_bet=self._current_bet,
            min_bet=self.rules.min_bet,
            min_raise=self.rules.min_bet,
            stack=player.seat.stack,
            committed=player.current_bet,
            available_actions=tuple(available),
            rng=self.rng,
        )

    def apply_bet_decision(
        self, player: _RoundPlayer, decision: BetDecision
    ) -> InteractiveEvent:
        context = self.betting_context(player)
        if decision.action not in context.available_actions:
            raise ValueError("Illegal betting action")
        action = decision.action
        amount = max(decision.amount or 0, 0)
        to_call = context.to_call
        if action == BettingAction.CHECK:
            self._players_needed.discard(player.player_id)
            event = BettingEvent(action, 0, decision.rationale, self.pot, player.seat.stack)
            player.betting_history.append(event)
            self.events.append(
                InteractiveEvent(
                    "bet",
                    {
                        "player_id": player.player_id,
                        "action": action.value,
                        "amount": 0,
                        "pot": self.pot,
                        "stack": player.seat.stack,
                    },
                )
            )
            return InteractiveEvent("bet_round", {"continue": True})

        if action == BettingAction.FOLD:
            player.folded = True
            self._players_needed.discard(player.player_id)
            player.betting_history.append(
                BettingEvent(action, 0, decision.rationale, self.pot, player.seat.stack)
            )
            self.events.append(
                InteractiveEvent(
                    "bet",
                    {
                        "player_id": player.player_id,
                        "action": action.value,
                        "amount": 0,
                        "pot": self.pot,
                        "stack": player.seat.stack,
                    },
                )
            )
            return InteractiveEvent("bet_round", {"continue": True})

        if action == BettingAction.BET:
            pay = min(max(amount, self.rules.min_bet), player.seat.stack)
            if pay <= 0:
                pay = min(player.seat.stack, self.rules.min_bet)
            player.seat.stack -= pay
            player.current_bet += pay
            player.committed += pay
            self.pot += pay
            self._current_bet = player.current_bet
            self._raises = 1
            player.betting_history.append(
                BettingEvent(action, pay, decision.rationale, self.pot, player.seat.stack)
            )
            self._reset_players_needed(exclude=player.player_id)
            if player.seat.stack == 0:
                player.all_in = True
            self.events.append(
                InteractiveEvent(
                    "bet",
                    {
                        "player_id": player.player_id,
                        "action": action.value,
                        "amount": pay,
                        "pot": self.pot,
                        "stack": player.seat.stack,
                    },
                )
            )
            return InteractiveEvent("bet_round", {"continue": True})

        if action == BettingAction.CALL:
            pay = min(max(amount, to_call), player.seat.stack)
            player.seat.stack -= pay
            player.current_bet += pay
            player.committed += pay
            self.pot += pay
            if player.current_bet < self._current_bet:
                player.all_in = True
            player.betting_history.append(
                BettingEvent(action, pay, decision.rationale, self.pot, player.seat.stack)
            )
            self._players_needed.discard(player.player_id)
            self.events.append(
                InteractiveEvent(
                    "bet",
                    {
                        "player_id": player.player_id,
                        "action": action.value,
                        "amount": pay,
                        "pot": self.pot,
                        "stack": player.seat.stack,
                    },
                )
            )
            return InteractiveEvent("bet_round", {"continue": True})

        if action == BettingAction.RAISE:
            minimum_total = to_call + max(self.rules.min_bet, self.rules.min_bet)
            pay = min(max(amount, minimum_total), player.seat.stack)
            player.seat.stack -= pay
            player.current_bet += pay
            player.committed += pay
            self.pot += pay
            self._current_bet = player.current_bet
            self._raises += 1
            player.betting_history.append(
                BettingEvent(action, pay, decision.rationale, self.pot, player.seat.stack)
            )
            self._reset_players_needed(exclude=player.player_id)
            if player.seat.stack == 0:
                player.all_in = True
            self.events.append(
                InteractiveEvent(
                    "bet",
                    {
                        "player_id": player.player_id,
                        "action": action.value,
                        "amount": pay,
                        "pot": self.pot,
                        "stack": player.seat.stack,
                    },
                )
            )
            return InteractiveEvent("bet_round", {"continue": True})

        raise ValueError(f"Unsupported action: {action}")

    def progress_after_betting(self) -> None:
        if self.phase != self.PHASE_BETTING:
            return
        if not self.betting_complete():
            return
        if self._should_continue_to_draw():
            self.begin_draw_phase()
        else:
            self.phase = self.PHASE_SHOWDOWN

    def _reset_players_needed(self, exclude: int) -> None:
        self._players_needed = {
            player.player_id
            for player in self.players
            if not player.folded and not player.all_in and player.player_id != exclude
        }

    def betting_complete(self) -> bool:
        active = [player for player in self.players if not player.folded]
        if len(active) <= 1:
            return True
        return not self._players_needed

    # ------------------------------------------------------------------
    # Draw helpers
    # ------------------------------------------------------------------

    def begin_draw_phase(self) -> None:
        self.phase = self.PHASE_DRAW
        self._draw_queue = [player for player in self.players if not player.folded]
        self._draw_index = 0

    def next_to_discard(self) -> Optional[_RoundPlayer]:
        while self._draw_index < len(self._draw_queue):
            player = self._draw_queue[self._draw_index]
            self._draw_index += 1
            return player
        return None

    def peek_next_discard(self) -> Optional[_RoundPlayer]:
        if self.phase != self.PHASE_DRAW:
            return None
        if not hasattr(self, "_draw_queue"):
            return None
        if self._draw_index >= len(self._draw_queue):
            return None
        return self._draw_queue[self._draw_index]

    def apply_discard(self, player: _RoundPlayer, decision: DiscardDecision) -> None:
        if not isinstance(decision, DiscardDecision):
            raise ValueError("Invalid discard decision")
        if not _validate_discard(decision.discard_indices, len(player.hand_after), self.rules):
            decision = _conservative_fallback(player.hand_after, self.rules)
        player.discard_decision = decision
        player.hand_after = _apply_discard(player.hand_after, decision.discard_indices, self.deck)
        player.final_eval = evaluate_hand(player.hand_after)
        self.events.append(
            InteractiveEvent(
                "discard",
                {
                    "player_id": player.player_id,
                    "discard_indices": list(decision.discard_indices),
                    "hand_after": [str(card) for card in player.hand_after],
                },
            )
        )
        if self.peek_next_discard() is None:
            self.phase = self.PHASE_SHOWDOWN

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def showdown(self) -> GameResult:
        active_players = [player for player in self.players if not player.folded]
        if len(active_players) == 1:
            winner = active_players[0]
            winner.final_eval = winner.final_eval or winner.initial_eval
            winner.seat.stack += self.pot
            winner.betting_history.append(
                BettingEvent(
                    action=BettingAction.CALL,
                    amount=self.pot,
                    rationale="Payout",
                    pot_after=0,
                    stack_after=winner.seat.stack,
                )
            )
            results = self._build_player_results([winner])
            bankrolls = {player.player_id: player.seat.stack for player in self.players}
            self.phase = self.PHASE_COMPLETE
            return GameResult(
                game_id=self.game_id,
                players=results,
                pot=self.pot,
                winners=[winner.player_id],
                bankrolls=bankrolls,
            )

        for player in active_players:
            player.final_eval = player.final_eval or evaluate_hand(player.hand_after)

        winners = self._determine_winners(active_players)
        share, remainder = divmod(self.pot, len(winners))
        remaining = self.pot
        for idx, winner in enumerate(winners):
            payout = share + (1 if idx < remainder else 0)
            winner.seat.stack += payout
            remaining -= payout
            winner.betting_history.append(
                BettingEvent(
                    action=BettingAction.CALL,
                    amount=payout,
                    rationale="Payout",
                    pot_after=max(remaining, 0),
                    stack_after=winner.seat.stack,
                )
            )
        results = self._build_player_results(winners)
        bankrolls = {player.player_id: player.seat.stack for player in self.players}
        self.phase = self.PHASE_COMPLETE
        return GameResult(
            game_id=self.game_id,
            players=results,
            pot=self.pot,
            winners=[player.player_id for player in winners],
            bankrolls=bankrolls,
        )

    def _determine_winners(self, players: List[_RoundPlayer]) -> List[_RoundPlayer]:
        if not players:
            return []
        best = players[0]
        winners = [best]
        for player in players[1:]:
            comparison = compare_hands(player.hand_after, winners[0].hand_after)
            if comparison > 0:
                winners = [player]
            elif comparison == 0:
                winners.append(player)
        return winners

    def _build_player_results(self, winners: List[_RoundPlayer]) -> List[PlayerResult]:
        winner_ids = {player.player_id for player in winners}
        results: List[PlayerResult] = []
        for player in self.players:
            final_eval = player.final_eval if not player.folded else None
            stack_change = player.seat.stack - player.starting_stack
            results.append(
                PlayerResult(
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
                    stack_change=stack_change,
                    betting_history=player.betting_history,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Automation helpers
    # ------------------------------------------------------------------

    def auto_play(self) -> GameResult:
        while self.phase == self.PHASE_BETTING and not self.betting_complete():
            actor = self.current_actor()
            if actor is None:
                break
            decision = self._auto_bet(actor)
            self.apply_bet_decision(actor, decision)
        if self.phase == self.PHASE_BETTING:
            self.progress_after_betting()
        if self.phase == self.PHASE_DRAW:
            self.begin_draw_phase()
            player = self.next_to_discard()
            while player is not None:
                decision = self._auto_discard(player)
                self.apply_discard(player, decision)
                player = self.next_to_discard()
            self.phase = self.PHASE_SHOWDOWN
        if self.phase == self.PHASE_SHOWDOWN:
            return self.showdown()
        return self.showdown()

    def _auto_bet(self, player: _RoundPlayer) -> BetDecision:
        agent = player.seat.agent
        if agent is None:
            raise RuntimeError("Cannot auto-play a seat without an agent")
        context = self.betting_context(player)
        decision = agent.decide_bet(player.hand_after, context)
        if not isinstance(decision, BetDecision):
            return BetDecision(BettingAction.CHECK, 0, "Auto fallback: check")
        return decision

    def _auto_discard(self, player: _RoundPlayer) -> DiscardDecision:
        agent = player.seat.agent
        if agent is None:
            return DiscardDecision([])
        context = DecisionContext(
            game_id=self.game_id,
            player_id=player.player_id,
            rng=self.rng,
        )
        decision = agent.decide_discard(player.hand_after, self.rules, context)
        if not isinstance(decision, DiscardDecision):
            decision = DiscardDecision([])
        if not _validate_discard(decision.discard_indices, len(player.hand_after), self.rules):
            decision = _conservative_fallback(player.hand_after, self.rules)
        return decision

    def auto_bet_for(self, player: _RoundPlayer) -> BetDecision:
        return self._auto_bet(player)

    def auto_discard_for(self, player: _RoundPlayer) -> DiscardDecision:
        return self._auto_discard(player)

    def get_player(self, player_id: int) -> _RoundPlayer:
        for player in self.players:
            if player.player_id == player_id:
                return player
        raise ValueError(f"Unknown player id: {player_id}")

    def discards_pending(self) -> bool:
        return self.peek_next_discard() is not None

    def _should_continue_to_draw(self) -> bool:
        active_players = [player for player in self.players if not player.folded]
        return len(active_players) > 1


class InteractiveFiveCardDrawEngine:
    """High level interface to run interactive Five-card draw matches."""

    def __init__(
        self,
        seats: Sequence[PlayerSeat],
        *,
        rules: Optional[DecisionRules] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        if len(seats) < 2:
            raise ValueError("At least two seats are required")
        self.seats = list(seats)
        self.rules = rules or DecisionRules()
        self.rng = rng or random.Random()

    def start_hand(self, game_id: int) -> InteractiveHand:
        return InteractiveHand(self, game_id, self.seats)

    def autoplay_hand(self, game_id: int) -> GameResult:
        hand = self.start_hand(game_id)
        return hand.auto_play()
