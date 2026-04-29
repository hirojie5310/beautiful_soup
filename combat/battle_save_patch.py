from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class BattleSavePatch:
    """戦闘終了時に save へ反映された差分。"""

    resource_changes: dict[str, dict[str, int]] = field(default_factory=dict)
    party_changes: list[dict[str, Any]] = field(default_factory=list)
    inventory_changes: list[dict[str, Any]] = field(default_factory=list)
    item_stock_changes: list[dict[str, Any]] = field(default_factory=list)
    rewards: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_changes": self.resource_changes,
            "party_changes": self.party_changes,
            "inventory_changes": self.inventory_changes,
            "item_stock_changes": self.item_stock_changes,
            "rewards": self.rewards,
        }


def _ensure_dict(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        value = {}
        parent[key] = value
    return value


def _set_numeric_leaf(root: dict[str, Any], path: list[str], value: int) -> None:
    if not path:
        return
    current = root
    for key in path[:-1]:
        current = _ensure_dict(current, str(key))
    current[str(path[-1])] = int(value)


def _save_party_entry_by_name(save: dict[str, Any], name: str) -> dict[str, Any] | None:
    party = save.get("party")
    if not isinstance(party, list):
        return None
    for entry in party:
        if isinstance(entry, dict) and entry.get("name") == name:
            return entry
    return None


def apply_battle_save_patch(save: dict[str, Any], patch: BattleSavePatch) -> None:
    """BattleSavePatch の after 値を save へ適用する。"""

    if not isinstance(save, dict):
        return

    resources = patch.resource_changes
    if "gil" in resources:
        save["gil"] = int(resources["gil"].get("after", save.get("gil", 0)))
    if "cp" in resources:
        save["CP"] = int(resources["cp"].get("after", save.get("CP", 0)))

    for member_patch in patch.party_changes:
        if not isinstance(member_patch, dict):
            continue
        name = member_patch.get("name")
        if not isinstance(name, str) or not name:
            continue
        entry = _save_party_entry_by_name(save, name)
        if entry is None:
            continue

        for key in ("hp", "max_hp", "level", "exp"):
            change = member_patch.get(key)
            if isinstance(change, dict) and "after" in change:
                entry[key] = int(change["after"])

        job_level_patch = member_patch.get("job_level")
        if isinstance(job_level_patch, dict):
            job_level = _ensure_dict(entry, "job_level")
            for key in ("level", "skill_point"):
                change = job_level_patch.get(key)
                if isinstance(change, dict) and "after" in change:
                    job_level[key] = int(change["after"])

        mp_levels_patch = member_patch.get("mp_levels")
        if isinstance(mp_levels_patch, dict):
            mp_levels = _ensure_dict(entry, "mp_levels")
            mp = _ensure_dict(entry, "mp")
            for level, level_patch in mp_levels_patch.items():
                if not isinstance(level_patch, dict):
                    continue
                row = _ensure_dict(mp_levels, str(level))
                if "current_after" in level_patch:
                    current = int(level_patch["current_after"])
                    row["current"] = current
                    mp[f"L{level}MP"] = current
                if "max_after" in level_patch:
                    row["max"] = int(level_patch["max_after"])

    inventory = _ensure_dict(save, "inventory")
    for change in patch.inventory_changes:
        path = change.get("path")
        if isinstance(path, list) and "after" in change:
            _set_numeric_leaf(inventory, [str(part) for part in path], int(change["after"]))

    item_stock = _ensure_dict(save, "item_stock")
    for change in patch.item_stock_changes:
        path = change.get("path")
        if isinstance(path, list) and "after" in change:
            _set_numeric_leaf(item_stock, [str(part) for part in path], int(change["after"]))


def _changed_int(before: Any, after: Any) -> dict[str, int] | None:
    before_int = _safe_int(before, 0)
    after_int = _safe_int(after, 0)
    if before_int == after_int:
        return None
    return {
        "before": before_int,
        "after": after_int,
        "delta": after_int - before_int,
    }


def _party_by_name(save: dict[str, Any]) -> dict[str, dict[str, Any]]:
    party = save.get("party")
    if not isinstance(party, list):
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for entry in party:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if isinstance(name, str) and name:
            rows[name] = entry
    return rows


def _mp_level_changes(before: Any, after: Any) -> dict[str, dict[str, int]]:
    before_rows = before if isinstance(before, dict) else {}
    after_rows = after if isinstance(after, dict) else {}
    changes: dict[str, dict[str, int]] = {}
    for level in sorted({str(key) for key in before_rows} | {str(key) for key in after_rows}):
        before_row = before_rows.get(level)
        after_row = after_rows.get(level)
        if not isinstance(before_row, dict):
            before_row = {}
        if not isinstance(after_row, dict):
            after_row = {}
        current_change = _changed_int(before_row.get("current"), after_row.get("current"))
        max_change = _changed_int(before_row.get("max"), after_row.get("max"))
        row_change: dict[str, int] = {}
        if current_change is not None:
            row_change["current_before"] = current_change["before"]
            row_change["current_after"] = current_change["after"]
            row_change["current_delta"] = current_change["delta"]
        if max_change is not None:
            row_change["max_before"] = max_change["before"]
            row_change["max_after"] = max_change["after"]
            row_change["max_delta"] = max_change["delta"]
        if row_change:
            changes[level] = row_change
    return changes


def _job_level_change(before: Any, after: Any) -> dict[str, dict[str, int]]:
    before_row = before if isinstance(before, dict) else {}
    after_row = after if isinstance(after, dict) else {}
    changes: dict[str, dict[str, int]] = {}
    for key in ("level", "skill_point"):
        change = _changed_int(before_row.get(key), after_row.get(key))
        if change is not None:
            changes[key] = change
    return changes


def _flatten_numeric_leaves(value: Any, prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], int]:
    if isinstance(value, dict):
        rows: dict[tuple[str, ...], int] = {}
        for key, child in value.items():
            rows.update(_flatten_numeric_leaves(child, (*prefix, str(key))))
        return rows
    if isinstance(value, int) and not isinstance(value, bool):
        return {prefix: value}
    return {}


