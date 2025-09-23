from __future__ import annotations

import random

from agent_random import RandomAgent
from engine import FiveCardDrawEngine, GameResult, PlayerSeat
from engine_interactive import InteractiveFiveCardDrawEngine
from game_types import BetDecision, BettingAction, DecisionRules, DiscardDecision


def _make_seats(stacks):
    return [
        PlayerSeat(player_id=i, name=f"P{i+1}", agent=RandomAgent(), stack=stack)
        for i, stack in enumerate(stacks)
    ]


def test_interactive_autoplay_matches_core_engine():
    stacks = [600, 400, 500]
    seats_core = _make_seats(stacks)
    seats_interactive = _make_seats(stacks)

    rng_core = random.Random(123)
    rng_interactive = random.Random(123)
    rules = DecisionRules(min_bet=20, ante=10, max_discards=5)

    core_engine = FiveCardDrawEngine(seats_core, rng=rng_core)
    core_result = core_engine.play_game(1, rules)

    interactive_engine = InteractiveFiveCardDrawEngine(
        seats_interactive, rules=rules, rng=rng_interactive
    )
    interactive_result = interactive_engine.autoplay_hand(1)

    assert core_result.pot == interactive_result.pot
    assert core_result.winners == interactive_result.winners
    assert [player.player_id for player in core_result.players] == [
        player.player_id for player in interactive_result.players
    ]
    core_bankrolls = sorted(core_result.bankrolls.items())
    interactive_bankrolls = sorted(interactive_result.bankrolls.items())
    assert core_bankrolls == interactive_bankrolls


def test_interactive_manual_flow_allows_external_actions():
    seats = [
        PlayerSeat(player_id=0, name="Manual", agent=None, stack=300),
        PlayerSeat(player_id=1, name="Auto", agent=RandomAgent(), stack=300),
    ]
    engine = InteractiveFiveCardDrawEngine(seats, rules=DecisionRules(min_bet=10), rng=random.Random(9))
    hand = engine.start_hand(1)

    # Manually resolve betting by checking with both players
    while hand.phase == hand.PHASE_BETTING and not hand.betting_complete():
        actor = hand.current_actor()
        assert actor is not None
        context = hand.betting_context(actor)
        decision = BetDecision(BettingAction.CHECK, 0, "manual test")
        if BettingAction.CHECK not in context.available_actions:
            decision = BetDecision(context.available_actions[0], 0, "manual alt")
        hand.apply_bet_decision(actor, decision)
    if hand.phase == hand.PHASE_BETTING:
        hand.phase = hand.PHASE_DRAW if hand._should_continue_to_draw() else hand.PHASE_SHOWDOWN

    if hand.phase == hand.PHASE_DRAW:
        hand.begin_draw_phase()
        player = hand.next_to_discard()
        while player is not None:
            hand.apply_discard(player, DiscardDecision([]))
            player = hand.next_to_discard()
        hand.phase = hand.PHASE_SHOWDOWN

    result = hand.showdown()
    assert isinstance(result, GameResult)
    assert result.pot >= 0
