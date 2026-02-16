# combat/dto.py
# ラウンド実行の入出力スキーマとして
# PlannedActionDTO / ExecuteRoundInputDTO / ExecuteRoundOutputDTO を定義
# これで「アダプタ（Flask等）⇔ユースケース」間の契約を先に固定
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, cast

from combat.enums import BattleKind
from combat.errors import InputValidationError, InvalidLifecycleError
from combat.models import BattleEvent, PlannedAction, TargetSide


# ユースケース境界で使う戦闘状態ライフサイクル。
# 契約テストで「どの状態からどの状態へ遷移できるか」を固定しやすくする。
BattleLifecycleState = str
LIFECYCLE_READY = "ready_for_actions"
LIFECYCLE_RESOLVING = "resolving_round"
LIFECYCLE_READY_NEXT_ROUND = "ready_for_next_round"
LIFECYCLE_FINISHED = "battle_finished"

ALLOWED_LIFECYCLE_TRANSITIONS: dict[BattleLifecycleState, set[BattleLifecycleState]] = {
    LIFECYCLE_READY: {LIFECYCLE_RESOLVING},
    LIFECYCLE_RESOLVING: {LIFECYCLE_READY_NEXT_ROUND, LIFECYCLE_FINISHED},
    LIFECYCLE_READY_NEXT_ROUND: {LIFECYCLE_READY},
    LIFECYCLE_FINISHED: {LIFECYCLE_FINISHED},
}


@dataclass
class PlannedActionDTO:
    kind: BattleKind
    command: Optional[str] = None
    spell_name: Optional[str] = None
    item_name: Optional[str] = None
    target_side: TargetSide = "enemy"
    target_index: Optional[int] = None
    target_all: bool = False


@dataclass
class ExecuteRoundInputDTO:
    planned_actions: list[Optional[PlannedActionDTO]]
    lifecycle_state: BattleLifecycleState = LIFECYCLE_READY


@dataclass
class BattleLifecycleDTO:
    before: BattleLifecycleState
    after: BattleLifecycleState
    battle_finished: bool


@dataclass
class ExecuteRoundOutputDTO:
    logs: list[str]
    end_reason: str
    escaped: bool
    enemy_was_physically_hit: bool
    events: list[BattleEvent]
    lifecycle: BattleLifecycleDTO


def validate_lifecycle_transition(
    *,
    before: BattleLifecycleState,
    after: BattleLifecycleState,
) -> None:
    allowed = ALLOWED_LIFECYCLE_TRANSITIONS.get(before, set())
    if after not in allowed:
        raise InvalidLifecycleError(
            f"Invalid lifecycle transition: {before!r} -> {after!r}.",
            details={"before": before, "after": after},
        )


def derive_round_lifecycle(
    *,
    current_state: BattleLifecycleState,
    end_reason: str,
) -> BattleLifecycleDTO:
    if current_state != LIFECYCLE_READY:
        raise InvalidLifecycleError(
            "execute_round_dto must start from 'ready_for_actions'. "
            f"actual={current_state!r}",
            details={"current_state": current_state},
        )

    before = LIFECYCLE_RESOLVING
    after = (
        LIFECYCLE_READY_NEXT_ROUND if end_reason == "continue" else LIFECYCLE_FINISHED
    )
    validate_lifecycle_transition(before=before, after=after)

    return BattleLifecycleDTO(
        before=before,
        after=after,
        battle_finished=after == LIFECYCLE_FINISHED,
    )


# DTOとドメインモデルの変換関数
def to_domain_planned_action(dto: PlannedActionDTO) -> PlannedAction:
    return PlannedAction(
        kind=dto.kind,
        command=dto.command,
        spell_name=dto.spell_name,
        item_name=dto.item_name,
        target_side=dto.target_side,
        target_index=dto.target_index,
        target_all=dto.target_all,
    )


