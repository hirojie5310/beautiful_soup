# combat/usecases.py
# UI非依存のユースケース境界
# Flask など別UIから同じ戦闘オーケストレーションを再利用できるように
from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Any, Optional, Sequence, cast

from combat.battle_sim import simulate_one_round_multi_party
from combat.char_build import build_party_members_from_save
from combat.dto import (
    ExecuteRoundInputDTO,
    ExecuteRoundOutputDTO,
    derive_round_lifecycle,
    to_domain_planned_action,
)
from combat.enemy_build import build_enemies
from combat.magic_menu import (
    build_party_magic_info,
    build_party_magic_lists,
    expand_spells_for_summons,
)
from combat.models import (
    BattleEvent,
    EnemyRuntime,
    PartyMemberRuntime,
    PlannedAction,
    SideTurnResult,
)
from combat.runtime_state import RuntimeState
from system.exp_system import LevelTable


@dataclass
class BattleSession:
    state: RuntimeState
    level_table: LevelTable
    party_members: list[PartyMemberRuntime]
    enemies: list[EnemyRuntime]
    party_magic_info: Any
    party_magic_lists: Any
    spells_expanded: dict[str, dict[str, Any]]


@dataclass
class RoundExecutionResult:
    logs: list[str]
    round_result: SideTurnResult
    event: list[BattleEvent]


def build_battle_session(
    *,
    state: RuntimeState,
    enemy_names: Sequence[str],
    level_exp_csv_path: str = "assets/data/level_exp.csv",
) -> BattleSession:
    """UIに依存しない戦闘セッションの初期化ユースケース。"""

    level_table = LevelTable(level_exp_csv_path)

    party_magic_info = build_party_magic_info(state)
    party_magic_lists = build_party_magic_lists(state)
    spells_expanded = expand_spells_for_summons(state.spells)

    party_members = build_party_members_from_save(
        save=state.save,
        weapons=state.weapons,
        armors=state.armors,
        jobs_by_name=state.jobs_by_name,
        level_table=level_table,
    )

    enemies = build_enemies(
        enemy_defs_by_name=state.monsters,
        spells_by_name=state.spells,
        enemy_names=list(enemy_names),
    )

    return BattleSession(
        state=state,
        level_table=level_table,
        party_members=party_members,
        enemies=enemies,
        party_magic_info=party_magic_info,
        party_magic_lists=party_magic_lists,
        spells_expanded=spells_expanded,
    )


def execute_round(
    *,
    session: BattleSession,
    planned_actions: Sequence[Optional[PlannedAction]],
    rng: Random,
) -> RoundExecutionResult:
    """UI入力済み行動を受けて1ラウンドを実行するユースケース。"""

    logs, round_result, event = simulate_one_round_multi_party(
        session.party_members,
        session.enemies,
        list(planned_actions),
        rng=rng,
        save=session.state.save,
        spells_by_name=session.spells_expanded,
        items_by_name=session.state.items_by_name,
        state=session.state,
    )
    typed_events = cast(list[BattleEvent], event)
    return RoundExecutionResult(
        logs=logs,
        round_result=round_result,
        event=typed_events,
    )


def execute_round_dto(
    *,
    session: BattleSession,
    request: ExecuteRoundInputDTO,
    rng: Random,
) -> ExecuteRoundOutputDTO:
    """DTOベースの1ラウンド実行ユースケース（Flask向けの入出力境界）。"""

    if request.lifecycle_state != "ready_for_actions":
        raise ValueError(
            "execute_round_dto accepts lifecycle_state='ready_for_actions' only. "
            f"actual={request.lifecycle_state!r}"
        )

    planned_actions = [
        to_domain_planned_action(a) if a is not None else None
        for a in request.planned_actions
    ]
    result = execute_round(
        session=session,
        planned_actions=planned_actions,
        rng=rng,
    )

    return ExecuteRoundOutputDTO(
        logs=result.logs,
        end_reason=result.round_result.end_reason,
        escaped=result.round_result.escaped,
        enemy_was_physically_hit=result.round_result.enemy_was_physically_hit,
        events=result.event,
        lifecycle=derive_round_lifecycle(
            current_state=request.lifecycle_state,
            end_reason=result.round_result.end_reason,
        ),
    )
