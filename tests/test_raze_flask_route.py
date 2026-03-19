# tests/test_raze_flask_route.py
from __future__ import annotations

from random import Random

import pytest

pytest.importorskip("flask")

from adapters.flask_app import create_app
from combat.runtime_state import init_runtime_state
from combat.usecases import build_battle_session


def test_battle_round_raze_victory_response_is_json_serializable():
    state = init_runtime_state()
    session = build_battle_session(state=state, enemy_names=["Goblin", "Goblin"])
    app = create_app(session=session, rng=Random(0))
    client = app.test_client()

    response = client.post(
        "/battle/round",
        json={
            "planned_actions": [
                {
                    "kind": "magic",
                    "command": "Magic",
                    "spell_name": "Raze",
                    "target_side": "enemy",
                    "target_index": 0,
                    "target_all": True,
                },
                None,
                None,
                None,
            ],
            "lifecycle_state": "ready_for_actions",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["end_reason"] == "enemy_defeated"
    assert payload["lifecycle"]["battle_finished"] is True
    assert any("Goblin Aは《Raze》の効果で倒れた" in row for row in payload["logs"])
    assert any("Goblin Bは《Raze》の効果で倒れた" in row for row in payload["logs"])
    assert any("=== Battle Rewards ===" in row for row in payload["logs"])
    assert [enemy["name"] for enemy in payload["session_status"]["enemies"]] == [
        "Goblin A",
        "Goblin B",
    ]

    status_events = [e for e in payload["events"] if e.get("type") == "status"]
    assert status_events
    for event in status_events:
        assert all(isinstance(name, str) for name in event.get("names", []))
