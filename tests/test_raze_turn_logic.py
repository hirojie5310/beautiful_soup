# tests/test_raze_turn_logic.py
from random import Random

from combat.models import (
    BattleActorState,
    EnemyRuntime,
    FinalCharacterStats,
    FinalEnemyStats,
    SpellInfo,
)
from combat.turn_logic import run_character_turn


def make_char_stats() -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=1,
        job_skill_point=0,
        max_hp=2188,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=40,
        row="front",
        main_power=1,
        main_accuracy=1,
        main_atk_multiplier=1,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=1,
        off_two=False,
        off_long=False,
        defense=1,
        defense_multiplier=1,
        evasion_percent=0,
        magic_defense=1,
        magic_def_multiplier=1,
        magic_resistance=0,
        shield_count=0,
    )


def make_enemy_stats() -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Ifrit",
        hp=500,
        level=1,
        job_level=1,
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


def test_single_target_raze_returns_enemy_defeated_immediately():
    char_stats = make_char_stats()
    enemy_stats = make_enemy_stats()
    char_state = BattleActorState(hp=2052, max_hp=2188)
    char_state.mp_pool[5] = 1
    enemy_state = BattleActorState(hp=500, max_hp=500)
    enemy_json = {"Level": 1, "StatusAilmentVulnerability": {"Immune": []}}
    enemies = [
        EnemyRuntime(
            name="Ifrit",
            stats=enemy_stats,
            state=enemy_state,
            json=enemy_json,
        )
    ]
    spell_json = {
        "Name": "Raze",
        "Type": "Black Magic",
        "Level": 5,
        "Target": "All Enemies",
        "Effect": "Inflict KO",
        "StatusAilment": "KO",
        "BaseAccuracy": 1.0,
        "BasePower": 100,
        "Reflectable": "No",
    }
    spell = SpellInfo(100, 100, "black", [], True)
    logs = []

    damage, result = run_character_turn(
        char_name="Runeth",
        enemy_name="Ifrit",
        char_stats=char_stats,
        enemy_stats=enemy_stats,
        enemy_json=enemy_json,
        char_state=char_state,
        enemy_state=enemy_state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=spell,
        char_spell_json=spell_json,
        char_spell_healing_type=None,
        char_spell_name="Raze",
        char_item=None,
        logs=logs,
        rng=Random(0),
        enemies=enemies,
        aoe_selected_override=False,
    )

    assert damage == 0
    assert result is not None
    assert result.end_reason == "enemy_defeated"
    assert enemy_state.hp == 0
    assert any("《Raze》の効果で倒れた" in line for line in logs)
