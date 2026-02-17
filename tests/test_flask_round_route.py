# tests/test_flask_round_route.py
from __future__ import annotations

from dataclasses import dataclass

import pytest

pytest.importorskip("flask")

from combat.dto import BattleLifecycleDTO, ExecuteRoundOutputDTO, LIFECYCLE_READY
from combat.errors import DomainError, InputValidationError, InvalidLifecycleError


@dataclass
class _DummyMember:
    state: object


@dataclass
class _DummySession:
    party_members: list[_DummyMember]
    enemies: list[_DummyMember]


def _build_app(monkeypatch, *, expected_actions: int = 4):
    import adapters.flask_app as flask_app

    app = flask_app.create_app(
        session=_DummySession(
            party_members=[_DummyMember(state=object()) for _ in range(expected_actions)],
            enemies=[_DummyMember(state=object()) for _ in range(3)],
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
    assert "Battle API Playground" in body
    assert "POST /battle/round" in body
    assert "Action Builder" in body
    assert "JSONへ反映" in body
    assert "敵の数" in body
    assert "味方HP" in body
    assert "敵HP" in body
    assert "Battle setup" in body
    assert "LocationGroup" in body

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
