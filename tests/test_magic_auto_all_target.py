# test_magic_auto_all_target.py
from combat.magic_damage import magic_damage_char_to_enemy
from combat.models import FinalCharacterStats, FinalEnemyStats, SpellInfo


def _caster() -> FinalCharacterStats:
    return FinalCharacterStats(
        level=30,
        job_level=40,
        job_skill_point=0,
        max_hp=9999,
        strength=1,
        agility=1,
        vitality=1,
        intelligence=48,
        mind=1,
        row="front",
        main_power=0,
        main_accuracy=0,
        main_atk_multiplier=1,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=1,
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


def _enemy() -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Test Enemy",
        hp=9999,
        level=1,
        job_level=1,
        attack_power=1,
        attack_multiplier=1,
        accuracy_percent=1,
        defense=0,
        defense_multiplier=0,
        evasion_percent=0,
        magic_defense=0,
        magic_def_multiplier=0,
        magic_resistance_percent=0,
        agility=1,
    )


def test_manual_aoe_still_splits_damage() -> None:
    caster = _caster()
    enemy = _enemy()
    fire = SpellInfo(
        power=50,
        accuracy_percent=100,
        magic_type="black",
        elements=["fire"],
        auto_all_target=False,
    )

    single = magic_damage_char_to_enemy(caster, fire, enemy, use_expectation=True)
    split = magic_damage_char_to_enemy(
        caster,
        fire,
        enemy,
        use_expectation=True,
        split_to_targets=4,
    )

    assert split == int(single / 4)


def test_auto_all_target_spell_ignores_split_penalty() -> None:
    caster = _caster()
    enemy = _enemy()
    quake = SpellInfo(
        power=50,
        accuracy_percent=100,
        magic_type="black",
        elements=["earth"],
        auto_all_target=True,
    )

    single = magic_damage_char_to_enemy(caster, quake, enemy, use_expectation=True)
    split = magic_damage_char_to_enemy(
        caster,
        quake,
        enemy,
        use_expectation=True,
        split_to_targets=4,
    )

    assert split == single
