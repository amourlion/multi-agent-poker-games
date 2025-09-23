"""Flask service exposing a REST API for interactive Five-card draw."""

from __future__ import annotations

import os
import random
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from flask import Flask, abort, jsonify, request, make_response

from agent_llm import LLMAgent
from agent_random import RandomAgent
from engine import GameResult, PlayerSeat
from engine_interactive import (
    InteractiveFiveCardDrawEngine,
    InteractiveHand,
)
from game_types import BetDecision, BettingAction, DecisionRules, DiscardDecision


@dataclass
class GameSession:
    engine: InteractiveFiveCardDrawEngine
    hand: InteractiveHand
    result: Optional[GameResult] = None


SESSIONS: Dict[str, GameSession] = {}
app = Flask(__name__)

DEFAULT_MODEL = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-new")


@app.after_request
def add_cors_headers(response):  # pragma: no cover - simple header addition
    response.headers.setdefault("Access-Control-Allow-Origin", "*")
    response.headers.setdefault("Access-Control-Allow-Headers", "Content-Type, Authorization")
    response.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    response.headers.setdefault("Access-Control-Max-Age", "3600")
    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_agent(config: Dict[str, Any]) -> Optional[Any]:
    agent_type = config.get("type", "random").lower()
    bet_mode = config.get("bet_mode", "heuristic")
    if agent_type == "human":
        return None
    if agent_type == "random":
        return RandomAgent()
    if agent_type == "llm":
        model = config.get("model", DEFAULT_MODEL)
        temperature = float(config.get("temperature", 0.0))
        return LLMAgent(
            model=model,
            temperature=temperature,
            bet_mode=bet_mode,
        )
    raise ValueError(f"Unsupported agent type: {agent_type}")


def _make_seats(seat_configs: List[Dict[str, Any]]) -> List[PlayerSeat]:
    seats: List[PlayerSeat] = []
    for idx, cfg in enumerate(seat_configs):
        name = cfg.get("name") or f"Player {idx + 1}"
        stack = int(cfg.get("stack", 500))
        agent = _create_agent(cfg)
        seat = PlayerSeat(player_id=idx, name=name, agent=agent, stack=stack)
        seats.append(seat)
    if len(seats) < 2:
        raise ValueError("At least two seats are required")
    return seats


def _make_rules(config: Dict[str, Any]) -> DecisionRules:
    return DecisionRules(
        max_discards=int(config.get("max_discards", DecisionRules.max_discards)),
        min_bet=int(config.get("min_bet", DecisionRules.min_bet)),
        ante=int(config.get("ante", DecisionRules.ante)),
        max_raises=int(config.get("max_raises", DecisionRules.max_raises)),
    )


def _serialize_betting_event(event) -> Dict[str, Any]:
    return {
        "action": event.action.value,
        "amount": event.amount,
        "rationale": event.rationale,
        "pot_after": event.pot_after,
        "stack_after": event.stack_after,
    }


def _serialize_player(player) -> Dict[str, Any]:
    return {
        "player_id": player.player_id,
        "name": player.seat.name,
        "hand": [str(card) for card in player.hand],
        "hand_after": [str(card) for card in player.hand_after],
        "starting_stack": player.starting_stack,
        "stack": player.seat.stack,
        "current_bet": player.current_bet,
        "committed": player.committed,
        "folded": player.folded,
        "all_in": player.all_in,
        "is_human": player.seat.agent is None,
        "betting_history": [
            _serialize_betting_event(event) for event in player.betting_history
        ],
    }


def _serialize_events(events) -> List[Dict[str, Any]]:
    return [
        {
            "type": event.type,
            "payload": event.payload,
        }
        for event in events
    ]


