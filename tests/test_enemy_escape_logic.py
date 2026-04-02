from pathlib import Path
from random import Random
from typing import Any, cast

from combat.models import (
    BattleActorState,
    FinalCharacterStats,
    FinalEnemyStats,
    PartyMemberRuntime,
)
from combat.runtime_state import RuntimeState
from combat.turn_logic import run_enemy_turn


def _char_stats(level: int = 40) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=level,
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


def _enemy_stats(name: str = "Hein", level: int = 13) -> FinalEnemyStats:
    return FinalEnemyStats(
        name=name,
        hp=1600,
        level=level,
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


def test_plot_battle_enemy_does_not_escape_even_with_large_level_gap() -> None:
    char_stats = _char_stats(level=45)
    enemy_stats = _enemy_stats(level=13)
    char_state = BattleActorState(hp=999, max_hp=999)
    enemy_state = BattleActorState(hp=1600, max_hp=1600)
    logs: list[str] = []

    result = run_enemy_turn(
        char_name="Refia",
        enemy_name="Hein",
        char_stats=char_stats,
        enemy_stats=enemy_stats,
        enemy_json={
            "PlotBattles": [{"Map": "Hein's Castle 5F"}],
            "SpecialAttackRate": 0.0,
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

    assert result.end_reason == "continue"
    assert enemy_state.hp > 0
    assert not any("逃げ出そうとしている" in line for line in logs)
    assert not any("逃げ出した" in line for line in logs)
