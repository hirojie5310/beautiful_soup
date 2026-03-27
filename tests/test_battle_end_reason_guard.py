# tests/test_battle_end_reason_guard.py
from pathlib import Path
from random import Random

from combat.battle_sim import simulate_one_round_multi_party
from combat.models import (
    BaseCharacter,
    BattleActorState,
    EnemyRuntime,
    FinalCharacterStats,
    FinalEnemyStats,
    Job,
    OneTurnResult,
    PartyMemberRuntime,
    PlannedAction,
)
from combat.runtime_state import RuntimeState


def _make_member() -> PartyMemberRuntime:
    stats = FinalCharacterStats(
        level=10,
        job_level=1,
        job_skill_point=0,
        max_hp=999,
        strength=12,
        agility=30,
        vitality=10,
        intelligence=8,
        mind=8,
        row="front",
        main_power=10,
        main_accuracy=80,
        main_atk_multiplier=1,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=1,
        off_two=False,
        off_long=False,
        defense=10,
        defense_multiplier=1,
        evasion_percent=0,
        magic_defense=5,
        magic_def_multiplier=1,
        magic_resistance=0,
        shield_count=0,
    )
    base = BaseCharacter(
        level=10,
        total_exp=0,
        job_level=1,
        job_skill_point=0,
        max_hp=stats.max_hp,
        strength=12,
        agility=30,
        vitality=10,
        intelligence=8,
        mind=8,
    )
    job = Job(name="Warrior", slug="warrior", earned="start", stats_by_level={}, raw={})
    return PartyMemberRuntime(
        name="Runeth",
        level=10,
        job=job,
        base=base,
        stats=stats,
        state=BattleActorState(hp=stats.max_hp, max_hp=stats.max_hp),
    )


def _make_enemy(name: str, hp: int) -> EnemyRuntime:
    stats = FinalEnemyStats(
        name=name,
        hp=hp,
        level=5,
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
    return EnemyRuntime(
        name=name,
        display_name=name,
        stats=stats,
        state=BattleActorState(hp=hp, max_hp=hp),
        json={"Level": 1, "SpecialAttackRate": 0},
    )


def _runtime_state() -> RuntimeState:
    return RuntimeState(
        monsters={},
        weapons={},
        armors={},
        spells={},
        items_by_name={},
        jobs_by_name={},
        save={"party": [{"name": "Runeth"}]},
        base_dir=Path("."),
    )


def test_simulate_round_ignores_false_enemy_defeated_from_character_turn(monkeypatch):
    member = _make_member()
    enemies = [_make_enemy("Skeleton A", 0), _make_enemy("Shadow A", 65)]

    def _fake_run_character_turn(**kwargs):
        return 0, OneTurnResult(
            char_state=kwargs["char_state"],
            enemy_state=kwargs["enemy_state"],
            logs=kwargs["logs"],
            enemy_attack_result=None,
            end_reason="enemy_defeated",
        )

    monkeypatch.setattr(
        "combat.battle_sim.run_character_turn", _fake_run_character_turn
    )

    _, side_result, _ = simulate_one_round_multi_party(
        party_members=[member],
        enemies=enemies,
        planned_actions=[
            PlannedAction(
                kind="magic",
                command="Magic",
                target_side="enemy",
                target_index=0,
                spell_name="Cure",
            )
        ],
        state=_runtime_state(),
        rng=Random(0),
    )

    assert side_result.end_reason == "continue"
