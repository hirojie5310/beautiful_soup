# tests/test_elemental_rod_magic_boost.py
from combat.magic_damage import magic_damage_char_to_enemy
from combat.models import FinalCharacterStats, FinalEnemyStats, SpellInfo


def make_char(*, boosts: dict[str, int] | None = None) -> FinalCharacterStats:
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
        magic_defense=0,
        magic_def_multiplier=0,
        magic_resistance=0,
        shield_count=0,
        elemental_magic_boosts=boosts or {},
    )


def make_enemy() -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Test Enemy",
        hp=9999,
        level=10,
        job_level=10,
        attack_power=1,
        attack_multiplier=1,
        accuracy_percent=1,
        defense=0,
        defense_multiplier=0,
        evasion_percent=0,
        magic_defense=0,
        magic_def_multiplier=0,
        magic_resistance_percent=0,
        agility=10,
    )


def test_elemental_rod_boost_applies_20_percent_to_matching_magic() -> None:
    caster = make_char(boosts={"fire": 1})
    enemy = make_enemy()
    spell = SpellInfo(
        power=10, accuracy_percent=100, magic_type="black", elements=["fire"]
    )

    boosted = magic_damage_char_to_enemy(caster, spell, enemy, use_expectation=True)
    base = magic_damage_char_to_enemy(make_char(), spell, enemy, use_expectation=True)

    assert boosted == int(base * 1.2)


def test_dual_wielded_rods_stack_multiplicatively() -> None:
    caster = make_char(boosts={"fire": 2})
    enemy = make_enemy()
    spell = SpellInfo(
        power=10, accuracy_percent=100, magic_type="black", elements=["fire"]
    )

    boosted = magic_damage_char_to_enemy(caster, spell, enemy, use_expectation=True)
    base = magic_damage_char_to_enemy(make_char(), spell, enemy, use_expectation=True)

    assert boosted == int(base * 1.44)


def test_omnirod_boost_matches_any_supported_element() -> None:
    caster = make_char(boosts={"fire": 1, "ice": 1, "thunder": 1})
    enemy = make_enemy()
    thunder_spell = SpellInfo(
        power=10, accuracy_percent=100, magic_type="black", elements=["thunder"]
    )

    boosted = magic_damage_char_to_enemy(
        caster, thunder_spell, enemy, use_expectation=True
    )
    base = magic_damage_char_to_enemy(
        make_char(), thunder_spell, enemy, use_expectation=True
    )

    assert boosted == int(base * 1.2)


def test_non_matching_element_does_not_get_boost() -> None:
    caster = make_char(boosts={"fire": 1})
    enemy = make_enemy()
    spell = SpellInfo(
        power=10, accuracy_percent=100, magic_type="black", elements=["ice"]
    )

    boosted = magic_damage_char_to_enemy(caster, spell, enemy, use_expectation=True)
    base = magic_damage_char_to_enemy(make_char(), spell, enemy, use_expectation=True)

    assert boosted == base
