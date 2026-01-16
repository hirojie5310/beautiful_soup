# ============================================================
# ui_types: TargetSide, InputMode などの型定義

# TargetSide: ターゲットの種類（enemy/ally/self）
# InputMode: UIの入力モード（normal/targeting/menu/paused）
# ============================================================

from typing import TypedDict, Literal
from dataclasses import dataclass

from combat.enums import BattleKind

InputMode = Literal[
    "member",
    "command",
    "magic",
    "aoe_choice",
    "item",
    "target_side",
    "target_enemy",
    "target_ally",
]


@dataclass(frozen=True)
class CommandCandidate:
    cmd: str
    kind: BattleKind