# DTOとドメインモデルの変換関数
def to_dto_planned_action(action: PlannedAction) -> PlannedActionDTO:
    return PlannedActionDTO(
        kind=action.kind,
        command=action.command,
        spell_name=action.spell_name,
        item_name=action.item_name,
        target_side=action.target_side,
        target_index=action.target_index,
        target_all=action.target_all,
    )


# HTTPレスポンス化しやすい
def to_json_ready_dict(dto: ExecuteRoundOutputDTO) -> dict[str, Any]:
    """Flaskレスポンス化しやすい dict へ変換する。"""
    return {
        "logs": dto.logs,
        "end_reason": dto.end_reason,
        "escaped": dto.escaped,
        "enemy_was_physically_hit": dto.enemy_was_physically_hit,
        "events": dto.events,
        "lifecycle": {
            "before": dto.lifecycle.before,
            "after": dto.lifecycle.after,
            "battle_finished": dto.lifecycle.battle_finished,
        },
    }


ALLOWED_BATTLE_KINDS: set[str] = {
    "physical",
    "magic",
    "item",
    "defend",
    "jump",
    "run",
    "special",
}


class DTOValidationError(InputValidationError):
    """Adapter payload validation error for DTO boundary."""


def _validate_planned_action_dto(payload: Any, *, idx: int) -> PlannedActionDTO:
    if not isinstance(payload, dict):
        raise DTOValidationError(
            f"planned_actions[{idx}] must be object or null. actual={type(payload).__name__}"
        )

    kind_raw = payload.get("kind")
    if not isinstance(kind_raw, str):
        raise DTOValidationError(
            f"planned_actions[{idx}].kind must be string. actual={type(kind_raw).__name__}"
        )
    if kind_raw not in ALLOWED_BATTLE_KINDS:
        raise DTOValidationError(
            f"planned_actions[{idx}].kind is unsupported. actual={kind_raw!r}"
        )
    kind = cast(BattleKind, kind_raw)

    target_side_raw = payload.get("target_side", "enemy")
    if target_side_raw not in {"enemy", "ally", "self"}:
        raise DTOValidationError(
            "planned_actions[{}].target_side must be one of 'enemy'/'ally'/'self'. "
            "actual={!r}".format(idx, target_side_raw)
        )

    target_index_raw = payload.get("target_index")
    if target_index_raw is not None and not isinstance(target_index_raw, int):
        raise DTOValidationError(
            f"planned_actions[{idx}].target_index must be int or null. "
            f"actual={type(target_index_raw).__name__}"
        )

    target_all_raw = payload.get("target_all", False)
    if not isinstance(target_all_raw, bool):
        raise DTOValidationError(
            f"planned_actions[{idx}].target_all must be bool. "
            f"actual={type(target_all_raw).__name__}"
        )

    return PlannedActionDTO(
        kind=kind,
        command=payload.get("command"),
        spell_name=payload.get("spell_name"),
        item_name=payload.get("item_name"),
        target_side=target_side_raw,
        target_index=target_index_raw,
        target_all=target_all_raw,
    )


def parse_execute_round_input_dict(payload: dict[str, Any]) -> ExecuteRoundInputDTO:
    """アダプタ受信JSON(dict)を ExecuteRoundInputDTO へ変換する。"""

    planned_actions_raw = payload.get("planned_actions")
    if not isinstance(planned_actions_raw, list):
        raise DTOValidationError(
            "planned_actions must be list[object|null]. "
            f"actual={type(planned_actions_raw).__name__}"
        )

    planned_actions: list[Optional[PlannedActionDTO]] = []
    for i, row in enumerate(planned_actions_raw):
        if row is None:
            planned_actions.append(None)
            continue
        planned_actions.append(_validate_planned_action_dto(row, idx=i))

    lifecycle_state_raw = payload.get("lifecycle_state", LIFECYCLE_READY)
    if not isinstance(lifecycle_state_raw, str):
        raise DTOValidationError(
            "lifecycle_state must be string. "
            f"actual={type(lifecycle_state_raw).__name__}"
        )

    return ExecuteRoundInputDTO(
        planned_actions=planned_actions,
        lifecycle_state=lifecycle_state_raw,
    )
