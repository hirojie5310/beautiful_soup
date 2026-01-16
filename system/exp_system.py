from dataclasses import dataclass
from typing import Optional
from bisect import bisect_right
import csv


@dataclass(frozen=True)
class LevelStatus:
    level: int
    total_exp: int
    exp_in_level: int
    exp_to_next: int
    is_max_level: bool


class LevelTable:
    def __init__(self, csv_path: str):
        rows: list[tuple[int, int, int]] = []  # (level, next_exp, accumulation_exp)

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                level = int(r["level"])
                next_exp = int(r["next_exp"])
                acc = int(r["accumulation_exp"])
                rows.append((level, next_exp, acc))

        # sort & validate
        rows.sort(key=lambda x: x[2])  # accumulation_exp
        for i in range(1, len(rows)):
            if rows[i][2] < rows[i - 1][2]:
                raise ValueError("accumulation_exp が昇順ではありません")

        self.levels = [r[0] for r in rows]
        self.next_exp = {r[0]: r[1] for r in rows}
        self.lower = {r[0]: r[2] for r in rows}
        self.max_level = self.levels[-1]

        self.next_lower: dict[int, Optional[int]] = {}
        for i, lv in enumerate(self.levels):
            self.next_lower[lv] = rows[i + 1][2] if i + 1 < len(rows) else None

        # ★追加：二分探索用（accumulation_exp の昇順配列）
        self._accum_list = [r[2] for r in rows]

    def level_exp_range(self, level: int) -> tuple[int, Optional[int]]:
        if level not in self.lower:
            raise ValueError(f"未知の level: {level}")
        lower = self.lower[level]
        nl = self.next_lower[level]
        return (lower, None) if nl is None else (lower, nl - 1)

    def clamp_exp_to_level_lower(self, level: int, total_exp: int) -> int:
        total_exp = max(0, int(total_exp))
        lower, upper = self.level_exp_range(level)
        if upper is None:
            return total_exp if total_exp >= lower else lower
        return total_exp if (lower <= total_exp <= upper) else lower

    def status_from_level_and_exp(self, level: int, total_exp: int) -> LevelStatus:
        total_exp = self.clamp_exp_to_level_lower(level, total_exp)
        lower, upper = self.level_exp_range(level)
        exp_in_level = total_exp - lower

        is_max = upper is None
        if is_max:
            exp_to_next = 0
        else:
            next_exp = upper - lower + 1
            exp_to_next = max(0, next_exp - exp_in_level)

        return LevelStatus(level, total_exp, exp_in_level, exp_to_next, is_max)

    def status_from_total_exp(self, total_exp: int) -> LevelStatus:
        """
        total_exp（累積経験値）から現在レベルを判定し、状態を返す。
        ルール：accumulation_exp が「そのレベルの下限」なので、
              total_exp が属する最大の lower を持つ level が現在レベル。
        """
        total_exp = max(0, int(total_exp))

        # idx = total_exp を挿入できる位置（右側）- 1 ＝ 属するレベルのindex
        idx = bisect_right(self._accum_list, total_exp) - 1
        if idx < 0:
            idx = 0
        if idx >= len(self.levels):
            idx = len(self.levels) - 1

        level = self.levels[idx]
        lower = self._accum_list[idx]
        exp_in_level = total_exp - lower

        nl = self.next_lower[level]
        if nl is None:
            # 最大レベル
            return LevelStatus(
                level=level,
                total_exp=total_exp,
                exp_in_level=exp_in_level,
                exp_to_next=0,
                is_max_level=True,
            )

        # 次レベルまでの必要量 = (次レベルの下限 - 現レベルの下限)
        need_to_next = nl - lower
        exp_to_next = max(0, need_to_next - exp_in_level)

        return LevelStatus(
            level=level,
            total_exp=total_exp,
            exp_in_level=exp_in_level,
            exp_to_next=exp_to_next,
            is_max_level=False,
        )