def _serialize_hand(hand: InteractiveHand) -> Dict[str, Any]:
    actor = hand.peek_current_actor()
    active_player = actor.player_id if actor else None
    betting_context = None
    available_actions: Optional[List[str]] = None
    if actor is not None and hand.phase == hand.PHASE_BETTING:
        context = hand.betting_context(actor)
        available_actions = [action.value for action in context.available_actions]
        betting_context = {
            "player_id": actor.player_id,
            "to_call": context.to_call,
            "current_bet": context.current_bet,
            "min_bet": context.min_bet,
            "min_raise": context.min_raise,
            "stack": context.stack,
            "committed": context.committed,
        }
    next_discard = hand.peek_next_discard()
    draw_context = None
    if hand.phase == hand.PHASE_DRAW:
        draw_context = {
            "player_id": next_discard.player_id if next_discard else None,
            "max_discards": hand._engine.rules.max_discards,
            "hand_size": len(next_discard.hand_after) if next_discard else 0,
        }

    return {
        "game_id": hand.game_id,
        "phase": hand.phase,
        "pot": hand.pot,
        "current_bet": getattr(hand, "_current_bet", 0),
        "active_player": active_player,
        "available_actions": available_actions,
        "next_discard_player": next_discard.player_id if next_discard else None,
        "betting_context": betting_context,
        "draw_context": draw_context,
        "players": [_serialize_player(player) for player in hand.players],
        "events": _serialize_events(hand.events),
    }


def _get_session(game_id: str) -> GameSession:
    session = SESSIONS.get(game_id)
    if session is None:
        abort(404, description="Game not found")
    return session


def _ensure_game_not_complete(session: GameSession) -> None:
    if session.result is not None:
        abort(400, description="Game already resolved")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/api/games", methods=["POST", "OPTIONS"])
def create_game():
    if request.method == "OPTIONS":
        return make_response("", 204)
    payload = request.get_json(force=True, silent=False)
    if not payload or "seats" not in payload:
        abort(400, description="Missing seats definition")
    try:
        seats = _make_seats(payload["seats"])
        rules = _make_rules(payload.get("rules", {}))
        seed = payload.get("seed")
        rng = random.Random(seed) if seed is not None else random.Random()
        engine = InteractiveFiveCardDrawEngine(seats, rules=rules, rng=rng)
        hand = engine.start_hand(payload.get("game_number", 1))
        session_id = str(uuid.uuid4())
        SESSIONS[session_id] = GameSession(engine=engine, hand=hand)
        return (
            jsonify({
                "game_id": session_id,
                "state": _serialize_hand(hand),
                "result": None,
            }),
            201,
        )
    except ValueError as exc:  # noqa: BLE001
        abort(400, description=str(exc))


@app.route("/api/games/<game_id>", methods=["GET", "OPTIONS"])
def get_game(game_id: str):
    if request.method == "OPTIONS":
        return make_response("", 204)
    session = _get_session(game_id)
    return jsonify(
        {
            "game_id": game_id,
            "state": _serialize_hand(session.hand),
            "result": session.result.to_dict() if session.result else None,
        }
    )


