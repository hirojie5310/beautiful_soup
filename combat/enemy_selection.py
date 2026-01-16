# combat/enemy_selection.py
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


def _safe_int(v: Any, default: int = 0) -> int:
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class LocationMonsters:
    location: str
    monster_names: Tuple[str, ...]
    avg_level: int
    min_level: int
    max_level: int
    boss_count: int  # ← 追加


def build_location_index(
    monsters_by_name: Dict[str, Dict[str, Any]],
) -> List[LocationMonsters]:
    location_to_monsters: Dict[str, List[str]] = {}

    for monster_name, monster in monsters_by_name.items():
        maps = monster.get("Maps")
        if not isinstance(maps, list):
            continue

        mname = str(monster_name).strip()
        if not mname:
            continue

        for loc in maps:
            if isinstance(loc, str) and loc.strip():
                location_to_monsters.setdefault(loc.strip(), []).append(mname)

    entries: List[LocationMonsters] = []
    for loc, names in location_to_monsters.items():
        unique_names = list(dict.fromkeys(names))

        boss_count = 0
        levels = []

        for n in unique_names:
            mon = monsters_by_name.get(n)
            if not isinstance(mon, dict):
                continue

            if _is_boss(mon):
                boss_count += 1

            lv = _safe_int(mon.get("Level"), default=0)
            if lv > 0:
                levels.append(lv)

        if levels:
            min_lv = min(levels)
            max_lv = max(levels)
            avg_lv = int(round(sum(levels) / len(levels)))
        else:
            # レベルが取れない場所（欠損/キー違い等）
            min_lv = max_lv = avg_lv = 0

        entries.append(
            LocationMonsters(
                location=loc,
                monster_names=tuple(unique_names),
                avg_level=avg_lv,
                min_level=min_lv,
                max_level=max_lv,
                boss_count=boss_count,
            )
        )

    # 変更前（場所名順）
    # entries.sort(key=lambda x: x.location)

    # 変更後（平均Lv → 場所名の順）
    entries.sort(key=lambda x: (x.avg_level, x.location))
    return entries


def _is_boss(monster_def: Dict[str, Any]) -> bool:
    # PlotBattles が「存在して list で、1件以上」ならボス扱い
    pb = monster_def.get("PlotBattles")
    return isinstance(pb, list) and len(pb) > 0


def pick_enemy_names(
    entry,  # LocationMonsters
    monsters_by_name: Dict[str, Dict[str, Any]],
    *,
    k_min: int = 2,
    k_max: int = 6,
) -> List[str]:
    """
    仕様:
      - entry の候補に PlotBattles 持ち（ボス）が含まれるなら、ボスを 1 体だけ出す
      - それ以外は通常どおり 2〜4体を重複OKで出す
    """
    candidates = list(entry.monster_names)
    if not candidates:
        raise ValueError("この場所に紐づくモンスターがありません。")

    bosses: List[str] = []
    normals: List[str] = []

    for name in candidates:
        mdef = monsters_by_name.get(name)
        if isinstance(mdef, dict) and _is_boss(mdef):
            bosses.append(name)
        else:
            normals.append(name)

    # ボス候補がいる場所なら「ボス1体のみ」
    if bosses:
        return [random.choice(bosses)]

    # 通常：2〜4体、重複OK
    if k_min < 1 or k_max < k_min:
        raise ValueError("k_min/k_max の指定が不正です。")
    k = random.randint(k_min, k_max)
    return random.choices(normals if normals else candidates, k=k)


# パーティメンバーの平均レベルを計算
def calc_party_avg_level(party_members) -> int:
    levels = []

    for pm in party_members:
        lv = None

        # PartyMemberRuntime
        if hasattr(pm, "stats") and hasattr(pm.stats, "level"):
            lv = pm.stats.level

        # dict fallback
        elif isinstance(pm, dict):
            lv = pm.get("level") or pm.get("Level")

        if isinstance(lv, (int, float)) and lv > 0:
            levels.append(int(lv))

    return int(round(sum(levels) / len(levels))) if levels else 0


def danger_label(entry: LocationMonsters, party_avg_lv: int) -> str:
    # Boss 戦は常に Boss
    if entry.boss_count > 0:
        return "Boss"

    diff = entry.avg_level - party_avg_lv
    if diff >= 10:
        return "HIGH"
    if diff <= -10:
        return "LOW"
    return "NORMAL"
