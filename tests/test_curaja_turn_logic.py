# tests/test_curaja_turn_logic.py
from random import Random
from types import SimpleNamespace

from combat.enums import Status
from combat.models import (
    BattleActorState,
    FinalCharacterStats,
    FinalEnemyStats,
    SpellInfo,
)
from combat.magic_damage import magic_heal_amount_to_char
from combat.turn_logic import run_character_turn


def _char_stats(*, max_hp: int = 9999) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=max_hp,
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


def _enemy_stats() -> FinalEnemyStats:
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
        magic_def_multiplier=1,
        magic_resistance_percent=0,
        agility=1,
    )


def test_curaja_single_target_fully_heals_selected_ally() -> None:
    caster_stats = _char_stats(max_hp=9999)
    target_stats = _char_stats(max_hp=1800)
    enemy_stats = _enemy_stats()
    caster_state = BattleActorState(hp=1500, max_hp=9999)
    caster_state.mp_pool[7] = 1
    caster_state.max_mp_pool[7] = 1
    target_state = BattleActorState(hp=123, max_hp=1800)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    curaja = SpellInfo(power=80, accuracy_percent=100, magic_type="white", elements=[])
    spell_json = {
        "Name": "Curaja",
        "Type": "White Magic",
        "Level": 7,
        "Target": "One/All Allies",
        "Effect": "Restore target's HP",
        "field_heal_hp": 9999,
        "target_scope": "one_or_all",
        "default_target_side": "Any",
    }
    party = [
        SimpleNamespace(name="Refia", stats=caster_stats, state=caster_state),
        SimpleNamespace(name="Ingus", stats=target_stats, state=target_state),
    ]
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
        char_spell=curaja,
        char_spell_json=spell_json,
        char_spell_healing_type="hp",
        char_spell_name="Curaja",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="ally",
        target_index=1,
        party_members=party,
        aoe_selected_override=False,
    )

    assert damage == 0
    assert result is None
    assert target_state.hp == target_stats.max_hp


def test_curaja_multi_target_uses_normal_heal_route() -> None:
    caster_stats = _char_stats(max_hp=9999)
    ally1_stats = _char_stats(max_hp=1800)
    ally2_stats = _char_stats(max_hp=1900)
    enemy_stats = _enemy_stats()
    caster_state = BattleActorState(hp=1500, max_hp=9999)
    caster_state.mp_pool[7] = 1
    caster_state.max_mp_pool[7] = 1
    ally1_state = BattleActorState(hp=100, max_hp=1800)
    ally2_state = BattleActorState(hp=200, max_hp=1900)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    curaja = SpellInfo(power=80, accuracy_percent=100, magic_type="white", elements=[])
    spell_json = {
        "Name": "Curaja",
        "Type": "White Magic",
        "Level": 7,
        "Target": "One/All Allies",
        "Effect": "Restore target's HP",
        "field_heal_hp": 9999,
        "target_scope": "one_or_all",
        "default_target_side": "Any",
    }
    party = [
        SimpleNamespace(name="Refia", stats=caster_stats, state=caster_state),
        SimpleNamespace(name="Ingus", stats=ally1_stats, state=ally1_state),
        SimpleNamespace(name="Arc", stats=ally2_stats, state=ally2_state),
    ]
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
        char_spell=curaja,
        char_spell_json=spell_json,
        char_spell_healing_type="hp",
        char_spell_name="Curaja",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="ally",
        target_index=1,
        party_members=party,
        aoe_selected_override=True,
    )

    assert damage == 0
    assert result is None
    assert ally1_state.hp < ally1_stats.max_hp
    assert ally2_state.hp < ally2_stats.max_hp
    assert any("味方全体" in line for line in logs)


def test_single_target_heal_log_displays_spell_amount_even_when_capped() -> None:
    caster_stats = _char_stats(max_hp=9999)
    target_stats = _char_stats(max_hp=1800)
    enemy_stats = _enemy_stats()
    caster_state = BattleActorState(hp=1500, max_hp=9999)
    caster_state.mp_pool[1] = 1
    caster_state.max_mp_pool[1] = 1
    target_state = BattleActorState(hp=1790, max_hp=1800)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    cure = SpellInfo(power=32, accuracy_percent=100, magic_type="white", elements=[])
    spell_json = {
        "Name": "Cure",
        "Type": "White Magic",
        "Level": 1,
        "Target": "One/All Allies",
        "Effect": "Restore target's HP",
    }
    party = [
        SimpleNamespace(name="Refia", stats=caster_stats, state=caster_state),
        SimpleNamespace(name="Ingus", stats=target_stats, state=target_state),
    ]
    expected_heal = magic_heal_amount_to_char(
        caster=caster_stats,
        spell=cure,
        rng=Random(0),
        use_expectation=False,
        blind=False,
        target_count=1,
        spell_name="Cure",
        spell_json=spell_json,
    )
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
        char_spell=cure,
        char_spell_json=spell_json,
        char_spell_healing_type="hp",
        char_spell_name="Cure",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="ally",
        target_index=1,
        party_members=party,
        aoe_selected_override=False,
    )

    assert damage == 0
    assert result is None
    assert target_state.hp == target_stats.max_hp
    assert any(f"HPが{expected_heal}回復。" in line for line in logs)