@app.route("/api/games/<game_id>/action", methods=["POST", "OPTIONS"])
def apply_action(game_id: str):
    if request.method == "OPTIONS":
        return make_response("", 204)
    session = _get_session(game_id)
    _ensure_game_not_complete(session)
    payload = request.get_json(force=True, silent=False) or {}
    action_type = payload.get("type")
    if not action_type:
        abort(400, description="Missing action type")

    hand = session.hand
    if action_type == "bet":
        if hand.phase != hand.PHASE_BETTING:
            abort(400, description="Not in betting phase")
        player_id = int(payload.get("player_id"))
        player = hand.get_player(player_id)
        action_name = payload.get("action")
        if not action_name:
            abort(400, description="Missing betting action")
        try:
            bet_action = BettingAction(action_name.lower())
        except ValueError as exc:  # noqa: BLE001
            abort(400, description=str(exc))
        context = hand.betting_context(player)
        amount = int(payload.get("amount", 0))
        rationale = payload.get("rationale")

        if bet_action == BettingAction.CALL:
            amount = context.to_call
        elif bet_action == BettingAction.BET:
            minimum = max(context.min_bet, 1)
            if amount < minimum:
                abort(400, description=f"Bet must be at least {minimum}")
        elif bet_action == BettingAction.RAISE:
            minimum_total = context.to_call + max(context.min_raise, 1)
            if amount < minimum_total:
                abort(400, description=f"Raise must total at least {minimum_total}")
        decision = BetDecision(bet_action, amount, rationale)
        hand.apply_bet_decision(player, decision)
        hand.progress_after_betting()

    elif action_type == "discard":
        if hand.phase != hand.PHASE_DRAW:
            abort(400, description="Not in draw phase")
        player_id = int(payload.get("player_id"))
        next_player = hand.peek_next_discard()
        if next_player is None or next_player.player_id != player_id:
            abort(400, description="Not this player's turn to discard")
        player = hand.next_to_discard()
        if player is None:
            abort(400, description="No player available to discard")
        indices = payload.get("discard_indices", [])
        if not isinstance(indices, list):
            abort(400, description="discard_indices must be a list")
        decision = DiscardDecision([int(idx) for idx in indices], payload.get("rationale"))
        hand.apply_discard(player, decision)

    elif action_type == "auto_bet":
        if hand.phase != hand.PHASE_BETTING:
            abort(400, description="Not in betting phase")
        actor = hand.peek_current_actor()
        if actor is None:
            abort(400, description="No actor available")
        if actor.seat.agent is None:
            abort(400, description="Active seat is human; use manual bet")
        decision = hand.auto_bet_for(actor)
        hand.apply_bet_decision(actor, decision)
        hand.progress_after_betting()

    elif action_type == "auto_discard":
        if hand.phase != hand.PHASE_DRAW:
            abort(400, description="Not in draw phase")
        player_peek = hand.peek_next_discard()
        if player_peek is None:
            abort(400, description="No player pending discard")
        if player_peek.seat.agent is None:
            abort(400, description="Pending seat is human; send discard decision")
        player = hand.next_to_discard()
        if player is None:
            abort(400, description="No player pending discard")
        decision = hand.auto_discard_for(player)
        hand.apply_discard(player, decision)

    elif action_type == "auto_until_human":
        made_progress = False

        while hand.phase == hand.PHASE_BETTING:
            peek_actor = hand.peek_current_actor()
            if peek_actor is None:
                hand.progress_after_betting()
                made_progress = True
                if hand.phase != hand.PHASE_BETTING:
                    break
                continue
            if peek_actor.seat.agent is None:
                break
            actor = hand.current_actor()
            if actor is None:
                break
            decision = hand.auto_bet_for(actor)
            hand.apply_bet_decision(actor, decision)
            hand.progress_after_betting()
            made_progress = True

        while hand.phase == hand.PHASE_DRAW:
            peek_player = hand.peek_next_discard()
            if peek_player is None:
                hand.phase = hand.PHASE_SHOWDOWN
                made_progress = True
                break
            if peek_player.seat.agent is None:
                break
            player = hand.next_to_discard()
            if player is None:
                break
            decision = hand.auto_discard_for(player)
            hand.apply_discard(player, decision)
            made_progress = True

        if not made_progress:
            actor = hand.peek_current_actor()
            if actor and actor.seat.agent is None:
                abort(400, description="Human seat is next to act")
            if hand.phase == hand.PHASE_DRAW:
                player = hand.peek_next_discard()
                if player and player.seat.agent is None:
                    abort(400, description="Human seat pending discard")

    elif action_type == "advance":
        if hand.phase == hand.PHASE_BETTING:
            hand.progress_after_betting()
        elif hand.phase == hand.PHASE_DRAW and not hand.discards_pending():
            hand.phase = hand.PHASE_SHOWDOWN
        else:
            abort(400, description="Nothing to advance")

    elif action_type == "resolve":
        if hand.phase != hand.PHASE_SHOWDOWN:
            abort(400, description="Not ready for showdown")
        session.result = hand.showdown()
    elif action_type == "auto_play":
        try:
            session.result = hand.auto_play()
        except RuntimeError as exc:
            abort(400, description=str(exc))
    else:
        abort(400, description=f"Unknown action type: {action_type}")

    if (session.result is None) and hand.phase == hand.PHASE_SHOWDOWN:
        session.result = hand.showdown()

    return jsonify(
        {
            "game_id": game_id,
            "state": _serialize_hand(hand),
            "result": session.result.to_dict() if session.result else None,
        }
    )


@app.route("/api/games/<game_id>/reset", methods=["POST", "OPTIONS"])
def reset_game(game_id: str):
    if request.method == "OPTIONS":
        return make_response("", 204)
    session = _get_session(game_id)
    seed = request.get_json(force=True, silent=True) or {}
    rng = random.Random(seed.get("seed")) if seed.get("seed") is not None else random.Random()
    session.engine.rng = rng
    session.hand = session.engine.start_hand(seed.get("game_number", 1))
    session.result = None
    return jsonify(
        {
            "game_id": game_id,
            "state": _serialize_hand(session.hand),
            "result": None,
        }
    )


if __name__ == "__main__":  # pragma: no cover
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
