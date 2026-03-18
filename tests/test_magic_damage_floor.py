# test_magic_damage_floor.py
from combat.magic_damage import magic_damage_char_to_enemy, magic_damage_enemy_to_char
from combat.models import (
    EnemyCasterStats,
    FinalCharacterStats,
    FinalEnemyStats,
    SpellInfo,
)


def make_char(
    *,
    magic_defense: int = 20,
    magic_def_multiplier: int = 0,
    magic_resistance: int = 0,
) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=10,
        job_level=10,
        job_skill_point=0,
        max_hp=100,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=10,
        row="front",
        main_power=10,
        main_accuracy=100,
        main_atk_multiplier=1,
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
        magic_defense=magic_defense,
        magic_def_multiplier=magic_def_multiplier,
        magic_resistance=magic_resistance,
        shield_count=0,
    )


def make_enemy(
    *,
    magic_defense: int = 20,
    magic_def_multiplier: int = 0,
    magic_resistance_percent: int = 0,
) -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Test Enemy",
        hp=100,
        level=10,
        job_level=10,
        attack_power=1,
        attack_multiplier=1,
        accuracy_percent=1,
        defense=0,
        defense_multiplier=0,
        evasion_percent=0,
        magic_defense=magic_defense,
        magic_def_multiplier=magic_def_multiplier,
        magic_resistance_percent=magic_resistance_percent,
        agility=10,
    )


def test_magic_char_to_enemy_floor_applies_after_total_hits() -> None:
    caster = make_char()
    enemy = make_enemy(magic_defense=20)
    spell = SpellInfo(power=10, accuracy_percent=100, magic_type="black", elements=[])

    damage = magic_damage_char_to_enemy(
        caster=caster,
        spell=spell,
        enemy=enemy,
        use_expectation=True,
    )

    assert damage == 1


def test_magic_char_to_enemy_floor_applies_after_split_penalty() -> None:
    caster = make_char()
    enemy = make_enemy(magic_defense=20)
    spell = SpellInfo(power=10, accuracy_percent=100, magic_type="black", elements=[])

    damage = magic_damage_char_to_enemy(
        caster=caster,
        spell=spell,
        enemy=enemy,
        use_expectation=True,
        split_to_targets=4,
    )

    assert damage == 1


def test_magic_enemy_to_char_floor_applies_after_total_hits() -> None:
    enemy_caster = EnemyCasterStats(
        magic_power_base=10,
        magic_multiplier=1,
        magic_accuracy_percent=100,
    )
    char = make_char(magic_defense=20)

    damage = magic_damage_enemy_to_char(
        enemy_caster=enemy_caster,
        char=char,
        use_expectation=True,
    )

    assert damage == 1


def test_magic_floor_not_applied_when_expected_hits_is_zero() -> None:
    caster = make_char()
    enemy = make_enemy(
        magic_defense=99,
        magic_def_multiplier=10,
        magic_resistance_percent=100,
    )
    spell = SpellInfo(power=10, accuracy_percent=0, magic_type="black", elements=[])

    damage = magic_damage_char_to_enemy(
        caster=caster,
        spell=spell,
        enemy=enemy,
        use_expectation=True,
    )

    assert damage == 0
