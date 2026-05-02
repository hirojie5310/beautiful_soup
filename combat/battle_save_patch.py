from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from combat.constants import STATUS_ICON_KEY_BY_ENUM
from combat.enums import Status


_STATUS_EFFECT_KEY_BY_STATUS = {
    Status.POISON: "Poison",
    Status.BLIND: "Blind",
    Status.MINI: "Mini",
    Status.SILENCE: "Silence",
    Status.TOAD: "Toad",
    Status.PETRIFY: "Petrification",
    Status.KO: "KO",
    Status.CONFUSION: "Confusion",
    Status.SLEEP: "Sleep",
    Status.PARALYZE: "Paralysis",
    Status.PARTIAL_PETRIFY: "Partial Petrification",
}
_TRANSIENT_BATTLE_END_STATUSES = {
    Status.SLEEP,
    Status.CONFUSION,
    Status.PARTIAL_PETRIFY,
}
_KNOWN_STATUS_EFFECT_KEYS = {
    "Poison",
    "Blind",
    "Mini",
    "Silence",
    "Toad",
    "Petrification",
    "KO",
    "Confusion",
    "Sleep",
    "Paralysis",
    "Partial Petrification",
    "Partial Petrification (1/3)",
    "Partial Petrification (1/2)",
    "Partial Petrification (Full)",
}


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


class BattleSavePatchValidationError(ValueError):
    """BattleSavePatch の契約違反を表す例外。"""


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


def _raise_patch_error(message: str) -> None:
    raise BattleSavePatchValidationError(message)


def _require_change_triplet(
    change: Any,
    path: str,
    *,
    allowed_extra_keys: set[str] | None = None,
) -> dict[str, int]:
    if not isinstance(change, dict):
        _raise_patch_error(f"{path} must be an object")
    required_keys = {"before", "after", "delta"}
    keys = set(change.keys())
    extras = allowed_extra_keys or set()
    if not required_keys.issubset(keys) or keys - required_keys - extras:
        _raise_patch_error(f"{path} must contain only before/after/delta")
    normalized: dict[str, int] = {}
    for key in ("before", "after", "delta"):
        value = change.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            _raise_patch_error(f"{path}.{key} must be an integer")
        normalized[key] = int(value)
    if normalized["after"] - normalized["before"] != normalized["delta"]:
        _raise_patch_error(f"{path}.delta must equal after - before")
    return normalized


def _get_numeric_leaf(root: Any, path: list[str], *, missing_default: int = 0) -> int:
    current = root
    for key in path:
        if not isinstance(current, dict):
            return missing_default
        if key not in current:
            return missing_default
        current = current.get(key)
    if isinstance(current, int) and not isinstance(current, bool):
        return int(current)
    return missing_default


def _validate_resource_changes(save: dict[str, Any], changes: Any) -> None:
    if not isinstance(changes, dict):
        _raise_patch_error("patch.resource_changes must be an object")
    allowed = {"gil": "gil", "cp": "CP"}
    for key, change in changes.items():
        if key not in allowed:
            _raise_patch_error(f"patch.resource_changes.{key} is unsupported")
        triplet = _require_change_triplet(change, f"patch.resource_changes.{key}")
        current_value = save.get(allowed[key], 0)
        if current_value != triplet["before"]:
            _raise_patch_error(
                f"patch.resource_changes.{key}.before does not match current save"
            )


