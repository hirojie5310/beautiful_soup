# tests/test_flask_round_route.py
from __future__ import annotations

import json
import re

from dataclasses import dataclass
from typing import cast

import pytest

pytest.importorskip("flask")

from combat.dto import BattleLifecycleDTO, ExecuteRoundOutputDTO, LIFECYCLE_READY
from combat.enums import MagicType
from combat.errors import DomainError, InputValidationError, InvalidLifecycleError
from combat.usecases import BattleSession


@dataclass
class _DummyMember:
    state: object


@dataclass
class _DummyState:
    items_by_name: dict[str, object]
    save: dict[str, object] | None = None


@dataclass
class _DummySession:
    party_members: list[_DummyMember]
    enemies: list[_DummyMember]
    state: _DummyState
    level_table: object | None = None


def _build_app(monkeypatch, *, expected_actions: int = 4):
    import adapters.flask_app as flask_app

    app = flask_app.create_app(
        session=cast(
            BattleSession,
            _DummySession(
                party_members=[
                    _DummyMember(state=object()) for _ in range(expected_actions)
                ],
                enemies=[_DummyMember(state=object()) for _ in range(3)],
                state=_DummyState(
                    items_by_name={
                        "Potion": {
                            "Name": "Potion",
                            "ItemType": "Anywhere",
                            "SpellEffect": "Recovery",
                            "SpellInfo": {"Effect": "Restore target's HP"},
                        },
                        "Bomb Fragment": {
                            "Name": "Bomb Fragment",
                            "ItemType": "Combat",
                            "SpellInfo": {"Effect": "Deal fire damage"},
                        },
                        "Gysahl Greens": {
                            "Name": "Gysahl Greens",
                            "ItemType": "Field",
                        },
                        "Eureka Key": {
                            "Name": "Eureka Key",
                            "ItemType": "Key Item",
                        },
                    },
                    save={
                        "inventory": {
                            "Anywhere": {"Potion": 2},
                            "Combat": {"Bomb Fragment": 1},
                            "Field": {"Gysahl Greens": 4},
                            "Key Item": {"Eureka Key": 1},
                        }
                    },
                ),
                level_table=object(),
            ),
        ),
    )

    def _fake_execute_round_dto(*, session, request, rng):
        if request.lifecycle_state != LIFECYCLE_READY:
            raise InvalidLifecycleError(
                "execute_round_dto must start from 'ready_for_actions'.",
                details={"current_state": request.lifecycle_state},
            )
        if len(request.planned_actions) != len(session.party_members):
            raise InputValidationError("planned action length mismatch")
        return ExecuteRoundOutputDTO(
            logs=[],
            end_reason="continue",
            escaped=False,
            enemy_was_physically_hit=False,
            events=[],
            lifecycle=BattleLifecycleDTO(
                before="resolving_round",
                after="ready_for_next_round",
                battle_finished=False,
            ),
        )

    monkeypatch.setattr(flask_app, "execute_round_dto", _fake_execute_round_dto)

    @app.get("/test/domain400")
    def _test_domain_400():
        raise DomainError(message="manual bad request")

    @app.get("/test/unexpected")
    def _test_unexpected():
        raise RuntimeError("secret")

    return app


def test_root_page_renders_html(monkeypatch):
    app = _build_app(monkeypatch)
    client = app.test_client()

    resp = client.get("/")

    assert resp.status_code == 200
    assert "text/html" in resp.content_type
    body = resp.get_data(as_text=True)
    assert "Battle Round Runner" in body
    assert "中部: Enemy Sprites" in body
    assert "下部: COMMAND" in body
    assert "LocationGroup" in body
    assert "Field Menu" in body
    assert "menuUseItemBtn" not in body
    assert '"is_jumping": false' in body
    assert '"jump_target_index": null' in body
    assert "magicSpellMetaJson" in body
    assert "itemBattleMetaJson" in body
    assert '"Potion":{"target_side":"ally"}' in body.replace(" ", "")

    match = re.search(
        r'<script id="commandCandidatesJson" type="application/json">(.*?)</script>',
        body,
        re.S,
    )
    assert match is not None
    command_payload = json.loads(match.group(1))
    assert command_payload["item"] == [
        {"item_type": "Anywhere", "label": "Potion ×2", "name": "Potion", "qty": 2},
        {
            "item_type": "Combat",
            "label": "Bomb Fragment ×1",
            "name": "Bomb Fragment",
            "qty": 1,
        },
    ]


def test_root_page_embeds_formatted_magic_candidates(monkeypatch):
    from types import SimpleNamespace

    import adapters.flask_app as flask_app

    session = cast(
        BattleSession,
        _DummySession(
            party_members=[
                _DummyMember(
                    state=SimpleNamespace(
                        mp_pool={8: 4, 7: 2, 6: 1},
                        max_mp_pool={8: 8, 7: 7, 6: 6},
                    )
                )
            ],
            enemies=[_DummyMember(state=object()) for _ in range(3)],
            state=_DummyState(items_by_name={}, save={}),
            level_table=object(),
        ),
    )
    session.party_magic_lists = [
        [
            ("Flare", MagicType.BLACK, 8),
            ("Curaja", MagicType.WHITE, 7),
            ("Bahamut: Mega Flare", MagicType.SUMMON, 6),
        ]
    ]

    app = flask_app.create_app(session=session)

    client = app.test_client()
    resp = client.get("/")

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    match = re.search(
        r'<script id="commandCandidatesJson" type="application/json">(.*?)</script>',
        body,
        re.S,
    )
    assert match is not None
    command_payload = json.loads(match.group(1))
    assert command_payload["magic_by_member"] == [
        [
            {
                "label": "●LV8: Flare - 4/8",
                "level": 8,
                "max_uses": 8,
                "name": "Flare",
                "remaining_uses": 4,
                "type": "Black Magic",
            },
            {
                "label": "〇LV7: Curaja - 2/7",
                "level": 7,
                "max_uses": 7,
                "name": "Curaja",
                "remaining_uses": 2,
                "type": "White Magic",
            },
            {
                "label": "◎LV6: Bahamut: Mega Flare - 1/6",
                "level": 6,
                "max_uses": 6,
                "name": "Bahamut: Mega Flare",
                "remaining_uses": 1,
                "type": "Summon Magic",
            },
        ]
    ]


