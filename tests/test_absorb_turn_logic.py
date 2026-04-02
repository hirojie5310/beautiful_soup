from random import Random

from combat.models import (
    BattleActorState,
    FinalCharacterStats,
    FinalEnemyStats,
    SpellInfo,
)
from combat.turn_logic import run_character_turn


def make_char_stats() -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=10,
        job_skill_point=0,
        max_hp=300,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=40,
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
    )


def make_enemy_stats() -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Bomb",
        hp=100,
        level=10,
        job_level=1,
        attack_power=1,
        attack_multiplier=1,
        accuracy_percent=1,
        defense=1,
        defense_multiplier=1,
        evasion_percent=0,
        magic_defense=0,
        magic_def_multiplier=0,
        magic_resistance_percent=0,
        agility=1,
    )


def test_single_target_absorb_magic_heals_enemy_instead_of_dealing_one_damage() -> None:
    char_stats = make_char_stats()
    enemy_stats = make_enemy_stats()
    char_state = BattleActorState(hp=300, max_hp=300)
    char_state.mp_pool[1] = 10
    enemy_state = BattleActorState(hp=40, max_hp=100)
    enemy_json = {
        "ElementalVulnerability": {"Absorb": ["Fire"]},
        "StatusAilmentVulnerability": {"Immune": []},
    }
    spell_json = {
        "Name": "Fire",
        "Type": "Black Magic",
        "Level": 1,
        "Target": "One Enemy",
        "Effect": "Deal Fire damage",
        "Element": "Fire",
        "BaseAccuracy": 1.0,
        "BasePower": 24,
        "Reflectable": "No",
    }
    spell = SpellInfo(
        power=24,
        accuracy_percent=100,
        magic_type="black",
        elements=["fire"],
        auto_all_target=False,
    )
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Refia",
        enemy_name="Bomb",
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
        char_spell_name="Fire",
        char_item=None,
        logs=logs,
        rng=Random(0),
    )

    assert damage == 0
    assert result is None
    assert enemy_state.hp > 40
    assert any("HPが" in line and "回復" in line for line in logs)


def test_absorb_auto_all_target_quake_fully_heals_enemy() -> None:
    char_stats = make_char_stats()
    enemy_stats = make_enemy_stats()
    char_state = BattleActorState(hp=300, max_hp=300)
    char_state.mp_pool[5] = 10
    enemy_state = BattleActorState(hp=1, max_hp=100)
    enemy_json = {
        "ElementalVulnerability": {"Absorb": ["Earth"]},
        "StatusAilmentVulnerability": {"Immune": []},
    }
    spell_json = {
        "Name": "Quake",
        "Type": "Black Magic",
        "Level": 5,
        "Target": "All Enemies",
        "Effect": "Deal Earth damage",
        "Element": "Earth",
        "BaseAccuracy": 1.0,
        "BasePower": 50,
        "Reflectable": "No",
    }
    spell = SpellInfo(
        power=50,
        accuracy_percent=100,
        magic_type="black",
        elements=["earth"],
        auto_all_target=True,
    )
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Refia",
        enemy_name="Bomb",
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
        char_spell_name="Quake",
        char_item=None,
        logs=logs,
        rng=Random(0),
        enemies=[],
        aoe_selected_override=False,
    )

    assert damage == 0
    assert result is None
    assert enemy_state.hp == 100
