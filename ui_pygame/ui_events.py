from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from combat.models import BattleEvent as CombatBattleEvent


# 音イベント（UI層）
@dataclass(frozen=True)
class AudioEvent:
    type: Literal["bgm", "bgm_stop", "se"]
    payload: dict[str, Any] | None = None


UiEvent: TypeAlias = CombatBattleEvent | AudioEvent
