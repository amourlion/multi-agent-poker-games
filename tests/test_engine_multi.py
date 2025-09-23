from __future__ import annotations

import random

from agent_llm import LLMAgent
from deck import Card
from engine import FiveCardDrawEngine, PlayerSeat
from game_types import (
    BetDecision,
    BettingAction,
    BettingContext,
    DecisionRules,
    DiscardDecision,
)


class PassiveAgent:
    def decide_bet(self, hand, context: BettingContext) -> BetDecision:
        if BettingAction.CHECK in context.available_actions:
            return BetDecision(BettingAction.CHECK)
        if BettingAction.CALL in context.available_actions:
            return BetDecision(BettingAction.CALL, min(context.to_call, context.stack))
        return BetDecision(BettingAction.FOLD)

    def decide_discard(self, hand, rules, context) -> DiscardDecision:
        return DiscardDecision([])


class AggressiveAgent(PassiveAgent):
    def decide_bet(self, hand, context: BettingContext) -> BetDecision:
        if context.to_call == 0 and BettingAction.BET in context.available_actions:
            return BetDecision(BettingAction.BET, max(context.min_bet, 1))
        return super().decide_bet(hand, context)


class FoldingAgent(PassiveAgent):
    def decide_bet(self, hand, context: BettingContext) -> BetDecision:
        if context.to_call > 0 and BettingAction.FOLD in context.available_actions:
            return BetDecision(BettingAction.FOLD)
        return super().decide_bet(hand, context)


def test_bet_and_fold_returns_chips_to_bettor():
    seats = [
        PlayerSeat(player_id=0, name="Aggressor", agent=AggressiveAgent(), stack=100),
        PlayerSeat(player_id=1, name="Folder", agent=FoldingAgent(), stack=100),
    ]
    engine = FiveCardDrawEngine(seats, rng=random.Random(0))
    rules = DecisionRules(min_bet=10, ante=0, max_discards=5, max_raises=3)
    result = engine.play_game(1, rules)

    assert result.winners == [0]
    assert result.bankrolls[0] == 100
    assert result.bankrolls[1] == 100
    assert result.pot == 10

    aggressor = next(player for player in result.players if player.player_id == 0)
    folder = next(player for player in result.players if player.player_id == 1)

    assert aggressor.folded is False
    assert folder.folded is True
    assert any(event.action == BettingAction.BET for event in aggressor.betting_history)


def test_multi_agent_round_records_all_players():
    seats = [
        PlayerSeat(player_id=0, name="P1", agent=PassiveAgent(), stack=100),
        PlayerSeat(player_id=1, name="P2", agent=PassiveAgent(), stack=100),
        PlayerSeat(player_id=2, name="P3", agent=PassiveAgent(), stack=100),
    ]
    engine = FiveCardDrawEngine(seats, rng=random.Random(1))
    rules = DecisionRules(min_bet=0, ante=0, max_discards=5, max_raises=1)
    result = engine.play_game(1, rules)

    assert len(result.players) == 3
    assert set(player.player_id for player in result.players) == {0, 1, 2}


class _StaticRandom(random.Random):
    def __init__(self, values: list[float] | None = None) -> None:
        super().__init__()
        self._values = values or [0.0]
        self._index = 0

    def random(self):  # type: ignore[override]
        value = self._values[self._index % len(self._values)]
        self._index += 1
        return value


def test_llm_agent_bets_with_strong_hand():
    agent = LLMAgent(client=None)
    hand = [Card("A", "S"), Card("K", "S"), Card("Q", "S"), Card("J", "S"), Card("T", "S")]
    context = BettingContext(
        game_id=1,
        player_id=0,
        round_id=0,
        pot=0,
        to_call=0,
        current_bet=0,
        min_bet=20,
        min_raise=20,
        stack=200,
        committed=0,
        available_actions=(BettingAction.CHECK, BettingAction.BET),
        rng=_StaticRandom([0.0]),
    )
    decision = agent.decide_bet(hand, context)
    assert decision.action == BettingAction.BET


def test_llm_agent_raises_with_premium_hand_when_facing_bet():
    agent = LLMAgent(client=None)
    hand = [
        Card("A", "S"),
        Card("A", "H"),
        Card("A", "D"),
        Card("K", "C"),
        Card("K", "S"),
    ]
    context = BettingContext(
        game_id=1,
        player_id=0,
        round_id=0,
        pot=60,
        to_call=20,
        current_bet=60,
        min_bet=20,
        min_raise=20,
        stack=200,
        committed=0,
        available_actions=(BettingAction.CALL, BettingAction.RAISE, BettingAction.FOLD),
        rng=_StaticRandom([0.0]),
    )
    decision = agent.decide_bet(hand, context)
    assert decision.action == BettingAction.RAISE


def test_llm_agent_bets_with_one_pair_most_of_the_time():
    agent = LLMAgent(client=None)
    hand = [
        Card("Q", "S"),
        Card("Q", "H"),
        Card("7", "D"),
        Card("4", "C"),
        Card("2", "S"),
    ]
    context = BettingContext(
        game_id=1,
        player_id=0,
        round_id=0,
        pot=0,
        to_call=0,
        current_bet=0,
        min_bet=20,
        min_raise=20,
        stack=400,
        committed=0,
        available_actions=(BettingAction.CHECK, BettingAction.BET),
        rng=_StaticRandom([0.2]),
    )
    decision = agent.decide_bet(hand, context)
    assert decision.action == BettingAction.BET


def test_llm_agent_bluffs_high_card_with_randomness():
    agent = LLMAgent(client=None)
    hand = [
        Card("A", "S"),
        Card("J", "H"),
        Card("8", "D"),
        Card("6", "C"),
        Card("2", "S"),
    ]
    context = BettingContext(
        game_id=1,
        player_id=0,
        round_id=0,
        pot=0,
        to_call=0,
        current_bet=0,
        min_bet=20,
        min_raise=20,
        stack=400,
        committed=0,
        available_actions=(BettingAction.CHECK, BettingAction.BET),
        rng=_StaticRandom([0.4]),
    )
    decision = agent.decide_bet(hand, context)
    assert decision.action == BettingAction.BET
