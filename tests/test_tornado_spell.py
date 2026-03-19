# tests/test_tornado_spell.py
from random import Random
from types import SimpleNamespace

from combat.magic_damage import apply_tornado_to_state
from combat.models import (
    BattleActorState,
    FinalCharacterStats,
    FinalEnemyStats,
    SpellInfo,
)
from combat.turn_logic import run_character_turn


def _char_stats() -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=9999,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=20,
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


def _enemy_stats(*, magic_def_multiplier: int = 0) -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Goblin",
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
        magic_def_multiplier=magic_def_multiplier,
        magic_resistance_percent=0,
        agility=1,
    )


def test_apply_tornado_sets_hp_into_spell_damage_range() -> None:
    state = BattleActorState(hp=400, max_hp=400)
    logs: list[str] = []

    damage = apply_tornado_to_state(
        target_state=state,
        target_name="Goblin",
        spell_damage=4,
        rng=Random(0),
        logs=logs,
        prefix="Refiaは《Tornado》を唱えた！ ",
    )

    assert 4 <= state.hp <= 8
    assert damage == 400 - state.hp
    assert any("Tornado" in line for line in logs)


def test_tornado_ignores_final_damage_formula_and_still_works_when_m_hits() -> None:
    caster_stats = _char_stats()
    enemy_stats = _enemy_stats(magic_def_multiplier=99)
    caster_state = BattleActorState(hp=999, max_hp=9999)
    caster_state.mp_pool[8] = 1
    caster_state.max_mp_pool[8] = 1
    enemy_state = BattleActorState(hp=500, max_hp=500)
    tornado = SpellInfo(
        power=4, accuracy_percent=100, magic_type="white", elements=["air"]
    )
    spell_json = {
        "name": "Tornado",
        "Type": "White Magic",
        "Level": 8,
        "Target": "One/All Enemies",
        "Element": "Air",
        "BasePower": 4,
        "BaseAccuracy": 1.0,
        "Reflectable": "No",
    }
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Refia",
        enemy_name="Goblin",
        char_stats=caster_stats,
        enemy_stats=enemy_stats,
        enemy_json={},
        char_state=caster_state,
        enemy_state=enemy_state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=tornado,
        char_spell_json=spell_json,
        char_spell_healing_type=None,
        char_spell_name="Tornado",
        char_item=None,
        logs=logs,
        rng=Random(1),
        target_side="enemy",
        target_index=0,
        party_members=[
            SimpleNamespace(name="Refia", stats=caster_stats, state=caster_state)
        ],
        aoe_selected_override=False,
    )

    assert result is None
    assert 4 <= enemy_state.hp <= 8
    assert enemy_state.hp < 100
    assert damage == 500 - enemy_state.hp
    assert any("Tornado" in line for line in logs)


def test_tornado_can_fail_when_magic_hit_count_is_zero() -> None:
    caster_stats = _char_stats()
    enemy_stats = FinalEnemyStats(
        name="Resist Slime",
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
        magic_def_multiplier=4,
        magic_resistance_percent=100,
        agility=1,
    )
    caster_state = BattleActorState(hp=999, max_hp=9999)
    caster_state.mp_pool[8] = 1
    caster_state.max_mp_pool[8] = 1
    enemy_state = BattleActorState(hp=500, max_hp=500)
    tornado = SpellInfo(
        power=4, accuracy_percent=40, magic_type="white", elements=["air"]
    )
    spell_json = {
        "name": "Tornado",
        "Type": "White Magic",
        "Level": 8,
        "Target": "One/All Enemies",
        "Element": "Air",
        "BasePower": 4,
        "BaseAccuracy": 0.4,
        "Reflectable": "No",
    }
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Runeth",
        enemy_name="Resist Slime",
        char_stats=caster_stats,
        enemy_stats=enemy_stats,
        enemy_json={},
        char_state=caster_state,
        enemy_state=enemy_state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=tornado,
        char_spell_json=spell_json,
        char_spell_healing_type=None,
        char_spell_name="Tornado",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="enemy",
        target_index=0,
        party_members=[
            SimpleNamespace(name="Runeth", stats=caster_stats, state=caster_state)
        ],
        aoe_selected_override=False,
    )

    assert result is None
    assert damage == 0
    assert enemy_state.hp == 500
    assert any("効かなかった" in line for line in logs)


