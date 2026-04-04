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
    PartyMemberRuntime,
    PlannedAction,
)
from combat.runtime_state import RuntimeState


def _make_char_stats(*, agility: int, power: int) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=10,
        job_level=1,
        job_skill_point=0,
        max_hp=120,
        strength=18,
        agility=agility,
        vitality=10,
        intelligence=8,
        mind=8,
        row="front",
        main_power=power,
        main_accuracy=100,
        main_atk_multiplier=4,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=0,
        off_two=False,
        off_long=False,
        defense=10,
        defense_multiplier=1,
        evasion_percent=0,
        magic_defense=1,
        magic_def_multiplier=1,
        magic_resistance=0,
        shield_count=0,
    )


def _make_member(*, name: str, agility: int, power: int) -> PartyMemberRuntime:
    stats = _make_char_stats(agility=agility, power=power)
    base = BaseCharacter(
        level=10,
        total_exp=0,
        job_level=1,
        job_skill_point=0,
        max_hp=stats.max_hp,
        strength=stats.strength,
        agility=stats.agility,
        vitality=stats.vitality,
        intelligence=stats.intelligence,
        mind=stats.mind,
    )
    job = Job(name="Warrior", slug="warrior", earned="start", stats_by_level={}, raw={})
    state = BattleActorState(hp=stats.max_hp, max_hp=stats.max_hp)
    return PartyMemberRuntime(
        name=name,
        level=10,
        job=job,
        base=base,
        stats=stats,
        state=state,
    )


def _make_enemy(*, hp: int) -> EnemyRuntime:
    stats = FinalEnemyStats(
        name="Goblin",
        hp=hp,
        level=1,
        job_level=1,
        attack_power=1,
        attack_multiplier=1,
        accuracy_percent=1,
        defense=0,
        defense_multiplier=0,
        evasion_percent=0,
        magic_defense=0,
        magic_def_multiplier=0,
        magic_resistance_percent=0,
        agility=1,
    )
    state = BattleActorState(hp=hp, max_hp=hp)
    return EnemyRuntime(
        name="Goblin",
        stats=stats,
        state=state,
        json={"Level": 1, "SpecialAttackRate": 0},
    )


def _make_runtime_state(*, party_names: list[str]) -> RuntimeState:
    return RuntimeState(
        monsters={},
        weapons={},
        armors={},
        spells={},
        items_by_name={},
        jobs_by_name={},
        save={"party": [{"name": name} for name in party_names]},
        base_dir=Path("."),
    )


def test_logs_skipped_party_actions_when_battle_ends_mid_round() -> None:
    fast_attacker = _make_member(name="Refia", agility=40, power=300)
    slow_attacker = _make_member(name="Arc", agility=1, power=10)
    enemy = _make_enemy(hp=1)

    logs, side_result, _events = simulate_one_round_multi_party(
        party_members=[fast_attacker, slow_attacker],
        enemies=[enemy],
        planned_actions=[
            PlannedAction(
                kind="physical", command="Fight", target_side="enemy", target_index=0
            ),
            PlannedAction(
                kind="physical", command="Fight", target_side="enemy", target_index=0
            ),
        ],
        state=_make_runtime_state(party_names=[fast_attacker.name, slow_attacker.name]),
        rng=Random(0),
    )

    assert side_result.end_reason == "enemy_defeated"
    assert any("▶ Refia の行動（Fight）" in line for line in logs)
    assert any("▶ Arc の行動（Fight）" in line for line in logs)
    assert any("Arcは敵が全滅していたため行動できなかった。" in line for line in logs)
