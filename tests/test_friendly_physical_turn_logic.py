# tests/test_friendly_physical_turn_logic.py
from random import Random
from types import SimpleNamespace

from combat.models import BattleActorState, FinalCharacterStats, FinalEnemyStats
from combat.turn_logic import run_character_turn


def test_turn_logic_module_imports_cleanly() -> None:
    from combat.turn_logic import run_character_turn as imported

    assert imported is run_character_turn


def _char_stats(
    *, row: str = "front", main_power: int = 20, defense: int = 50
) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=999,
        strength=20,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=10,
        row=row,
        main_power=main_power,
        main_accuracy=100,
        main_atk_multiplier=2,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=1,
        off_two=False,
        off_long=False,
        defense=defense,
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


def test_physical_attack_to_ally_does_not_use_target_defense() -> None:
    attacker_stats = _char_stats(main_power=20, defense=0)
    ally_stats = _char_stats(main_power=5, defense=80)
    enemy_stats = _enemy_stats()
    attacker_state = BattleActorState(hp=999, max_hp=999)
    ally_state = BattleActorState(hp=120, max_hp=999)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    party = [
        SimpleNamespace(name="Refia", stats=attacker_stats, state=attacker_state),
        SimpleNamespace(name="Ingus", stats=ally_stats, state=ally_state),
    ]
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Refia",
        enemy_name="Goblin",
        char_stats=attacker_stats,
        enemy_stats=enemy_stats,
        enemy_json={},
        char_state=attacker_state,
        enemy_state=enemy_state,
        char_attack_kind="physical",
        char_battle_command="Fight",
        char_weapon_hand="main",
        char_spell=None,
        char_spell_json=None,
        char_spell_healing_type=None,
        char_spell_name=None,
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="ally",
        target_index=1,
        party_members=party,
    )

    assert damage == 0
    assert result is None
    assert ally_state.hp == 72
    assert enemy_state.hp == 500
    assert any("Ingus" in line for line in logs)
