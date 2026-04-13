# tests/test_menu_save_download.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("flask")

from adapters.flask_app import create_app


def test_menu_save_persists_file_and_returns_download_url(monkeypatch):
    app = create_app()
    client = app.test_client()

    saved_calls: list[tuple[Path, dict]] = []

    def fake_save_savedata(path: Path, save: dict) -> None:
        saved_calls.append((path, json.loads(json.dumps(save))))

    monkeypatch.setattr("adapters.flask_app.save_savedata", fake_save_savedata)

    resp = client.post("/menu/save", json={})

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload == {
        "ok": True,
        "message": "セーブしました",
        "download_url": "/menu/save/download",
        "filename": "ffiii_savedata.json",
    }
    assert saved_calls
    assert saved_calls[0][0] == Path("assets/data/ffiii_savedata.json")
    assert isinstance(saved_calls[0][1], dict)
    assert saved_calls[0][1]["version"] == 1
    assert saved_calls[0][1]["save"]["schema_version"] == 1
    assert "saved_at" in saved_calls[0][1]
    assert "selected_location_group" in saved_calls[0][1]
    assert "selected_location" in saved_calls[0][1]
    assert "party" in saved_calls[0][1]["save"]


def test_menu_save_download_returns_json_attachment():
    app = create_app()
    client = app.test_client()

    resp = client.get("/menu/save/download")

    assert resp.status_code == 200
    assert resp.mimetype == "application/json"
    assert "attachment;" in resp.headers["Content-Disposition"]
    assert "ffiii_savedata.json" in resp.headers["Content-Disposition"]

    payload = json.loads(resp.get_data(as_text=True))
    assert isinstance(payload, dict)
    assert payload["version"] == 1
    assert payload["save"]["schema_version"] == 1
    assert "saved_at" in payload
    assert "selected_location_group" in payload
    assert "selected_location" in payload
    assert "party" in payload["save"]


def test_menu_save_persists_latest_progress_fields_after_victory_round(monkeypatch):
    app = create_app()
    client = app.test_client()

    saved_calls: list[tuple[Path, dict]] = []

    def fake_execute_round_dto(*, session, request, rng):
        del session, request, rng
        return type(
            "Output",
            (),
            {
                "logs": ["Victory!"],
                "end_reason": "enemy_defeated",
                "escaped": False,
                "enemy_was_physically_hit": True,
                "events": [],
                "event_blocks": [],
                "lifecycle": type(
                    "Lifecycle",
                    (),
                    {
                        "before": "resolving_round",
                        "after": "battle_finished",
                        "battle_finished": True,
                    },
                )(),
            },
        )()

    def fake_apply_victory_rewards(*, party_members, enemies, state, level_table):
        del party_members, enemies, level_table
        state.save["party"][0]["exp"] = 24680
        state.save["party"][0]["job_level"] = {"level": 23, "skill_point": 45}
        state.save["gil"] = 1111
        state.save["CP"] = 222
        state.save["inventory"] = {"Anywhere": {"Hi-Potion": 3}}
        return {
            "gained_exp": 24680,
            "gained_gil": 0,
            "gained_cp": 0,
            "dropped_item": [],
            "levelups": [],
        }

    def fake_save_savedata(path: Path, save: dict) -> None:
        saved_calls.append((path, json.loads(json.dumps(save))))

    monkeypatch.setattr("adapters.flask_app.execute_round_dto", fake_execute_round_dto)
    monkeypatch.setattr(
        "adapters.flask_app.apply_victory_rewards", fake_apply_victory_rewards
    )
    monkeypatch.setattr("adapters.flask_app.save_savedata", fake_save_savedata)

    round_resp = client.post(
        "/battle/round",
        json={"planned_actions": [], "lifecycle_state": "ready_for_actions"},
    )
    assert round_resp.status_code == 200

    save_resp = client.post("/menu/save", json={})
    assert save_resp.status_code == 200
    assert saved_calls
    saved_payload = saved_calls[0][1]
    assert saved_payload["version"] == 1
    assert saved_payload["save"]["schema_version"] == 1
    assert saved_payload["save"]["party"][0]["exp"] == 24680
    assert saved_payload["save"]["party"][0]["job_level"]["level"] == 23
    assert saved_payload["save"]["party"][0]["job_level"]["skill_point"] == 45
    assert saved_payload["save"]["gil"] == 1111
    assert saved_payload["save"]["CP"] == 222
    assert saved_payload["save"]["inventory"]["Anywhere"]["Hi-Potion"] == 3
