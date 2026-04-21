from random import Random

from combat.models import (
    BattleActorState,
    FinalCharacterStats,
    FinalEnemyStats,
    PlannedEnemyAction,
)
from combat.runtime_state import init_runtime_state
from combat.turn_logic import run_enemy_turn


def _char_stats() -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=999,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=20,
        row="front",
        main_power=10,
        main_accuracy=10,
        main_atk_multiplier=1,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=0,
        off_two=False,
        off_long=False,
        defense=10,
        defense_multiplier=0,
        evasion_percent=0,
        magic_defense=10,
        magic_def_multiplier=0,
        magic_resistance=0,
        shield_count=0,
    )


def _enemy_stats() -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Mage",
        hp=500,
        level=20,
        job_level=20,
        attack_power=1,
        attack_multiplier=1,
        accuracy_percent=1,
        defense=1,
        defense_multiplier=1,
        evasion_percent=0,
        magic_defense=1,
        magic_def_multiplier=1,
        magic_resistance_percent=0,
        agility=1,
    )


def test_enemy_buff_attack_spell_uses_effect_category_without_haste_name() -> None:
    char_stats = _char_stats()
    enemy_stats = _enemy_stats()
    char_state = BattleActorState(hp=999, max_hp=999)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    spell_json = {
        "Name": "War Cry",
        "Type": "White Magic",
        "BasePower": 5,
        "BaseAccuracy": 1.0,
        "effect_category": "buff_attack",
    }
    enemy_json = {
        "SpecialAttackRate": 1.0,
        "Special Attacks": [{"Attack": "War Cry", "Rate": 1.0}],
        "Spells": [spell_json],
    }
    logs: list[str] = []

    result = run_enemy_turn(
        char_name="Refia",
        enemy_name="Mage",
        char_stats=char_stats,
        enemy_stats=enemy_stats,
        enemy_json=enemy_json,
        char_state=char_state,
        enemy_state=enemy_state,
        char_attack_kind="fight",
        dmg_to_enemy=0,
        char_conf=False,
        char_is_mini_or_toad=False,
        logs=logs,
        state=init_runtime_state(),
        rng=Random(0),
        planned_enemy_action=PlannedEnemyAction(
            kind="special",
            spell_name="War Cry",
            spell_json=spell_json,
        ),
    )

    assert result.end_reason == "continue"
    assert enemy_stats.haste_power_bonus > 0
    assert enemy_stats.haste_multiplier_bonus > 0
    assert any("《War Cry》" in line and "物理加算値" in line for line in logs)


def test_enemy_buff_defense_spell_uses_effect_category_without_protect_name() -> None:
    char_stats = _char_stats()
    enemy_stats = _enemy_stats()
    char_state = BattleActorState(hp=999, max_hp=999)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    spell_json = {
        "Name": "Stone Skin",
        "Type": "White Magic",
        "BasePower": 5,
        "BaseAccuracy": 1.0,
        "effect_category": "buff_defense",
    }
    enemy_json = {
        "SpecialAttackRate": 1.0,
        "Special Attacks": [{"Attack": "Stone Skin", "Rate": 1.0}],
        "Spells": [spell_json],
    }
    logs: list[str] = []

    result = run_enemy_turn(
        char_name="Refia",
        enemy_name="Mage",
        char_stats=char_stats,
        enemy_stats=enemy_stats,
        enemy_json=enemy_json,
        char_state=char_state,
        enemy_state=enemy_state,
        char_attack_kind="fight",
        dmg_to_enemy=0,
        char_conf=False,
        char_is_mini_or_toad=False,
        logs=logs,
        state=init_runtime_state(),
        rng=Random(0),
        planned_enemy_action=PlannedEnemyAction(
            kind="special",
            spell_name="Stone Skin",
            spell_json=spell_json,
        ),
    )

    assert result.end_reason == "continue"
    assert enemy_stats.defense > 1
    assert enemy_stats.magic_defense > 1
    assert any("《Stone Skin》" in line and "防御力" in line for line in logs)
