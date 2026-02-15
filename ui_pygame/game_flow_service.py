# ui_pygame.game_flow_service.py
# 再利用しやすいドメイン呼び出し集約ロジック（UI 実装詳細は引数コールバック化）
# prepare_battle_resources（パーティ/魔法/敵生成）
# select_enemy_names_from_groups（ロケーション→敵名解決）
from __future__ import annotations

from typing import Any, Callable, Sequence, cast

from assets.data.data_loader import ExplicitGroupDef

from combat.char_build import build_party_members_from_save
from combat.enemy_build import build_enemies
from combat.enemy_selection import (
    LocationGroup,
    LocationMonsters,
    build_groups,
    build_location_index,
    pick_enemy_names,
)
from combat.magic_menu import build_party_magic_lists
from combat.models import EnemyRuntime, PartyMemberRuntime


def _to_ui_magic_candidates(
    party_magic_lists: Sequence[Sequence[tuple[str, object, int]]],
    member_idx: int,
) -> list[tuple[str, int, int]]:
    """Convert domain magic tuples to UI-facing (name, level, cost) tuples."""
    out: list[tuple[str, int, int]] = []
    for row in party_magic_lists[member_idx] or []:
        name = str(row[0])
        lv = int(row[2])
        out.append((name, lv, 0))
    return out


def prepare_battle_resources(
    *,
    state,
    level_table,
    enemy_names: list[str] | None,
    select_enemy_names: Callable[
        [list[PartyMemberRuntime], Callable[[int], list[tuple[str, int, int]]]],
        list[str],
    ],
) -> tuple[
    list[EnemyRuntime],
    list[PartyMemberRuntime],
    Callable[[int], list[tuple[str, int, int]]],
]:
    """Build party/magic/enemies for a single battle session."""
    party_members = build_party_members_from_save(
        save=state.save,
        weapons=state.weapons,
        armors=state.armors,
        jobs_by_name=state.jobs_by_name,
        level_table=level_table,
    )
    party_magic_lists = cast(
        Sequence[Sequence[tuple[str, object, int]]],
        build_party_magic_lists(state),
    )

    def build_magic_fn(member_idx: int) -> list[tuple[str, int, int]]:
        return _to_ui_magic_candidates(party_magic_lists, member_idx)

    resolved_enemy_names = enemy_names
    if resolved_enemy_names is None:
        resolved_enemy_names = select_enemy_names(party_members, build_magic_fn)

    enemies = build_enemies(
        enemy_defs_by_name=state.monsters,
        spells_by_name=state.spells,
        enemy_names=resolved_enemy_names,
    )
    return enemies, party_members, build_magic_fn


def select_enemy_names_from_groups(
    *,
    monsters: dict[str, dict[str, Any]],
    explicit_groups: dict[str, ExplicitGroupDef],
    choose_group: Callable[[list[LocationGroup]], LocationGroup | None],
    choose_floor: Callable[[list[LocationMonsters]], LocationMonsters | None],
    warn_unknown_location: Callable[[str, str], None],
) -> list[str]:
    """Resolve enemy names by using location-group/floor selectors."""
    flat_locations = build_location_index(monsters)
    all_locations = {loc.location for loc in flat_locations}
    for group_name, entry in explicit_groups.items():
        for location_name in entry["locations"]:
            if location_name not in all_locations:
                warn_unknown_location(group_name, location_name)

    groups = build_groups(flat_locations, explicit_groups=explicit_groups)

    selected = None
    while selected is None:
        group = choose_group(groups)
        if group is None:
            continue
        selected = choose_floor(group.children)

    return pick_enemy_names(selected, monsters, k_min=2, k_max=6)
