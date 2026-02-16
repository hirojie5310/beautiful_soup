# combat/dto.py
# ラウンド実行の入出力スキーマとして
# PlannedActionDTO / ExecuteRoundInputDTO / ExecuteRoundOutputDTO を定義
# これで「アダプタ（Flask等）⇔ユースケース」間の契約を先に固定
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from combat.enums import BattleKind
from combat.models import BattleEvent, PlannedAction, TargetSide


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


@dataclass
class ExecuteRoundOutputDTO:
    logs: list[str]
    end_reason: str
    escaped: bool
    enemy_was_physically_hit: bool
    events: list[BattleEvent]


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
    }
