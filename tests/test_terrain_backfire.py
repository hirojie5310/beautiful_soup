# tests/test_terrain_backfire.py
from random import Random
from types import SimpleNamespace

from combat.enums import Status
from combat.models import (
    BattleActorState,
    EnemyRuntime,
    FinalCharacterStats,
    FinalEnemyStats,
)
from combat.turn_logic import run_character_turn


def _make_char_stats() -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=1,
        job_skill_point=0,
        max_hp=200,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=16,
        mind=10,
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


def _make_enemy_stats(
    *, magic_def_multiplier: int = 1, magic_resistance_percent: int = 0
) -> FinalEnemyStats:
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
        magic_def_multiplier=magic_def_multiplier,
        magic_resistance_percent=magic_resistance_percent,
        agility=1,
    )


def test_terrain_backfires_when_all_targets_are_ineffective():
    char_stats = _make_char_stats()
    enemy_stats = _make_enemy_stats(
        magic_def_multiplier=8, magic_resistance_percent=100
    )
    char_state = BattleActorState(hp=180, max_hp=200)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    enemy_json = {"Level": 1}
    spells_by_name = {
        "Cave In": {
            "name": "Cave In",
            "BasePower": 20,
            "BaseAccuracy": 0.3,
            "Target": "One Enemy",
            "Effect": "Deal damage",
        }
    }
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Desch",
        enemy_name="Ifrit",
        char_stats=char_stats,
        enemy_stats=enemy_stats,
        enemy_json=enemy_json,
        char_state=char_state,
        enemy_state=enemy_state,
        char_attack_kind="special",
        char_battle_command="Terrain",
        char_weapon_hand="main",
        char_spell=None,
        char_spell_json=None,
        char_spell_healing_type=None,
        char_spell_name=None,
        char_item=None,
        logs=logs,
        rng=Random(0),
        save={"map": {"surface": "Other"}},
        spells_by_name=spells_by_name,
    )

    assert damage == 0
    assert result is None
    assert char_state.hp == 130
    assert enemy_state.hp == 500
    assert "Backfired!" in logs
    assert any("バックファイア！" in line for line in logs)


def test_terrain_does_not_backfire_when_at_least_one_target_is_hit():
    char_stats = _make_char_stats()
    sturdy_enemy_stats = _make_enemy_stats(
        magic_def_multiplier=8, magic_resistance_percent=100
    )
    soft_enemy_stats = _make_enemy_stats(
        magic_def_multiplier=0, magic_resistance_percent=0
    )
    char_state = BattleActorState(hp=180, max_hp=200)
    primary_enemy_state = BattleActorState(hp=500, max_hp=500)
    ally_enemy_state = BattleActorState(hp=500, max_hp=500)
    primary_enemy_json = {"Level": 1}
    ally_enemy_json = {"Level": 1}
    spells_by_name = {
        "Wind Slash": {
            "name": "Wind Slash",
            "BasePower": 20,
            "BaseAccuracy": 0.3,
            "Target": "All Enemies",
            "Effect": "Deal damage",
        }
    }
    enemies = [
        EnemyRuntime(
            name="Adamantoise",
            stats=sturdy_enemy_stats,
            state=primary_enemy_state,
            json=primary_enemy_json,
        ),
        EnemyRuntime(
            name="Bomb",
            stats=soft_enemy_stats,
            state=ally_enemy_state,
            json=ally_enemy_json,
        ),
    ]
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Desch",
        enemy_name="Adamantoise",
        char_stats=char_stats,
        enemy_stats=sturdy_enemy_stats,
        enemy_json=primary_enemy_json,
        char_state=char_state,
        enemy_state=primary_enemy_state,
        char_attack_kind="special",
        char_battle_command="Terrain",
        char_weapon_hand="main",
        char_spell=None,
        char_spell_json=None,
        char_spell_healing_type=None,
        char_spell_name=None,
        char_item=None,
        logs=logs,
        rng=Random(0),
        save={"map": {"surface": "Forest"}},
        spells_by_name=spells_by_name,
        enemies=enemies,
    )

    assert damage > 0
    assert result is None
    assert char_state.hp == 180
    assert primary_enemy_state.hp == 500
    assert ally_enemy_state.hp < 500
    assert "Backfired!" not in logs
    assert any("Adamantoiseには効かなかった。" in line for line in logs)
    assert not any(status is Status.KO for status in char_state.statuses)