def test_menu_page_renders_html(monkeypatch):
    app = _build_app(monkeypatch)
    client = app.test_client()

    resp = client.get("/menu")

    assert resp.status_code == 200
    assert "text/html" in resp.content_type
    body = resp.get_data(as_text=True)
    assert "Field Menu" in body
    assert "menuHelp" in body
    assert "menuMessage" in body
    assert "/menu/item" in body
    assert "/menu/toggle-row" in body


def test_menu_sub_pages_render(monkeypatch):
    app = _build_app(monkeypatch)
    client = app.test_client()

    for path, marker in [
        ("/menu/item", 'id="itemPane"'),
        ("/menu/magic", 'id="magicScreen"'),
        ("/menu/equip", 'id="equipScreen"'),
        ("/menu/status", 'id="statusScreen"'),
        ("/menu/job", 'id="jobScreen"'),
    ]:
        resp = client.get(path)
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert marker in body


def test_post_round_accepts_shorter_planned_actions_with_padding(monkeypatch):
    app = _build_app(monkeypatch, expected_actions=4)
    client = app.test_client()

    resp = client.post(
        "/battle/round",
        json={"planned_actions": [], "lifecycle_state": "ready_for_actions"},
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert "session_status" in payload
    assert payload["session_status"]["party"]
    assert payload["session_status"]["enemies"]


def test_post_round_rejects_too_many_planned_actions(monkeypatch):
    app = _build_app(monkeypatch, expected_actions=2)
    client = app.test_client()

    resp = client.post(
        "/battle/round",
        json={
            "planned_actions": [None, None, None],
            "lifecycle_state": "ready_for_actions",
        },
    )

    assert resp.status_code == 422
    payload = resp.get_json()
    assert payload["error"]["code"] == "input_validation_error"


def test_post_round_invalid_lifecycle_maps_to_409(monkeypatch):
    app = _build_app(monkeypatch, expected_actions=2)
    client = app.test_client()

    resp = client.post(
        "/battle/round",
        json={
            "planned_actions": [None, None],
            "lifecycle_state": "ready_for_next_round",
        },
    )

    assert resp.status_code == 409


def test_post_round_non_json_body_maps_to_422(monkeypatch):
    app = _build_app(monkeypatch, expected_actions=2)
    client = app.test_client()

    resp = client.post(
        "/battle/round",
        data="not-json",
        content_type="text/plain",
    )

    assert resp.status_code == 422
    payload = resp.get_json()
    assert payload["error"]["code"] == "input_validation_error"


def test_domain_error_default_maps_to_400(monkeypatch):
    app = _build_app(monkeypatch)
    client = app.test_client()

    resp = client.get("/test/domain400")

    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["error"]["code"] == "domain_error"


def test_method_not_allowed_maps_to_http_error_405(monkeypatch):
    app = _build_app(monkeypatch)
    client = app.test_client()

    resp = client.get("/battle/round")

    assert resp.status_code == 405
    payload = resp.get_json()
    assert payload["error"]["code"] == "http_error"


def test_unexpected_error_maps_to_500_masked(monkeypatch):
    app = _build_app(monkeypatch)
    client = app.test_client()

    resp = client.get("/test/unexpected")

    assert resp.status_code == 500
    payload = resp.get_json()
    assert payload["error"]["code"] == "internal_domain_error"


def test_post_round_appends_victory_reward_logs(monkeypatch):
    import adapters.flask_app as flask_app

    app = flask_app.create_app(
        session=cast(
            BattleSession,
            _DummySession(
                party_members=[_DummyMember(state=object()) for _ in range(2)],
                enemies=[_DummyMember(state=object())],
                state=_DummyState(items_by_name={}),
                level_table=object(),
            ),
        ),
    )

    def _fake_execute_round_dto(*, session, request, rng):
        return ExecuteRoundOutputDTO(
            logs=["Enemy was defeated."],
            end_reason="enemy_defeated",
            escaped=False,
            enemy_was_physically_hit=True,
            events=[],
            lifecycle=BattleLifecycleDTO(
                before="resolving_round",
                after="battle_finished",
                battle_finished=True,
            ),
        )

    monkeypatch.setattr(flask_app, "execute_round_dto", _fake_execute_round_dto)
    monkeypatch.setattr(
        flask_app,
        "apply_victory_rewards",
        lambda **_kwargs: {
            "gained_exp": 120,
            "gained_gil": 80,
            "gained_cp": 3,
            "dropped_item": [],
            "levelups": [],
        },
    )

    client = app.test_client()
    resp = client.post(
        "/battle/round",
        json={"planned_actions": [None, None], "lifecycle_state": "ready_for_actions"},
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["lifecycle"]["battle_finished"] is True
    assert any("=== Battle Rewards ===" in row for row in payload["logs"])
    assert any("EXP +120" in row for row in payload["logs"])
    assert payload["victory_rewards"]["gained_gil"] == 80
