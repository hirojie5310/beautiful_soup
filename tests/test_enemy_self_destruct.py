from pathlib import Path
from random import Random
from types import SimpleNamespace
from typing import Any, cast

from combat.battle_sim import simulate_one_round_multi_party
from combat.models import (
    BattleActorState,
    EnemyRuntime,
    FinalCharacterStats,
    FinalEnemyStats,
    PartyMemberRuntime,
    PlannedAction,
)
from combat.runtime_state import RuntimeState
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


def _enemy_stats(name: str = "Bomb", hp: int = 120) -> FinalEnemyStats:
    return FinalEnemyStats(
        name=name,
        hp=hp,
        level=10,
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


def _state() -> RuntimeState:
    return RuntimeState(
        monsters={},
        weapons={},
        armors={},
        spells={},
        items_by_name={},
        jobs_by_name={},
        save={},
        base_dir=Path("."),
    )


def test_enemy_self_destruct_deals_four_times_current_hp_and_kos_user() -> None:
    char_stats = _char_stats()
    enemy_stats = _enemy_stats(hp=120)
    char_state = BattleActorState(hp=999, max_hp=999)
    enemy_state = BattleActorState(hp=120, max_hp=120)
    logs: list[str] = []
    spell = {
        "Name": "Self-Destruct",
        "Power": 3,
        "Multiplier": 1,
        "Accuracy": 1.0,
        "Target": "One Enemy",
    }

    result = run_enemy_turn(
        char_name="Refia",
        enemy_name="Bomb",
        char_stats=char_stats,
        enemy_stats=enemy_stats,
        enemy_json={
            "SpecialAttackRate": 1.0,
            "Special Attacks": [{"Attack": "Self-Destruct", "Rate": 1.0}],
            "Spells": [spell],
        },
        char_state=char_state,
        enemy_state=enemy_state,
        char_attack_kind="physical",
        dmg_to_enemy=0,
        char_conf=False,
        char_is_mini_or_toad=False,
        logs=logs,
        state=_state(),
        rng=Random(0),
        party_members=[
            PartyMemberRuntime(
                name="Refia",
                level=char_stats.level,
                job=cast(Any, None),
                base=cast(Any, None),
                stats=char_stats,
                state=char_state,
            )
        ],
    )

    assert result.enemy_attack_result is not None
    assert result.enemy_attack_result.attack_name == "Self-Destruct"
    assert result.enemy_attack_result.damage == 480
    assert char_state.hp == 519
    assert enemy_state.hp == 0
    assert any("Bombの《Self-Destruct》！" in line for line in logs)


def test_enemy_self_destruct_only_kos_user_in_multi_enemy_battle() -> None:
    state = _state()
    char_stats = _char_stats()
    member = PartyMemberRuntime(
        name="Refia",
        level=char_stats.level,
        job=cast(Any, SimpleNamespace(name="Warrior", raw={})),
        base=cast(Any, SimpleNamespace(job_level=1, job_skill_point=0)),
        stats=char_stats,
        state=BattleActorState(hp=999, max_hp=999),
    )
    bomb_spell = {
        "Name": "Self-Destruct",
        "Power": 3,
        "Multiplier": 1,
        "Accuracy": 1.0,
        "Target": "One Enemy",
    }
    enemies = [
        EnemyRuntime(
            name="Bomb",
            stats=_enemy_stats(name="Bomb", hp=100),
            state=BattleActorState(hp=100, max_hp=100),
            json={
                "SpecialAttackRate": 1.0,
                "Special Attacks": [{"Attack": "Self-Destruct", "Rate": 1.0}],
                "Spells": [bomb_spell],
            },
        ),
        EnemyRuntime(
            name="Goblin",
            stats=_enemy_stats(name="Goblin", hp=50),
            state=BattleActorState(hp=50, max_hp=50),
            json={"SpecialAttackRate": 0.0, "Special Attacks": [], "Spells": []},
        ),
    ]

    logs, result, _ = simulate_one_round_multi_party(
        party_members=[member],
        enemies=enemies,
        planned_actions=[PlannedAction(kind="defend", command="Defend", target_side="self")],
        state=state,
        rng=Random(0),
        save=state.save,
        spells_by_name=state.spells,
        items_by_name=state.items_by_name,
    )

    assert result.end_reason == "continue"
    assert enemies[0].state.hp == 0
    assert enemies[1].state.hp > 0
    assert any("Bombの《Self-Destruct》！" in line for line in logs)
