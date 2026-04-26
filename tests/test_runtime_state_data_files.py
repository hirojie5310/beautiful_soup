# tests/test_runtime_state_data_files.py
from pathlib import Path
import json

from assets.data.data_loader import (
    load_armors,
    load_items,
    load_jobs,
    load_savedata,
    load_spells,
    load_weapons,
)
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


def test_load_spells_prefers_lowercase_name_key() -> None:
    spells = load_spells(BASE_DIR / "assets/data/ffiii_spells.json")

    flare = spells["Flare"]

    assert flare["name"] == "Flare"
    assert "Name" not in flare


def test_spell_nested_monsters_and_summons_use_lowercase_name_key() -> None:
    raw = json.loads((BASE_DIR / "assets/data/ffiii_spells.json").read_text())
    nested_monsters = [
        row
        for spell in raw["spells"]
        for row in spell.get("Monsters", [])
    ]
    nested_summons = [
        row
        for spell in raw["spells"]
        for row in spell.get("Spells", [])
    ]

    assert nested_monsters
    assert nested_summons
    assert all("name" in row and "Name" not in row for row in nested_monsters)
    assert all("name" in row and "Name" not in row for row in nested_summons)


def test_items_and_spell_nested_items_use_lowercase_name_key() -> None:
    items = load_items(BASE_DIR / "assets/data/ffiii_items.json")
    potion = items["Potion"]
    raw_spells = json.loads((BASE_DIR / "assets/data/ffiii_spells.json").read_text())
    nested_items = [
        row
        for spell in raw_spells["spells"]
        for row in spell.get("Items", [])
    ]

    assert potion["name"] == "Potion"
    assert "Name" not in potion
    assert nested_items
    assert all("name" in row and "Name" not in row for row in nested_items)


def test_master_data_name_keys_are_lowercase() -> None:
    paths = [
        BASE_DIR / "assets/data/ffiii_spells.json",
        BASE_DIR / "assets/data/ffiii_armors.json",
        BASE_DIR / "assets/data/ffiii_items.json",
        BASE_DIR / "assets/data/ffiii_jobs_compact.json",
        BASE_DIR / "assets/data/ffiii_monsters.json",
        BASE_DIR / "assets/data/ffiii_weapons.json",
    ]

    def count_upper_name(value: object) -> int:
        if isinstance(value, list):
            return sum(count_upper_name(row) for row in value)
        if isinstance(value, dict):
            return int("Name" in value) + sum(
                count_upper_name(row) for row in value.values()
            )
        return 0

    for path in paths:
        assert count_upper_name(json.loads(path.read_text())) == 0, path.name


def test_load_jobs_uses_lowercase_name_key() -> None:
    jobs = load_jobs(BASE_DIR / "assets/data/ffiii_jobs_compact.json")

    assert "Onion Knight" in jobs
    assert jobs["Onion Knight"].raw["name"] == "Onion Knight"
    assert "Name" not in jobs["Onion Knight"].raw


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
