# tests/test_protect_buff_formula.py
import random

from combat.models import FinalCharacterStats, FinalEnemyStats
from combat.status_effects import (
    apply_protect_buff,
    buff_target_magic_parameters,
    calc_protect_buff_amount,
)


def make_char(
    *,
    level: int = 16,
    job_level: int = 32,
    mind: int = 32,
    defense: int = 10,
    magic_defense: int = 2,
    magic_def_multiplier: int = 1,
    magic_resistance: int = 0
) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=level,
        job_level=job_level,
        job_skill_point=0,
        max_hp=100,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=mind,
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
        defense=defense,
        defense_multiplier=0,
        evasion_percent=0,
        magic_defense=magic_defense,
        magic_def_multiplier=magic_def_multiplier,
        magic_resistance=magic_resistance,
        shield_count=0,
    )


def make_enemy(
    *,
    level: int = 16,
    job_level: int = 32,
    defense: int = 10,
    magic_defense: int = 2,
    magic_def_multiplier: int = 1,
    magic_resistance_percent: int = 0
) -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Enemy",
        hp=100,
        level=level,
        job_level=job_level,
        attack_power=10,
        attack_multiplier=2,
        accuracy_percent=100,
        defense=defense,
        defense_multiplier=0,
        evasion_percent=0,
        magic_defense=magic_defense,
        magic_def_multiplier=magic_def_multiplier,
        magic_resistance_percent=magic_resistance_percent,
        agility=10,
    )


def test_calc_protect_buff_amount_uses_magic_formula_final_damage() -> None:
    add_value = calc_protect_buff_amount(
        base_power=5,
        base_factor=4,
        target_magic_defense=2,
        target_magic_def_multiplier=1,
        target_magic_resistance_percent=0,
        rng=random.Random(0),
    )

    assert add_value == 16


def test_friendly_buff_magic_parameters_zero_mdef_and_multiplier_only() -> None:
    assert buff_target_magic_parameters(
        target_magic_defense=48,
        target_magic_def_multiplier=11,
        target_magic_resistance_percent=37,
        target_is_friendly=True,
    ) == (0, 0, 37)


def test_apply_protect_buff_adds_same_amount_to_defense_and_magic_defense_for_char() -> (
    None
):
    char = make_char()
    magic_defense, magic_def_multiplier, magic_resistance_percent = (
        buff_target_magic_parameters(
            target_magic_defense=char.magic_defense,
            target_magic_def_multiplier=char.magic_def_multiplier,
            target_magic_resistance_percent=char.magic_resistance,
            target_is_friendly=True,
        )
    )

    old_def, old_mdef, add_value = apply_protect_buff(
        char,
        base_power=5,
        base_factor=4,
        rng=random.Random(0),
        target_magic_defense=magic_defense,
        target_magic_def_multiplier=magic_def_multiplier,
        target_magic_resistance_percent=magic_resistance_percent,
    )

    assert (old_def, old_mdef) == (10, 2)
    assert add_value == 24
    assert char.defense == 34
    assert char.magic_defense == 26


def test_apply_protect_buff_uses_enemy_magic_defense_parameters_too() -> None:
    enemy = make_enemy()
    magic_defense, magic_def_multiplier, magic_resistance_percent = (
        buff_target_magic_parameters(
            target_magic_defense=enemy.magic_defense,
            target_magic_def_multiplier=enemy.magic_def_multiplier,
            target_magic_resistance_percent=enemy.magic_resistance_percent,
            target_is_friendly=True,
        )
    )

    old_def, old_mdef, add_value = apply_protect_buff(
        enemy,
        base_power=5,
        base_factor=4,
        rng=random.Random(0),
        target_magic_defense=magic_defense,
        target_magic_def_multiplier=magic_def_multiplier,
        target_magic_resistance_percent=magic_resistance_percent,
    )

    assert (old_def, old_mdef) == (10, 2)
    assert add_value == 24
    assert enemy.defense == 34
    assert enemy.magic_defense == 26


def test_high_magic_defense_friendly_target_no_longer_collapses_to_plus_one() -> None:
    char = make_char(
        level=40,
        job_level=40,
        mind=55,
        defense=25,
        magic_defense=80,
        magic_def_multiplier=12,
    )
    magic_defense, magic_def_multiplier, magic_resistance_percent = (
        buff_target_magic_parameters(
            target_magic_defense=char.magic_defense,
            target_magic_def_multiplier=char.magic_def_multiplier,
            target_magic_resistance_percent=char.magic_resistance,
            target_is_friendly=True,
        )
    )

    _, _, add_value = apply_protect_buff(
        char,
        base_power=5,
        base_factor=(char.mind // 16) + (char.level // 16) + (char.job_level // 32) + 1,
        rng=random.Random(0),
        target_magic_defense=magic_defense,
        target_magic_def_multiplier=magic_def_multiplier,
        target_magic_resistance_percent=magic_resistance_percent,
    )

    assert add_value > 1
