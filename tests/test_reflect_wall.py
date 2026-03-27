# tests/test_reflect_wall.py
from random import Random
from types import SimpleNamespace

from combat.models import (
    BattleActorState,
    FinalCharacterStats,
    FinalEnemyStats,
    SpellInfo,
)
from combat.magic_aoe import enemy_cast_aoe_damage_spell_to_party
from combat.status_effects import apply_reflect_to_actor
from combat.turn_logic import run_character_turn


def test_apply_reflect_to_actor_sets_single_charge_once():
    state = BattleActorState(hp=100, max_hp=100)
    logs: list[str] = []

    applied = apply_reflect_to_actor(state, "Refia", logs)

    assert applied is True
    assert state.reflect_charges == 1
    assert logs == ["Refiaは魔法反射のバリアを張った！（Reflect）"]


def test_apply_reflect_to_actor_does_not_refresh_existing_wall():
    state = BattleActorState(hp=100, max_hp=100, reflect_charges=1)
    logs: list[str] = []

    applied = apply_reflect_to_actor(state, "Refia", logs)

    assert applied is False
    assert state.reflect_charges == 1
    assert logs == ["Refiaには既にReflectがかかっている。"]


def _make_char_stats() -> FinalCharacterStats:
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


def _make_enemy_stats() -> FinalEnemyStats:
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


def test_reflect_log_mentions_selected_ally_target():
    caster_stats = _make_char_stats()
    target_stats = _make_char_stats()
    enemy_stats = _make_enemy_stats()
    caster_state = BattleActorState(hp=2052, max_hp=2188)
    caster_state.mp_pool[7] = 4
    caster_state.max_mp_pool[7] = 11
    target_state = BattleActorState(hp=1800, max_hp=2188)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    enemy_json = {"Level": 1, "StatusAilmentVulnerability": {"Immune": []}}
    party_members = [
        SimpleNamespace(name="Runeth", stats=caster_stats, state=caster_state),
        SimpleNamespace(name="Refia", stats=target_stats, state=target_state),
    ]
    spell_json = {
        "name": "Reflect",
        "Name": "Reflect",
        "Type": "White Magic",
        "Level": 7,
        "Target": "One Ally",
        "Effect": "Grant Reflect",
        "BaseAccuracy": 0.75,
        "Reflectable": "No",
    }
    spell = SpellInfo(0, 75, "white", [])
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Runeth",
        enemy_name="Ifrit",
        char_stats=caster_stats,
        enemy_stats=enemy_stats,
        enemy_json=enemy_json,
        char_state=caster_state,
        enemy_state=enemy_state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=spell,
        char_spell_json=spell_json,
        char_spell_healing_type="reflect",
        char_spell_name="Reflect",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="ally",
        target_index=1,
        party_members=party_members,
    )

    assert damage == 0
    assert result is None
    assert target_state.reflect_charges == 1
    assert any("RunethはRefiaに《Reflect》を唱えた！" in line for line in logs)


def test_odin_protective_light_logs_party_wide_reflect():
    caster_stats = _make_char_stats()
    ally_stats = _make_char_stats()
    enemy_stats = _make_enemy_stats()
    caster_state = BattleActorState(hp=2052, max_hp=2188)
    caster_state.mp_pool[6] = 5
    caster_state.max_mp_pool[6] = 5
    ally_state = BattleActorState(hp=1800, max_hp=2188)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    enemy_json = {"Level": 1, "StatusAilmentVulnerability": {"Immune": []}}
    party_members = [
        SimpleNamespace(name="Runeth", stats=caster_stats, state=caster_state),
        SimpleNamespace(name="Ingus", stats=ally_stats, state=ally_state),
    ]
    spell_json = {
        "name": "Odin: Protective Light",
        "Name": "Odin: Protective Light",
        "Type": "Summon",
        "Level": 6,
        "Target": "All Allies",
        "Accuracy": 100,
        "Effect": "Grant Reflect",
    }
    spell = SpellInfo(0, 100, "summon", [])
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Runeth",
        enemy_name="Ifrit",
        char_stats=caster_stats,
        enemy_stats=enemy_stats,
        enemy_json=enemy_json,
        char_state=caster_state,
        enemy_state=enemy_state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=spell,
        char_spell_json=spell_json,
        char_spell_healing_type="reflect",
        char_spell_name="Odin: Protective Light",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="ally",
        target_index=0,
        party_members=party_members,
    )

    assert damage == 0
    assert result is None
    assert caster_state.reflect_charges == 1
    assert ally_state.reflect_charges == 1
    assert any("守護の光が味方全員を包み" in line for line in logs)


