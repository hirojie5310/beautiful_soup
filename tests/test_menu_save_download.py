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
    assert "party" in saved_calls[0][1]


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
    assert "party" in payload