def _validate_party_changes(save: dict[str, Any], changes: Any) -> None:
    if not isinstance(changes, list):
        _raise_patch_error("patch.party_changes must be a list")
    for index, member_patch in enumerate(changes):
        path = f"patch.party_changes[{index}]"
        if not isinstance(member_patch, dict):
            _raise_patch_error(f"{path} must be an object")
        name = member_patch.get("name")
        if not isinstance(name, str) or not name:
            _raise_patch_error(f"{path}.name must be a non-empty string")
        entry = _save_party_entry_by_name(save, name)
        if entry is None:
            _raise_patch_error(f"{path}.name does not exist in current save.party")

        for key in ("hp", "max_hp", "level", "exp"):
            if key not in member_patch:
                continue
            triplet = _require_change_triplet(member_patch.get(key), f"{path}.{key}")
            if entry.get(key, 0) != triplet["before"]:
                _raise_patch_error(f"{path}.{key}.before does not match current save")

        if "job_level" in member_patch:
            job_level_patch = member_patch.get("job_level")
            if not isinstance(job_level_patch, dict):
                _raise_patch_error(f"{path}.job_level must be an object")
            current_job_level = entry.get("job_level")
            if current_job_level is None:
                current_job_level = {}
            if not isinstance(current_job_level, dict):
                _raise_patch_error(f"{path}.job_level target must be an object")
            for key, change in job_level_patch.items():
                if key not in {"level", "skill_point"}:
                    _raise_patch_error(f"{path}.job_level.{key} is unsupported")
                triplet = _require_change_triplet(change, f"{path}.job_level.{key}")
                if current_job_level.get(key, 0) != triplet["before"]:
                    _raise_patch_error(
                        f"{path}.job_level.{key}.before does not match current save"
                    )

        if "mp_levels" in member_patch:
            mp_levels_patch = member_patch.get("mp_levels")
            if not isinstance(mp_levels_patch, dict):
                _raise_patch_error(f"{path}.mp_levels must be an object")
            current_mp_levels = entry.get("mp_levels")
            if current_mp_levels is None:
                current_mp_levels = {}
            if not isinstance(current_mp_levels, dict):
                _raise_patch_error(f"{path}.mp_levels target must be an object")
            for level, row_change in mp_levels_patch.items():
                row_path = f"{path}.mp_levels.{level}"
                if not isinstance(row_change, dict):
                    _raise_patch_error(f"{row_path} must be an object")
                row = current_mp_levels.get(level)
                if row is None:
                    row = {}
                if not isinstance(row, dict):
                    _raise_patch_error(f"{row_path} target must be an object")
                for prefix, current_key in (("current", "current"), ("max", "max")):
                    keys = {f"{prefix}_before", f"{prefix}_after", f"{prefix}_delta"}
                    present = [key for key in keys if key in row_change]
                    if present and len(present) != 3:
                        _raise_patch_error(f"{row_path} must include full {prefix}_* triplet")
                    if present:
                        triplet = _require_change_triplet(
                            {
                                "before": row_change[f"{prefix}_before"],
                                "after": row_change[f"{prefix}_after"],
                                "delta": row_change[f"{prefix}_delta"],
                            },
                            f"{row_path}.{prefix}",
                        )
                        if row.get(current_key, 0) != triplet["before"]:
                            _raise_patch_error(
                                f"{row_path}.{prefix}_before does not match current save"
                            )
                unsupported = set(row_change.keys()) - {
                    "current_before",
                    "current_after",
                    "current_delta",
                    "max_before",
                    "max_after",
                    "max_delta",
                }
                if unsupported:
                    unsupported_key = sorted(unsupported)[0]
                    _raise_patch_error(f"{row_path}.{unsupported_key} is unsupported")

        if "status_effects" in member_patch:
            status_patch = member_patch.get("status_effects")
            if not isinstance(status_patch, dict):
                _raise_patch_error(f"{path}.status_effects must be an object")
            keys = set(status_patch.keys())
            if keys != {"before", "after"}:
                _raise_patch_error(f"{path}.status_effects must contain only before/after")
            for key in ("before", "after"):
                value = status_patch.get(key)
                if not isinstance(value, dict):
                    _raise_patch_error(f"{path}.status_effects.{key} must be an object")
                for status_name, enabled in value.items():
                    if not isinstance(status_name, str) or not status_name:
                        _raise_patch_error(
                            f"{path}.status_effects.{key} keys must be non-empty strings"
                        )
                    if not isinstance(enabled, bool):
                        _raise_patch_error(
                            f"{path}.status_effects.{key}.{status_name} must be a boolean"
                        )
            current_status_effects = entry.get("status_effects")
            if current_status_effects is None:
                current_status_effects = {}
            if not isinstance(current_status_effects, dict):
                _raise_patch_error(f"{path}.status_effects target must be an object")
            normalized_current = {
                str(key): bool(value)
                for key, value in current_status_effects.items()
            }
            if normalized_current != status_patch["before"]:
                _raise_patch_error(
                    f"{path}.status_effects.before does not match current save"
                )

        if "status_icons" in member_patch:
            status_icons_patch = member_patch.get("status_icons")
            if not isinstance(status_icons_patch, dict):
                _raise_patch_error(f"{path}.status_icons must be an object")
            if set(status_icons_patch.keys()) != {"before", "after"}:
                _raise_patch_error(f"{path}.status_icons must contain only before/after")
            for key in ("before", "after"):
                value = status_icons_patch.get(key)
                if not isinstance(value, list):
                    _raise_patch_error(f"{path}.status_icons.{key} must be a list")
                for item_index, item in enumerate(value):
                    if not isinstance(item, str) or not item:
                        _raise_patch_error(
                            f"{path}.status_icons.{key}[{item_index}] must be a non-empty string"
                        )
            current_status_icons = _normalize_status_icons(entry.get("status_icons"))
            if current_status_icons != _normalize_status_icons(status_icons_patch["before"]):
                _raise_patch_error(
                    f"{path}.status_icons.before does not match current save"
                )