def test_tornado_does_not_work_on_plot_battle_boss() -> None:
    caster_stats = _char_stats()
    enemy_stats = _enemy_stats()
    caster_state = BattleActorState(hp=999, max_hp=9999)
    caster_state.mp_pool[8] = 1
    caster_state.max_mp_pool[8] = 1
    enemy_state = BattleActorState(hp=29000, max_hp=29000)
    tornado = SpellInfo(
        power=4, accuracy_percent=100, magic_type="white", elements=["air"]
    )
    spell_json = {
        "name": "Tornado",
        "Type": "White Magic",
        "Level": 8,
        "Target": "One/All Enemies",
        "Element": "Air",
        "BasePower": 4,
        "BaseAccuracy": 1.0,
        "Reflectable": "No",
    }
    enemy_json = {
        "name": "Two Headed Dragon",
        "PlotBattles": [{"Map": "World of Darkness Northeast"}],
    }
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Runeth",
        enemy_name="Two Headed Dragon",
        char_stats=caster_stats,
        enemy_stats=enemy_stats,
        enemy_json=enemy_json,
        char_state=caster_state,
        enemy_state=enemy_state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=tornado,
        char_spell_json=spell_json,
        char_spell_healing_type=None,
        char_spell_name="Tornado",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="enemy",
        target_index=0,
        party_members=[
            SimpleNamespace(name="Runeth", stats=caster_stats, state=caster_state)
        ],
        aoe_selected_override=False,
    )

    assert result is None
    assert damage == 0
    assert enemy_state.hp == 29000
    assert any("効かなかった" in line for line in logs)


def test_tornado_aoe_skips_plot_battle_boss_and_hits_normal_enemy() -> None:
    caster_stats = _char_stats()
    caster_state = BattleActorState(hp=999, max_hp=9999)
    caster_state.mp_pool[8] = 1
    caster_state.max_mp_pool[8] = 1
    boss_state = BattleActorState(hp=29000, max_hp=29000)
    normal_state = BattleActorState(hp=500, max_hp=500)
    tornado = SpellInfo(
        power=4, accuracy_percent=100, magic_type="white", elements=["air"]
    )
    spell_json = {
        "name": "Tornado",
        "Type": "White Magic",
        "Level": 8,
        "Target": "One/All Enemies",
        "Element": "Air",
        "BasePower": 4,
        "BaseAccuracy": 1.0,
        "Reflectable": "No",
    }
    boss = SimpleNamespace(
        name="Cerberus",
        state=boss_state,
        stats=_enemy_stats(),
        json={"name": "Cerberus", "PlotBattles": [{"Map": "Eureka"}]},
    )
    normal = SimpleNamespace(
        name="Goblin",
        state=normal_state,
        stats=_enemy_stats(),
        json={"name": "Goblin"},
    )
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Runeth",
        enemy_name="Cerberus",
        char_stats=caster_stats,
        enemy_stats=boss.stats,
        enemy_json=boss.json,
        char_state=caster_state,
        enemy_state=boss_state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=tornado,
        char_spell_json=spell_json,
        char_spell_healing_type=None,
        char_spell_name="Tornado",
        char_item=None,
        logs=logs,
        rng=Random(1),
        target_side="enemy",
        target_index=0,
        party_members=[
            SimpleNamespace(name="Runeth", stats=caster_stats, state=caster_state)
        ],
        enemies=[boss, normal],
        aoe_selected_override=True,
    )

    assert result is None
    assert boss_state.hp == 29000
    assert 4 <= normal_state.hp <= 8
    assert damage == 500 - normal_state.hp
    assert any("Cerberusには効かなかった" in line for line in logs)
    assert any("Goblin" in line and "Tornado" in line for line in logs)
