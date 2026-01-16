# ============================================================
# initiative: 行動順

# calc_initiative	行動順を決めるためのイニシアティブ値（素早さ＋乱数）を計算する簡易関数
# ============================================================

import random


def calc_initiative(agility: int, rng: random.Random) -> int:
    # 適当な例: Agi * 10 + 0〜9 の乱数
    return agility * 10 + rng.randint(0, 9)
