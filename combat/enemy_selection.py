# combat/enemy_selection.py
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional
from collections import defaultdict

from combat.enums import World
from assets.data.data_loader import ExplicitGroupDef


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


@dataclass
class LocationGroup:
    group_name: str
    children: list[LocationMonsters]
    avg_level: int
    min_level: int
    max_level: int
    boss_count: int
    world: World | None = None
    order: int = 999


FLOOR_WORDS = re.compile(r"(B\d+|F\d+|Base|Room|Floor|Hall)$", re.IGNORECASE)


def split_location_name(name: str) -> tuple[str, str | None]:
    if " " not in name:
        return name, None

    parent, child = name.rsplit(" ", 1)

    # B1 / 2F / Base / Room 等
    if FLOOR_WORDS.search(child):
        return parent, child

    # Crystal Room のような複合語対応
    parts = name.split()
    for i in range(len(parts) - 1, 0, -1):
        candidate = " ".join(parts[i:])
        if FLOOR_WORDS.search(candidate):
            parent = " ".join(parts[:i])
            return parent, candidate

    return name, None


def build_groups(
    locations: list[LocationMonsters],
    *,
    explicit_groups: dict[str, ExplicitGroupDef] | None = None,
) -> list[LocationGroup]:
    used: set[str] = set()
    groups: list[LocationGroup] = []

    explicit_groups = explicit_groups or {}

    # ① 明示グループ
    for gname, entry in explicit_groups.items():
        members = entry["locations"]

        world_str = entry.get("world")
        world = World.from_str(world_str) if world_str else None

        order = entry.get("order", 999)

        childs = [loc for loc in locations if loc.location in members]
        if not childs:
            continue

        group = make_group(gname, childs)
        group.world = world
        group.order = order

        groups.append(group)

        used.update(loc.location for loc in childs)

    # ② 残りは自動グループ
    for loc in locations:
        if loc.location in used:
            continue

        group_name, _ = split_location_name(loc.location)
        groups.append(make_group(group_name, [loc]))
        used.add(loc.location)

    # order 順で最終ソート（重要）
    groups.sort(key=lambda g: g.order)

    return groups


def make_group(
    group_name: str,
    children: list[LocationMonsters],
) -> LocationGroup:
    """
    LocationMonsters の集合から LocationGroup を作る
    """
    assert children, "make_group: children must not be empty"

    min_levels = [c.min_level for c in children if c.min_level > 0]
    max_levels = [c.max_level for c in children if c.max_level > 0]
    avg_levels = [c.avg_level for c in children if c.avg_level > 0]

    return LocationGroup(
        group_name=group_name,
        children=sorted(children, key=lambda c: c.location),
        min_level=min(min_levels) if min_levels else 0,
        max_level=max(max_levels) if max_levels else 0,
        avg_level=int(round(sum(avg_levels) / len(avg_levels))) if avg_levels else 0,
        boss_count=sum(c.boss_count for c in children),
    )


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
