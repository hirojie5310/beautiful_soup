# tests/test_turn_start_priority_actions.py
from random import Random

from combat.battle_sim import simulate_one_round_multi_party
from combat.enums import Status
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


def _make_char_stats(*, agility: int = 1, max_hp: int = 160) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=10,
        job_level=1,
        job_skill_point=0,
        max_hp=max_hp,
        strength=12,
        agility=agility,
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


def _make_enemy_stats(*, agility: int = 40) -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Goblin",
        hp=120,
        level=5,
        job_level=1,
        attack_power=22,
        attack_multiplier=1,
        accuracy_percent=95,
        defense=4,
        defense_multiplier=1,
        evasion_percent=0,
        magic_defense=1,
        magic_def_multiplier=1,
        magic_resistance_percent=0,
        agility=agility,
    )


def _make_member(*, name: str = "Refia", agility: int = 1) -> PartyMemberRuntime:
    stats = _make_char_stats(agility=agility)
    base = BaseCharacter(
        level=10,
        total_exp=0,
        job_level=1,
        job_skill_point=0,
        max_hp=stats.max_hp,
        strength=12,
        agility=agility,
        vitality=10,
        intelligence=8,
        mind=8,
    )
    job = Job(name="Warrior", slug="warrior", earned="start", stats_by_level={}, raw={})
    state = BattleActorState(hp=stats.max_hp, max_hp=stats.max_hp)
    state.statuses.add(Status.POISON)
    return PartyMemberRuntime(
        name=name,
        level=10,
        job=job,
        base=base,
        stats=stats,
        state=state,
    )


def _make_enemy() -> EnemyRuntime:
    stats = _make_enemy_stats()
    state = BattleActorState(hp=stats.hp, max_hp=stats.hp)
    return EnemyRuntime(
        name="Goblin",
        stats=stats,
        state=state,
        json={"Level": 5, "SpecialAttackRate": 0},
    )


def _make_runtime_state(*, member_name: str) -> RuntimeState:
    return RuntimeState(
        monsters={},
        weapons={},
        armors={},
        spells={},
        items_by_name={},
        jobs_by_name={},
        save={"party": [{"name": member_name}]},
    )


def test_defend_executes_after_poison_and_before_initiative_actions():
    member = _make_member(name="Ingus", agility=1)
    enemy = _make_enemy()

    logs, side_result, _events = simulate_one_round_multi_party(
        party_members=[member],
        enemies=[enemy],
        planned_actions=[
            PlannedAction(kind="defend", command="Defend", target_side="self")
        ],
        state=_make_runtime_state(member_name=member.name),
        rng=Random(0),
    )

    poison_idx = next(i for i, line in enumerate(logs) if "毒のダメージ" in line)
    defend_idx = next(i for i, line in enumerate(logs) if "防御した" in line)
    enemy_turn_idx = next(i for i, line in enumerate(logs) if "◆ Goblin の行動" in line)

    assert side_result.end_reason == "continue"
    assert poison_idx < defend_idx < enemy_turn_idx
    assert any("防御してダメージを軽減" in line for line in logs)


def test_flee_executes_after_poison_and_before_enemy_action():
    member = _make_member(name="Edge", agility=1)
    enemy = _make_enemy()

    logs, side_result, _events = simulate_one_round_multi_party(
        party_members=[member],
        enemies=[enemy],
        planned_actions=[PlannedAction(kind="run", command="Flee", target_side="self")],
        state=_make_runtime_state(member_name=member.name),
        rng=Random(0),
    )

    poison_idx = next(i for i, line in enumerate(logs) if "毒のダメージ" in line)
    flee_idx = next(
        i for i, line in enumerate(logs) if "《Flee》で戦闘から逃げ出した" in line
    )

    assert poison_idx < flee_idx
    assert side_result.end_reason == "escaped"
    assert side_result.escaped is True
    assert not any("◆ Goblin の行動" in line for line in logs)


def test_multiple_defends_resolve_before_normal_action_order():
    runeth = _make_member(name="Runeth", agility=30)
    arc = _make_member(name="Arc", agility=1)
    refia = _make_member(name="Refia", agility=1)
    enemy = _make_enemy()

    arc.state.statuses.discard(Status.POISON)
    refia.state.statuses.discard(Status.POISON)

    logs, side_result, _events = simulate_one_round_multi_party(
        party_members=[runeth, arc, refia],
        enemies=[enemy],
        planned_actions=[
            PlannedAction(
                kind="physical", command="Fight", target_side="enemy", target_index=0
            ),
            PlannedAction(kind="defend", command="Defend", target_side="self"),
            PlannedAction(kind="defend", command="Defend", target_side="self"),
        ],
        state=_make_runtime_state(member_name=runeth.name),
        rng=Random(0),
    )

    poison_idx = next(i for i, line in enumerate(logs) if "毒のダメージ" in line)
    arc_defend_idx = next(
        i for i, line in enumerate(logs) if "▶ Arc の行動（Defend）" in line
    )
    refia_defend_idx = next(
        i for i, line in enumerate(logs) if "▶ Refia の行動（Defend）" in line
    )
    runeth_action_idx = next(
        i for i, line in enumerate(logs) if "▶ Runeth の行動（Fight）" in line
    )

    assert side_result.end_reason == "continue"
    assert poison_idx < arc_defend_idx < refia_defend_idx < runeth_action_idx
