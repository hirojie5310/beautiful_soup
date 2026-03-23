# tests/test_wasm_api.py
from __future__ import annotations

import json

from combat.enums import Status
from combat.wasm_api import WasmBattleEngine, build_session_status_snapshot


def test_wasm_engine_round_json_returns_browser_ready_payload(monkeypatch) -> None:
    engine = WasmBattleEngine.create_default(seed=7)

    def _fake_execute_round_dto(*, session, request, rng):
        assert len(request.planned_actions) == len(session.party_members)
        first_enemy = session.enemies[0]
        first_enemy.state.hp = 0
        return type(
            "Output",
            (),
            {
                "logs": ["Refia attacks!", "Goblin took 10 damage."],
                "end_reason": "continue",
                "escaped": False,
                "enemy_was_physically_hit": True,
                "events": [
                    {
                        "type": "damage",
                        "target_side": "enemy",
                        "target_index": 0,
                        "value": 10,
                    }
                ],
                "lifecycle": type(
                    "Lifecycle",
                    (),
                    {
                        "before": "resolving_round",
                        "after": "ready_for_next_round",
                        "battle_finished": False,
                    },
                )(),
            },
        )()

    monkeypatch.setattr("combat.wasm_api.execute_round_dto", _fake_execute_round_dto)

    payload = json.loads(
        engine.execute_round_json(
            json.dumps(
                {"planned_actions": [], "lifecycle_state": "ready_for_actions"},
                ensure_ascii=False,
            )
        )
    )

    assert payload["logs"] == ["Refia attacks!", "Goblin took 10 damage."]
    assert payload["lifecycle"]["after"] == "ready_for_next_round"
    assert payload["session_status"]["enemies"][0]["hp"] == 0
    assert payload["selected_location_group"] == ""
    assert payload["selected_location"] == ""


def test_build_session_status_snapshot_serializes_status_icons() -> None:
    engine = WasmBattleEngine.create_default(seed=1)
    engine.session.party_members[0].state.statuses = {Status.BLIND}

    snapshot = build_session_status_snapshot(engine.session)

    assert snapshot["party"][0]["status_icons"] == ["blind"]
    assert snapshot["enemies"]


def test_wasm_engine_initial_payload_exposes_flat_party_members() -> None:
    engine = WasmBattleEngine.create_default(seed=3)

    payload = engine.build_initial_payload()

    assert payload["session_status"]["party"]
    assert payload["party_members"][0]["equipment"]["main_hand"] is not None
    assert "strength" in payload["party_members"][0]