def test_multi_target_heal_log_displays_spell_amount_even_when_capped() -> None:
    caster_stats = _char_stats(max_hp=9999)
    ally1_stats = _char_stats(max_hp=1800)
    ally2_stats = _char_stats(max_hp=1900)
    enemy_stats = _enemy_stats()
    caster_state = BattleActorState(hp=1500, max_hp=9999)
    caster_state.mp_pool[7] = 1
    caster_state.max_mp_pool[7] = 1
    ally1_state = BattleActorState(hp=1790, max_hp=1800)
    ally2_state = BattleActorState(hp=1890, max_hp=1900)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    curaja = SpellInfo(power=80, accuracy_percent=100, magic_type="white", elements=[])
    spell_json = {
        "Name": "Curaja",
        "Type": "White Magic",
        "Level": 7,
        "Target": "One/All Allies",
        "Effect": "Restore target's HP",
        "field_heal_hp": 9999,
        "target_scope": "one_or_all",
        "default_target_side": "Any",
    }
    party = [
        SimpleNamespace(name="Refia", stats=caster_stats, state=caster_state),
        SimpleNamespace(name="Ingus", stats=ally1_stats, state=ally1_state),
        SimpleNamespace(name="Arc", stats=ally2_stats, state=ally2_state),
    ]
    total_targets = len(party)
    expected_heal = magic_heal_amount_to_char(
        caster=caster_stats,
        spell=curaja,
        rng=Random(0),
        use_expectation=False,
        blind=False,
        target_count=total_targets,
        spell_name="Curaja",
        spell_json=spell_json,
    )
    per_target_heal = int(max(0, expected_heal) / total_targets)
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
        char_spell=curaja,
        char_spell_json=spell_json,
        char_spell_healing_type="hp",
        char_spell_name="Curaja",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="ally",
        target_index=1,
        party_members=party,
        aoe_selected_override=True,
    )

    assert damage == 0
    assert result is None
    assert ally1_state.hp == ally1_stats.max_hp
    assert ally2_state.hp == ally2_stats.max_hp
    assert any(
        f"合計HPが{per_target_heal * total_targets}回復（Refia:{per_target_heal}, Ingus:{per_target_heal}, Arc:{per_target_heal}）。"
        in line
        for line in logs
    )


def test_raise_uses_field_revive_hp_metadata_for_partial_revive() -> None:
    caster_stats = _char_stats(max_hp=9999)
    target_stats = _char_stats(max_hp=1800)
    enemy_stats = _enemy_stats()
    caster_state = BattleActorState(hp=1500, max_hp=9999)
    caster_state.mp_pool[5] = 1
    caster_state.max_mp_pool[5] = 1
    target_state = BattleActorState(hp=0, max_hp=1800)
    target_state.statuses.add(Status.KO)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    raise_spell = SpellInfo(power=1, accuracy_percent=15, magic_type="white", elements=[])
    spell_json = {
        "Name": "Raise",
        "Type": "White Magic",
        "Level": 5,
        "Effect": "stale legacy text",
        "effect_category": "revive",
        "field_revive_hp": "half",
        "status_ailment": "KO",
        "target_scope": "one",
        "default_target_side": "Ally",
    }
    party = [
        SimpleNamespace(name="Refia", stats=caster_stats, state=caster_state),
        SimpleNamespace(name="Ingus", stats=target_stats, state=target_state),
    ]
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
        char_spell=raise_spell,
        char_spell_json=spell_json,
        char_spell_healing_type="revive",
        char_spell_name="Raise",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="ally",
        target_index=1,
        party_members=party,
    )

    assert damage == 0
    assert result is None
    assert target_state.hp == 360
    assert Status.KO not in target_state.statuses


def test_arise_uses_field_revive_hp_metadata_for_full_revive() -> None:
    caster_stats = _char_stats(max_hp=9999)
    target_stats = _char_stats(max_hp=1800)
    enemy_stats = _enemy_stats()
    caster_state = BattleActorState(hp=1500, max_hp=9999)
    caster_state.mp_pool[8] = 1
    caster_state.max_mp_pool[8] = 1
    target_state = BattleActorState(hp=0, max_hp=1800)
    target_state.statuses.add(Status.KO)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    arise_spell = SpellInfo(power=255, accuracy_percent=100, magic_type="white", elements=[])
    spell_json = {
        "Name": "Arise",
        "Type": "White Magic",
        "Level": 8,
        "Effect": "stale legacy text",
        "effect_category": "revive",
        "field_revive_hp": "full",
        "status_ailment": "KO",
        "target_scope": "one",
        "default_target_side": "Ally",
    }
    party = [
        SimpleNamespace(name="Refia", stats=caster_stats, state=caster_state),
        SimpleNamespace(name="Ingus", stats=target_stats, state=target_state),
    ]
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
        char_spell=arise_spell,
        char_spell_json=spell_json,
        char_spell_healing_type="revive",
        char_spell_name="Arise",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="ally",
        target_index=1,
        party_members=party,
    )

    assert damage == 0
    assert result is None
    assert target_state.hp == target_stats.max_hp
    assert Status.KO not in target_state.statuses