def test_enemy_aoe_reflect_redirects_to_another_enemy_member():
    char_stats = _make_char_stats()
    enemy_stats = _make_enemy_stats()
    ally_enemy_stats = FinalEnemyStats(
        name="Vulcan",
        hp=260,
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
    char_state = BattleActorState(hp=2000, max_hp=2188, reflect_charges=1)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    ally_enemy_state = BattleActorState(hp=260, max_hp=260)
    logs: list[str] = []

    enemy_down = enemy_cast_aoe_damage_spell_to_party(
        spell_json={
            "Name": "Blizzara",
            "Accuracy": 100,
            "Power": 46,
            "Multiplier": 1,
            "Reflectable": "Yes",
            "Element": "Ice",
        },
        enemy_name="Dracrocotta",
        party_members=[
            SimpleNamespace(name="Runeth", stats=char_stats, state=char_state)
        ],
        enemies=[
            SimpleNamespace(name="Dracrocotta", label="Dracrocotta", state=enemy_state),
            SimpleNamespace(name="Vulcan", label="Vulcan", state=ally_enemy_state),
        ],
        rng=Random(0),
        logs=logs,
        caster_state=enemy_state,
        caster_max_hp=500,
    )

    assert enemy_down is False
    assert enemy_state.hp == 500
    assert ally_enemy_state.hp < 260
    assert any("Vulcan" in line and "跳ね返した" in line for line in logs)


def test_enemy_aoe_reflect_ko_does_not_report_enemy_defeated_if_enemy_side_still_alive():
    char_stats = _make_char_stats()
    char_state = BattleActorState(hp=2000, max_hp=2188, reflect_charges=1)
    caster_enemy_state = BattleActorState(hp=500, max_hp=500)
    ko_enemy_state = BattleActorState(hp=10, max_hp=10)
    alive_enemy_state = BattleActorState(hp=260, max_hp=260)
    logs: list[str] = []

    enemy_down = enemy_cast_aoe_damage_spell_to_party(
        spell_json={
            "Name": "Snow Storm",
            "Accuracy": 100,
            "Power": 46,
            "Multiplier": 1,
            "Reflectable": "Yes",
            "Element": "Ice",
        },
        enemy_name="Dracrocotta",
        party_members=[
            SimpleNamespace(name="Runeth", stats=char_stats, state=char_state)
        ],
        enemies=[
            SimpleNamespace(
                name="Dracrocotta", label="Dracrocotta", state=caster_enemy_state
            ),
            SimpleNamespace(name="Skeleton", label="Skeleton", state=ko_enemy_state),
            SimpleNamespace(name="Vulcan", label="Vulcan", state=alive_enemy_state),
        ],
        rng=Random(0),
        logs=logs,
        caster_state=caster_enemy_state,
        caster_max_hp=500,
    )

    assert ko_enemy_state.hp == 0
    assert alive_enemy_state.hp == 260
    assert enemy_down is False


def test_character_spell_reflect_redirects_to_a_party_member():
    caster_stats = _make_char_stats()
    ally_stats = _make_char_stats()
    enemy_stats = _make_enemy_stats()
    caster_state = BattleActorState(hp=2052, max_hp=2188)
    caster_state.mp_pool[7] = 4
    caster_state.max_mp_pool[7] = 11
    ally_state = BattleActorState(hp=1800, max_hp=2188)
    enemy_state = BattleActorState(hp=500, max_hp=500, reflect_charges=1)
    enemy_json = {"Level": 1, "StatusAilmentVulnerability": {"Immune": []}}
    party_members = [
        SimpleNamespace(name="Runeth", stats=caster_stats, state=caster_state),
        SimpleNamespace(name="Ingus", stats=ally_stats, state=ally_state),
    ]
    spell_json = {
        "name": "Blizzara",
        "Name": "Blizzara",
        "Type": "White Magic",
        "Level": 7,
        "Target": "One Enemy",
        "Effect": "Deal Ice damage",
        "BaseAccuracy": 1.0,
        "BasePower": 46,
        "Reflectable": "Yes",
        "Element": "Ice",
    }
    spell = SpellInfo(46, 100, "white", ["ice"])
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Runeth",
        enemy_name="Dracrocotta",
        char_stats=caster_stats,
        enemy_stats=enemy_stats,
        enemy_json=enemy_json,
        char_state=caster_state,
        enemy_state=enemy_state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=spell,
        char_spell_json=spell_json,
        char_spell_healing_type=None,
        char_spell_name="Blizzara",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="enemy",
        target_index=0,
        party_members=party_members,
    )

    assert damage == 0
    assert result is None
    assert caster_state.hp == 2052
    assert ally_state.hp < 1800
    assert any("Ingus" in line and "跳ね返した" in line for line in logs)
