from random import Random

from combat.models import BattleActorState, FinalCharacterStats, FinalEnemyStats, SpellInfo
from combat.turn_logic import run_character_turn


def _char_stats() -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=1,
        job_skill_point=0,
        max_hp=999,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=20,
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
    )


def _enemy_stats() -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Ifrit",
        hp=500,
        level=20,
        job_level=1,
        attack_power=1,
        attack_multiplier=1,
        accuracy_percent=1,
        defense=10,
        defense_multiplier=1,
        evasion_percent=0,
        magic_defense=12,
        magic_def_multiplier=1,
        magic_resistance_percent=0,
        agility=1,
    )


def test_erase_like_spell_dispels_enemy_buffs_via_metadata() -> None:
    char_stats = _char_stats()
    enemy_stats = _enemy_stats()
    char_state = BattleActorState(hp=999, max_hp=999)
    char_state.mp_pool[5] = 1
    char_state.max_mp_pool[5] = 1
    enemy_state = BattleActorState(hp=500, max_hp=500, reflect_charges=1)
    enemy_stats.haste_power_bonus = 14
    enemy_stats.haste_multiplier_bonus = 2
    enemy_stats.protect_defense_bonus = 9
    enemy_stats.protect_magic_defense_bonus = 9
    enemy_stats.defense += 9
    enemy_stats.magic_defense += 9
    spell_json = {
        "Name": "Null Field",
        "Type": "Black Magic",
        "Level": 5,
        "Target": "One Enemy",
        "Effect": "Dispel buffs",
        "effect_category": "remove_reflect",
        "dispel_effects": "Protect, Haste, Reflect",
        "BaseAccuracy": 1.0,
        "BasePower": 0,
        "Reflectable": "No",
    }
    spell = SpellInfo(0, 100, "black", [], False)
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Runeth",
        enemy_name="Ifrit",
        char_stats=char_stats,
        enemy_stats=enemy_stats,
        enemy_json={"Level": 20, "StatusAilmentVulnerability": {"Immune": []}},
        char_state=char_state,
        enemy_state=enemy_state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=spell,
        char_spell_json=spell_json,
        char_spell_healing_type=None,
        char_spell_name="Null Field",
        char_item=None,
        logs=logs,
        rng=Random(0),
        aoe_selected_override=False,
    )

    assert damage == 0
    assert result is None
    assert enemy_state.reflect_charges == 0
    assert enemy_stats.haste_power_bonus == 0
    assert enemy_stats.haste_multiplier_bonus == 0
    assert enemy_stats.protect_defense_bonus == 0
    assert enemy_stats.protect_magic_defense_bonus == 0
    assert enemy_stats.defense == 10
    assert enemy_stats.magic_defense == 12
    assert any("解除" in line for line in logs)