def _validate_leaf_changes(root: Any, changes: Any, *, path_label: str) -> None:
    if not isinstance(changes, list):
        _raise_patch_error(f"{path_label} must be a list")
    for index, change in enumerate(changes):
        row_path = f"{path_label}[{index}]"
        if not isinstance(change, dict):
            _raise_patch_error(f"{row_path} must be an object")
        raw_path = change.get("path")
        if not isinstance(raw_path, list) or not raw_path:
            _raise_patch_error(f"{row_path}.path must be a non-empty list")
        normalized_path: list[str] = []
        for part_index, part in enumerate(raw_path):
            if not isinstance(part, str) or not part:
                _raise_patch_error(f"{row_path}.path[{part_index}] must be a non-empty string")
            normalized_path.append(part)
        triplet = _require_change_triplet(
            change,
            row_path,
            allowed_extra_keys={"path"},
        )
        current_value = _get_numeric_leaf(root, normalized_path, missing_default=0)
        if current_value != triplet["before"]:
            _raise_patch_error(f"{row_path}.before does not match current save")


def validate_battle_save_patch(save: dict[str, Any], patch: BattleSavePatch) -> None:
    if not isinstance(save, dict):
        _raise_patch_error("save must be a dictionary")
    if not isinstance(patch, BattleSavePatch):
        _raise_patch_error("patch must be BattleSavePatch")
    if not isinstance(patch.rewards, dict):
        _raise_patch_error("patch.rewards must be an object")
    _validate_resource_changes(save, patch.resource_changes)
    _validate_party_changes(save, patch.party_changes)
    _validate_leaf_changes(
        save.get("inventory", {}),
        patch.inventory_changes,
        path_label="patch.inventory_changes",
    )
    _validate_leaf_changes(
        save.get("item_stock", {}),
        patch.item_stock_changes,
        path_label="patch.item_stock_changes",
    )


def apply_battle_save_patch(save: dict[str, Any], patch: BattleSavePatch) -> None:
    """BattleSavePatch の after 値を save へ適用する。"""

    validate_battle_save_patch(save, patch)

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

        status_effects_patch = member_patch.get("status_effects")
        if isinstance(status_effects_patch, dict) and isinstance(
            status_effects_patch.get("after"), dict
        ):
            entry["status_effects"] = {
                str(key): bool(value)
                for key, value in status_effects_patch["after"].items()
            }

        status_icons_patch = member_patch.get("status_icons")
        if isinstance(status_icons_patch, dict) and isinstance(
            status_icons_patch.get("after"), list
        ):
            entry["status_icons"] = _normalize_status_icons(status_icons_patch["after"])

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


def _normalize_status_icons(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for row in value:
        if not isinstance(row, str) or not row:
            continue
        rows.append(row)
    return sorted(set(rows))


def _status_changes(before: Any, after: Any) -> dict[str, Any] | None:
    before_row = before if isinstance(before, dict) else {}
    after_row = after if isinstance(after, dict) else {}
    if before_row == after_row:
        return None
    return {
        "before": {str(key): bool(value) for key, value in before_row.items()},
        "after": {str(key): bool(value) for key, value in after_row.items()},
    }


def _status_icons_change(before: Any, after: Any) -> dict[str, list[str]] | None:
    before_rows = _normalize_status_icons(before)
    after_rows = _normalize_status_icons(after)
    if before_rows == after_rows:
        return None
    return {"before": before_rows, "after": after_rows}


def _serialize_status_effects_from_runtime(
    existing_effects: Any,
    statuses: Any,
) -> dict[str, bool]:
    next_effects = (
        {str(key): bool(value) for key, value in existing_effects.items()}
        if isinstance(existing_effects, dict)
        else {}
    )
    for key in _KNOWN_STATUS_EFFECT_KEYS:
        next_effects[key] = False
    if not isinstance(statuses, (set, list, tuple)):
        return next_effects

    for status in statuses:
        if status in _TRANSIENT_BATTLE_END_STATUSES:
            continue
        save_key = _STATUS_EFFECT_KEY_BY_STATUS.get(status)
        if save_key:
            next_effects[save_key] = True
    return next_effects


def _serialize_status_icons_from_runtime(statuses: Any) -> list[str]:
    if not isinstance(statuses, (set, list, tuple)):
        return []
    rows: list[str] = []
    for status in statuses:
        if status in _TRANSIENT_BATTLE_END_STATUSES:
            continue
        icon_key = STATUS_ICON_KEY_BY_ENUM.get(status)
        if isinstance(icon_key, str) and icon_key:
            rows.append(icon_key)
    return sorted(set(rows))


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
        status_effects = _status_changes(
            before_member.get("status_effects"),
            after_member.get("status_effects"),
        )
        if status_effects is not None:
            member_patch["status_effects"] = status_effects
        status_icons = _status_icons_change(
            before_member.get("status_icons"),
            after_member.get("status_icons"),
        )
        if status_icons is not None:
            member_patch["status_icons"] = status_icons
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
        statuses = getattr(state, "statuses", set())
        entry["status_effects"] = _serialize_status_effects_from_runtime(
            entry.get("status_effects"),
            statuses,
        )
        entry["status_icons"] = _serialize_status_icons_from_runtime(statuses)

    return build_battle_save_patch(save, after_save)
