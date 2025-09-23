from __future__ import annotations

from typing import Any, Dict

from service import SESSIONS, app


def _create_game(client, seats: Dict[str, Any]) -> Dict[str, Any]:
    response = client.post(
        "/api/games",
        json={
            "seats": seats,
            "rules": {"min_bet": 10, "ante": 0, "max_discards": 5},
            "seed": 123,
        },
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data is not None
    return data


def test_create_and_autoplay_game():
    SESSIONS.clear()
    client = app.test_client()
    data = _create_game(
        client,
        [
            {"name": "Alice", "type": "random", "stack": 500},
            {"name": "Bob", "type": "random", "stack": 400},
            {"name": "Cara", "type": "random", "stack": 400},
        ],
    )
    game_id = data["game_id"]

    response = client.post(
        f"/api/games/{game_id}/action", json={"type": "auto_play"}
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload is not None
    assert payload["result"] is not None
    assert payload["state"]["phase"] == "complete" or payload["state"]["phase"] == "showdown"


def test_manual_flow_via_api():
    SESSIONS.clear()
    client = app.test_client()
    data = _create_game(
        client,
        [
            {"name": "Human", "type": "human", "stack": 400},
            {"name": "Bot", "type": "random", "stack": 400},
        ],
    )
    game_id = data["game_id"]
    state = data["state"]

    # Betting phase: human checks, bot auto plays until betting resolves
    while state["phase"] == "betting":
        active = state.get("active_player")
        if active is None:
            break
        players = {player["player_id"]: player for player in state["players"]}
        active_player = players[active]
        if active_player["is_human"]:
            resp = client.post(
                f"/api/games/{game_id}/action",
                json={
                    "type": "bet",
                    "player_id": active,
                    "action": "check",
                    "rationale": "test",
                },
            )
        else:
            resp = client.post(
                f"/api/games/{game_id}/action",
                json={"type": "auto_bet"},
            )
        assert resp.status_code == 200
        state = resp.get_json()["state"]

    # Ensure we are now in draw or showdown
    assert state["phase"] in {"draw", "showdown", "complete"}

    # If draw, discard nothing for human and auto for bot
    while state["phase"] == "draw":
        next_discard = state.get("next_discard_player")
        if next_discard is None:
            break
        players = {player["player_id"]: player for player in state["players"]}
        if players[next_discard]["is_human"]:
            resp = client.post(
                f"/api/games/{game_id}/action",
                json={
                    "type": "discard",
                    "player_id": next_discard,
                    "discard_indices": [],
                },
            )
        else:
            resp = client.post(
                f"/api/games/{game_id}/action",
                json={"type": "auto_discard"},
            )
        assert resp.status_code == 200
        state = resp.get_json()["state"]

    # Resolve showdown if still pending
    if state["phase"] == "showdown":
        resp = client.post(
            f"/api/games/{game_id}/action", json={"type": "resolve"}
        )
        assert resp.status_code == 200
        state = resp.get_json()["state"]
        result = resp.get_json()["result"]
    else:
        result = client.get(f"/api/games/{game_id}").get_json()["result"]

    assert result is not None
    assert "winners" in result


def test_invalid_action_returns_400():
    SESSIONS.clear()
    client = app.test_client()
    data = _create_game(
        client,
        [
            {"name": "Alice", "type": "random", "stack": 400},
            {"name": "Bob", "type": "random", "stack": 400},
        ],
    )
    game_id = data["game_id"]
    resp = client.post(
        f"/api/games/{game_id}/action", json={"type": "unknown"}
    )
    assert resp.status_code == 400
