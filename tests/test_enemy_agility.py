# test_enemy_agility.py
from combat.enemy_build import compute_enemy_base_agility


def test_enemy_base_agility_uses_rebalanced_coefficients_low_level() -> None:
    monster = {
        "Level": 2,
        "Attack": {"Count": 3},
        "Evasion": {"Rate": 0.1},
    }

    assert compute_enemy_base_agility(monster) == 5


def test_enemy_base_agility_floors_fractional_result() -> None:
    monster = {
        "Level": 40,
        "Attack": {"Count": 8},
        "Evasion": {"Rate": 0.5},
    }

    assert compute_enemy_base_agility(monster) == 35


def test_enemy_base_agility_reduces_level_weight_above_50() -> None:
    monster = {
        "Level": 69,
        "Attack": {"Count": 3},
        "Evasion": {"Rate": 0.1},
    }

    assert compute_enemy_base_agility(monster) == 31
