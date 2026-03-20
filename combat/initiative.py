# ============================================================
# initiative: 行動順

# calc_initiative	行動順を決めるためのイニシアティブ値を計算する
# ============================================================

import random
from typing import Optional


def command_weight(action: Optional[object]) -> int:
    """
    PlannedAction などからコマンド重量を引く。

    現時点では明示データ未整備のため、`weight` 属性があれば使い、
    それ以外は 0 を返す。
    """
    if action is None:
        return 0
    return int(getattr(action, "weight", 0) or 0)


def calc_initiative(agility: int, rng: random.Random, weight: int = 0) -> int:
    """
    行動値 = (Agility × 2) － Weight ＋ 乱数(0 ～ Agility)
    """
    agility = max(0, int(agility))
    weight = int(weight)
    return agility * 2 - weight + rng.randint(0, agility)
