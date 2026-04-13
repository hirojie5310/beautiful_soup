# tests/test_runtime_state_data_files.py
from pathlib import Path
import json

from assets.data.data_loader import load_armors, load_savedata, load_weapons
from combat.runtime_state import init_runtime_state


BASE_DIR = Path(__file__).resolve().parents[1]


def test_bonus_equipment_master_files_load_successfully() -> None:
    weapons = load_weapons(BASE_DIR / "assets/data/ffiii_weapons.json")
    armors = load_armors(BASE_DIR / "assets/data/ffiii_armors.json")

    assert weapons["Onion Sword"]["Bonus"] == {
        "Strength": 5,
        "Agility": 5,
        "Vitality": 5,
    }
    assert armors["Protect Ring"]["Bonus"] == {"Vitality": 5}


def test_init_runtime_state_reads_bonus_equipment_data() -> None:
    state = init_runtime_state(base_dir=BASE_DIR)

    assert state.weapons["Ragnarok"]["Bonus"] == {
        "Strength": 5,
        "Agility": 5,
        "Vitality": 5,
    }
    assert state.armors["White Robe"]["Bonus"] == {"Mind": 5}
    assert state.base_dir == BASE_DIR


def test_load_savedata_accepts_v1_envelope_format(tmp_path: Path) -> None:
    path = tmp_path / "savedata_envelope.json"
    payload = {
        "version": 1,
        "saved_at": "2026-03-28T00:00:00Z",
        "save": {"schema_version": 1, "party": [{"name": "Refia"}], "inventory": {}, "gil": 0, "CP": 0},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    loaded = load_savedata(path)

    assert loaded["party"][0]["name"] == "Refia"
    assert loaded["schema_version"] == 1
    assert "save" not in loaded


def test_load_savedata_accepts_legacy_flat_format(tmp_path: Path) -> None:
    path = tmp_path / "savedata_flat.json"
    payload = {"schema_version": 1, "party": [{"name": "Ingus"}], "inventory": {}, "gil": 0, "CP": 0}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    loaded = load_savedata(path)

    assert loaded["party"][0]["name"] == "Ingus"
    assert loaded["schema_version"] == 1
