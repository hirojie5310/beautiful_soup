# tests/test_haste_buff_formula.py
import random

from combat.models import FinalCharacterStats, FinalEnemyStats
from combat.phys_damage import physical_damage_char_to_enemy
from combat.status_effects import apply_haste_buff


def make_char() -> FinalCharacterStats:
    return FinalCharacterStats(
        level=16,
        job_level=32,
        job_skill_point=0,
        max_hp=100,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=32,
        row="front",
        main_power=10,
        main_accuracy=100,
        main_atk_multiplier=2,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=0,
        off_two=False,
        off_long=False,
        defense=0,
        defense_multiplier=0,
        evasion_percent=0,
        magic_defense=0,
        magic_def_multiplier=0,
        magic_resistance=0,
        shield_count=0,
    )


def make_enemy() -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Enemy",
        hp=100,
        level=10,
        job_level=10,
        attack_power=10,
        attack_multiplier=2,
        accuracy_percent=100,
        defense=0,
        defense_multiplier=0,
        evasion_percent=0,
        magic_defense=2,
        magic_def_multiplier=1,
        magic_resistance_percent=0,
        agility=10,
    )


def test_apply_haste_buff_stores_transferred_formula_values() -> None:
    char = make_char()
    rng = random.Random(0)

    (
        old_power_bonus,
        new_power_bonus,
        old_mul_bonus,
        new_mul_bonus,
        add_power,
        add_mul,
    ) = apply_haste_buff(
        char,
        base_power=5,
        base_factor=4,
        rng=rng,
        target_magic_defense=2,
        target_magic_def_multiplier=1,
        target_magic_resistance_percent=0,
    )

    assert (old_power_bonus, old_mul_bonus) == (0, 0)
    assert (new_power_bonus, new_mul_bonus) == (add_power, add_mul)
    assert add_power == 16
    assert add_mul == 4
    assert char.main_power == 10
    assert char.main_atk_multiplier == 2


def test_physical_damage_uses_haste_bonus_without_mutating_base_stats() -> None:
    char = make_char()
    enemy = make_enemy()
    rng = random.Random(0)

    apply_haste_buff(
        char,
        base_power=5,
        base_factor=4,
        rng=rng,
        target_magic_defense=2,
        target_magic_def_multiplier=1,
        target_magic_resistance_percent=0,
    )

    result = physical_damage_char_to_enemy(char, enemy, use_expectation=True)

    assert char.main_power == 10
    assert char.main_atk_multiplier == 2
    assert result.hit_count == 6
    assert result.damage == 190
