# tests/test_runtime_state_data_files.py
from pathlib import Path

from assets.data.data_loader import load_armors, load_weapons
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