def _numeric_leaf_changes(before: Any, after: Any, *, path_key: str) -> list[dict[str, Any]]:
    before_leaves = _flatten_numeric_leaves(before)
    after_leaves = _flatten_numeric_leaves(after)
    changes: list[dict[str, Any]] = []
    for path in sorted(set(before_leaves) | set(after_leaves)):
        before_value = before_leaves.get(path, 0)
        after_value = after_leaves.get(path, 0)
        if before_value == after_value:
            continue
        changes.append(
            {
                path_key: list(path),
                "before": before_value,
                "after": after_value,
                "delta": after_value - before_value,
            }
        )
    return changes


def build_battle_save_patch(
    before_save: dict[str, Any],
    after_save: dict[str, Any],
    *,
    rewards: dict[str, Any] | None = None,
) -> BattleSavePatch:
    """save の before/after から戦闘終了差分を作る。"""

    patch = BattleSavePatch(rewards=dict(rewards or {}))

    gil_change = _changed_int(before_save.get("gil"), after_save.get("gil"))
    if gil_change is not None:
        patch.resource_changes["gil"] = gil_change
    cp_change = _changed_int(before_save.get("CP"), after_save.get("CP"))
    if cp_change is not None:
        patch.resource_changes["cp"] = cp_change

    before_party = _party_by_name(before_save)
    after_party = _party_by_name(after_save)
    for name in sorted(set(before_party) | set(after_party)):
        before_member = before_party.get(name, {})
        after_member = after_party.get(name, {})
        member_patch: dict[str, Any] = {"name": name}
        for key in ("hp", "max_hp", "level", "exp"):
            change = _changed_int(before_member.get(key), after_member.get(key))
            if change is not None:
                member_patch[key] = change
        job_level = _job_level_change(
            before_member.get("job_level"),
            after_member.get("job_level"),
        )
        if job_level:
            member_patch["job_level"] = job_level
        mp_levels = _mp_level_changes(
            before_member.get("mp_levels"),
            after_member.get("mp_levels"),
        )
        if mp_levels:
            member_patch["mp_levels"] = mp_levels
        if len(member_patch) > 1:
            patch.party_changes.append(member_patch)

    patch.inventory_changes = _numeric_leaf_changes(
        before_save.get("inventory", {}),
        after_save.get("inventory", {}),
        path_key="path",
    )
    patch.item_stock_changes = _numeric_leaf_changes(
        before_save.get("item_stock", {}),
        after_save.get("item_stock", {}),
        path_key="path",
    )
    return patch


def build_party_battle_state_patch(
    save: dict[str, Any],
    party_members: list[Any] | tuple[Any, ...],
) -> BattleSavePatch:
    """runtime party state から save に適用する HP/MP 差分を作る。"""

    after_save = {
        **save,
        "party": [
            dict(entry) if isinstance(entry, dict) else entry
            for entry in save.get("party", [])
        ],
    }
    party = after_save.get("party")
    if not isinstance(party, list):
        return BattleSavePatch()

    by_name = {
        str(getattr(member, "name", "")): member
        for member in party_members
        if str(getattr(member, "name", ""))
    }

    for index, entry in enumerate(party):
        if not isinstance(entry, dict):
            continue
        member = None
        name = entry.get("name")
        if isinstance(name, str):
            member = by_name.get(name)
        if member is None and index < len(party_members):
            member = party_members[index]
        if member is None:
            continue

        state = getattr(member, "state", None)
        if state is None:
            continue

        hp = _safe_int(getattr(state, "hp", 0), 0)
        max_hp = _safe_int(getattr(state, "max_hp", hp), hp)
        mp_pool = getattr(state, "mp_pool", {})
        max_mp_pool = getattr(state, "max_mp_pool", {})
        if not isinstance(mp_pool, dict):
            mp_pool = {}
        if not isinstance(max_mp_pool, dict):
            max_mp_pool = {}

        entry["hp"] = max(0, min(hp, max_hp))
        entry["max_hp"] = max_hp
        entry["mp"] = {}
        entry["mp_levels"] = {}
        for level in range(1, 9):
            max_uses = _safe_int(max_mp_pool.get(level, mp_pool.get(level, 0)), 0)
            current = max(0, min(_safe_int(mp_pool.get(level, 0), 0), max_uses))
            entry["mp"][f"L{level}MP"] = current
            entry["mp_levels"][str(level)] = {
                "current": current,
                "max": max_uses,
            }

    return build_battle_save_patch(save, after_save)
