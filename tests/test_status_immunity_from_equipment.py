from random import Random

from combat.enums import Status
from combat.models import BattleActorState, FinalCharacterStats
from combat.status_effects import apply_status_spell_to_char


def make_char_stats(*, status_immunities=()) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=1,
        job_skill_point=0,
        max_hp=999,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=10,
        row="front",
        main_power=1,
        main_accuracy=1,
        main_atk_multiplier=1,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=0,
        off_two=False,
        off_long=False,
        defense=1,
        defense_multiplier=1,
        evasion_percent=0,
        magic_defense=1,
        magic_def_multiplier=1,
        magic_resistance=0,
        shield_count=0,
        status_immunities=frozenset(status_immunities),
    )


def test_equipment_status_immunity_blocks_enemy_status_spell() -> None:
    char_stats = make_char_stats(status_immunities=("Poison",))
    char_state = BattleActorState(hp=300, max_hp=300)
    logs: list[str] = []

    handled = apply_status_spell_to_char(
        spell_json={
            "Name": "Poison",
            "StatusAilment": "Poison",
            "BaseAccuracy": 1.0,
        },
        char_state=char_state,
        char_stats=char_stats,
        char_name="Refia",
        rng=Random(0),
        logs=logs,
    )

    assert handled is True
    assert Status.POISON not in char_state.statuses
    assert any("無効" in line for line in logs)


def test_enemy_erase_dispels_character_buffs() -> None:
    char_stats = make_char_stats()
    char_stats.haste_power_bonus = 12
    char_stats.haste_multiplier_bonus = 3
    char_stats.protect_defense_bonus = 8
    char_stats.protect_magic_defense_bonus = 8
    char_stats.defense += 8
    char_stats.magic_defense += 8
    char_state = BattleActorState(hp=300, max_hp=300)
    char_state.reflect_charges = 1
    logs: list[str] = []

    handled = apply_status_spell_to_char(
        spell_json={
            "Name": "Erase",
            "BaseAccuracy": 1.0,
            "dispel_effects": "Protect, Haste, Reflect",
        },
        char_state=char_state,
        char_stats=char_stats,
        char_name="Refia",
        rng=Random(0),
        logs=logs,
    )

    assert handled is True
    assert char_stats.haste_power_bonus == 0
    assert char_stats.haste_multiplier_bonus == 0
    assert char_stats.protect_defense_bonus == 0
    assert char_stats.protect_magic_defense_bonus == 0
    assert char_stats.defense == 1
    assert char_stats.magic_defense == 1
    assert char_state.reflect_charges == 0
    assert char_state.hp == 300
    assert any("Erase" in line and "解除" in line for line in logs)
