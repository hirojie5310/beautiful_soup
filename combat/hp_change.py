from __future__ import annotations

from typing import Optional

from combat.models import BattleActorState


def apply_signed_hp_change(
    target_state: BattleActorState,
    amount: int,
    *,
    max_hp: Optional[int] = None,
) -> tuple[int, int, int]:
    """
    HP変動を適用する。

    amount:
      - 正数: ダメージ
      - 負数: 回復

    Returns:
      (old_hp, new_hp, actual_change)
      - actual_change は実際のHP差分
        - ダメージ時は正数
        - 回復時は負数
    """
    old_hp = int(target_state.hp)

    if amount >= 0:
        new_hp = max(0, old_hp - int(amount))
    else:
        heal = abs(int(amount))
        resolved_max_hp = max_hp
        if resolved_max_hp is None:
            resolved_max_hp = getattr(target_state, "max_hp", None)
        if resolved_max_hp is None:
            new_hp = old_hp + heal
        else:
            new_hp = min(old_hp + heal, int(resolved_max_hp))

    target_state.hp = int(new_hp)
    actual_change = old_hp - int(new_hp)
    return old_hp, int(new_hp), int(actual_change)
