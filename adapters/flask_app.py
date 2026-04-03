# adapters/flask_app.py
# create_app() でエラーハンドラ登録、JSON受信、DTO変換、
# execute_round_dto 呼び出し、JSONレスポンス返却までを接続
from __future__ import annotations

import io
import json
import os
from collections import Counter
from copy import deepcopy
from pathlib import Path
from random import Random
from typing import Any, Sequence

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_file,
    send_from_directory,
)

from adapters.flask_error_handlers import register_flask_error_handlers
from assets.data.data_loader import load_explicit_groups
from combat.dto import (
    ExecuteRoundInputDTO,
    parse_execute_round_input_dict,
    to_json_ready_dict,
)
from combat.enemy_selection import build_groups, build_location_index, pick_enemy_names
from combat.errors import InputValidationError
from combat.progression import apply_victory_rewards
from combat.input_ui import normalize_battle_command
from combat.inventory import build_item_list, is_item_visible_in_context
from combat.item_effects import infer_battle_item_target_side
from combat.magic_menu import (
    build_magic_stock_by_level,
    build_party_magic_info,
    build_party_magic_lists,
    dump_equipped_magic_slots_to_entry,
    load_equipped_magic_slots_from_entry,
)
from combat.magic_damage import healing_spell_kind
from combat.runtime_state import init_runtime_state
from combat.char_build import (
    apply_job_equipment_restrictions,
    build_party_members_from_save,
    compute_character_final_stats,
)
from combat.usecases import BattleSession, build_battle_session, execute_round_dto
from combat.models import EquipmentSet
from combat.constants import STATUS_ICON_KEY_BY_ENUM
from assets.data.data_loader import save_savedata
from ui_pygame.field_effects import (
    dec_inventory_item,
    get_inventory_item_count,
    inc_inventory_item,
    sync_equipment_to_save,
)
from adapters.flask_menu_actions import make_cast_field_magic_fn, make_use_field_item_fn
from utils.name_normalize import normalize_name
from utils.text_normalize import normalize_text_basic
from system.cp_system import compute_job_change_cp_cost, load_job_attribution


def group_name_to_image_key(name: str) -> str:
    return normalize_text_basic(name).replace("'", "").replace(" ", "_")


def _resolve_location_group_bg_filename(maps_dir: Path, group_name: str) -> str | None:
    key = group_name_to_image_key(group_name)
    exts = (".png", ".jpg", ".jpeg", ".PNG", ".JPG")

    for ext in exts:
        target = maps_dir / f"{key}{ext}"
        if target.exists() and target.is_file():
            return target.name

    # Linux では大文字小文字が区別されるため、Windows/Pygame 互換で
    # 拡張子とファイル名の大文字小文字差異を吸収して探索する。
    allowed_exts = {ext.lower() for ext in exts}
    for file in maps_dir.iterdir():
        if not file.is_file():
            continue
        if file.suffix.lower() not in allowed_exts:
            continue
        if normalize_text_basic(file.stem) == key:
            return file.name

    return None


def _build_default_session(
    *, enemy_names: Sequence[str] | None = None
) -> BattleSession:
    state = init_runtime_state()
    selected_enemy_names = (
        list(enemy_names) if enemy_names else sorted(state.monsters.keys())[:3]
    )
    return build_battle_session(state=state, enemy_names=selected_enemy_names)


def _normalize_planned_actions_length(
    request_dto: ExecuteRoundInputDTO, *, expected_count: int
) -> ExecuteRoundInputDTO:
    actual_count = len(request_dto.planned_actions)
    if actual_count > expected_count:
        raise InputValidationError(
            "planned_actions has too many entries",
            details={"expected_max": expected_count, "actual": actual_count},
        )
    if actual_count == expected_count:
        return request_dto

    padded = list(request_dto.planned_actions) + [None] * (
        expected_count - actual_count
    )
    return ExecuteRoundInputDTO(
        planned_actions=padded,
        lifecycle_state=request_dto.lifecycle_state,
    )


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_party_status_snapshot(session: BattleSession) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for idx, member in enumerate(session.party_members):
        state = getattr(member, "state", None)
        hp = _safe_int(getattr(state, "hp", 0), 0)
        max_hp_raw = getattr(state, "max_hp", None)
        max_hp = _safe_int(max_hp_raw, hp) if max_hp_raw is not None else hp
        statuses = getattr(state, "statuses", set())
        status_icons: list[str] = []
        if isinstance(statuses, (set, list, tuple)):
            for st in statuses:
                icon_key = STATUS_ICON_KEY_BY_ENUM.get(st)
                if icon_key:
                    status_icons.append(str(icon_key))

        snapshots.append(
            {
                "index": idx,
                "name": str(getattr(member, "name", f"Ally {idx + 1}")),
                "hp": hp,
                "max_hp": max_hp,
                "level": _safe_int(getattr(member, "level", 0), 0),
                "portrait_key": getattr(member, "portrait_key", None),
                "status_icons": sorted(set(status_icons)),
                "is_jumping": bool(getattr(state, "is_jumping", False)),
                "jump_target_index": getattr(state, "jump_target_index", None),
            }
        )
    return snapshots


def _build_enemy_status_snapshot(session: BattleSession) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for idx, enemy in enumerate(session.enemies):
        state = getattr(enemy, "state", None)
        hp = _safe_int(getattr(state, "hp", 0), 0)
        max_hp_raw = getattr(state, "max_hp", None)
        max_hp = _safe_int(max_hp_raw, hp) if max_hp_raw is not None else hp
        snapshots.append(
            {
                "index": idx,
                "name": str(
                    getattr(enemy, "label", getattr(enemy, "name", f"Enemy {idx + 1}"))
                ),
                "sprite_id": getattr(enemy, "sprite_id", None),
                "hp": hp,
                "max_hp": max_hp,
            }
        )
    return snapshots


def _build_session_status_snapshot(session: BattleSession) -> dict[str, Any]:
    return {
        "party": _build_party_status_snapshot(session),
        "enemies": _build_enemy_status_snapshot(session),
    }


def _item_type_label_prefix(item_type: Any) -> str:
    raw = str(item_type).strip() if item_type is not None else ""
    if not raw:
        return "?"
    return raw[0].upper()


def _build_battle_item_command_candidates(
    session: BattleSession,
) -> list[dict[str, Any]]:
    state = getattr(session, "state", None)
    items_by_name = getattr(state, "items_by_name", {}) if state is not None else {}
    save = getattr(state, "save", {}) if state is not None else {}
    if not isinstance(items_by_name, dict):
        return []
    if not isinstance(save, dict):
        save = {}

    item_list = build_item_list(items_by_name, save, in_battle=True)
    candidates: list[dict[str, Any]] = []
    for item_name, item_type, qty in item_list:
        item_json = items_by_name.get(item_name, {})
        if not is_item_visible_in_context(item_json, in_combat=True):
            continue
        candidates.append(
            {
                "name": item_name,
                "item_type": item_type,
                "qty": _safe_int(qty, 0),
                "label": f"{_item_type_label_prefix(item_type)}: {item_name} ×{_safe_int(qty, 0)}",
            }
        )
    return candidates


def _build_battle_item_meta(
    items_by_name: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    for item_name, item_json in items_by_name.items():
        if not isinstance(item_json, dict):
            continue
        meta[item_name] = {
            "target_side": infer_battle_item_target_side(item_json),
        }
    return meta


def _build_member_status_snapshot(
    session: BattleSession, member: Any
) -> dict[str, Any]:
    state = getattr(member, "state", None)
    stats = getattr(member, "stats", None)
    base = getattr(member, "base", None)

    hp = _safe_int(getattr(member, "hp", getattr(state, "hp", 0)), 0)
    max_hp = _safe_int(getattr(member, "max_hp", getattr(state, "max_hp", hp)), hp)

    mp_pool = getattr(member, "mp_pool", None)
    if not isinstance(mp_pool, dict):
        mp_pool = getattr(state, "mp_pool", {})
    if not isinstance(mp_pool, dict):
        mp_pool = {}
    mp_text = "/".join(f"{_safe_int(mp_pool.get(i, 0), 0):2d}" for i in range(1, 9))

    eq = getattr(member, "equipment", None) or EquipmentSet()

    def _is_weapon(name: str | None) -> bool:
        weapons = getattr(getattr(session, "state", None), "weapons", {})
        return isinstance(name, str) and isinstance(weapons, dict) and name in weapons

    powers: list[int] = []
    accs: list[int] = []
    if _is_weapon(getattr(eq, "main_hand", None)):
        powers.append(
            _safe_int(getattr(stats, "main_power", getattr(stats, "attack", 0)), 0)
        )
        accs.append(
            _safe_int(getattr(stats, "main_accuracy", getattr(stats, "hit_rate", 0)), 0)
        )
    if _is_weapon(getattr(eq, "off_hand", None)):
        powers.append(
            _safe_int(getattr(stats, "off_power", getattr(stats, "attack", 0)), 0)
        )
        accs.append(
            _safe_int(getattr(stats, "off_accuracy", getattr(stats, "hit_rate", 0)), 0)
        )
    if not powers:
        powers = [
            _safe_int(getattr(stats, "main_power", getattr(stats, "attack", 0)), 0)
        ]
        accs = [
            _safe_int(getattr(stats, "main_accuracy", getattr(stats, "hit_rate", 0)), 0)
        ]

    atk_value = int(round(sum(powers) / len(powers)))
    acc_value = int(round(sum(accs) / len(accs)))

    atk_times = 0
    if _is_weapon(getattr(eq, "main_hand", None)):
        atk_times += _safe_int(getattr(stats, "main_atk_multiplier", 0), 0)
    if _is_weapon(getattr(eq, "off_hand", None)):
        atk_times += _safe_int(getattr(stats, "off_atk_multiplier", 0), 0)
    if atk_times == 0:
        atk_times = _safe_int(getattr(stats, "main_atk_multiplier", 0), 0)

    def_times = _safe_int(getattr(stats, "defense_multiplier", 0), 0)
    statuses = getattr(state, "statuses", set())
    status_icons: list[str] = []
    status_labels: list[str] = []
    if isinstance(statuses, (set, list, tuple)):
        for st in statuses:
            label = str(st)
            icon_key = STATUS_ICON_KEY_BY_ENUM.get(st)
            if icon_key:
                status_icons.append(str(icon_key))
            status_labels.append(label)

    exp_to_next = 0
    level_table = getattr(session, "level_table", None)
    if level_table is not None and base is not None:
        try:
            ls = level_table.status_from_level_and_exp(
                _safe_int(getattr(base, "level", getattr(member, "level", 1)), 1),
                _safe_int(getattr(base, "total_exp", 0), 0),
            )
            exp_to_next = _safe_int(getattr(ls, "exp_to_next", 0), 0)
        except Exception:
            exp_to_next = 0

    row_raw = str(getattr(base, "row", getattr(stats, "row", "front"))).lower()
    row_label = "FRONT" if row_raw == "front" else "BACK"

    return {
        "level": _safe_int(getattr(base, "level", getattr(member, "level", 0)), 0),
        "job_level": _safe_int(getattr(base, "job_level", 0), 0),
        "exp": _safe_int(getattr(base, "total_exp", 0), 0),
        "exp_to_next": exp_to_next,
        "hp": hp,
        "max_hp": max_hp,
        "mp_text": mp_text,
        "strength": _safe_int(getattr(stats, "strength", 0), 0),
        "atk_value": atk_value,
        "atk_times": atk_times,
        "agility": _safe_int(getattr(stats, "agility", 0), 0),
        "acc_value": acc_value,
        "evasion_percent": _safe_int(getattr(stats, "evasion_percent", 0), 0),
        "vitality": _safe_int(getattr(stats, "vitality", 0), 0),
        "defense": _safe_int(getattr(stats, "defense", 0), 0),
        "def_times": def_times,
        "intelligence": _safe_int(getattr(stats, "intelligence", 0), 0),
        "mind": _safe_int(getattr(stats, "mind", 0), 0),
        "magic_defense": _safe_int(getattr(stats, "magic_defense", 0), 0),
        "magic_resistance": _safe_int(getattr(stats, "magic_resistance", 0), 0),
        "row_label": row_label,
        "status_line": ",".join(status_labels) if status_labels else "-",
        "status_icons": sorted(set(status_icons)),
    }


def _build_party_menu_snapshot(session: BattleSession) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, member in enumerate(session.party_members):
        eq = getattr(member, "equipment", None)
        state = getattr(member, "state", None)
        stats = getattr(member, "stats", None)
        hp = _safe_int(getattr(state, "hp", 0), 0)
        max_hp_raw = getattr(state, "max_hp", None)
        max_hp = _safe_int(max_hp_raw, hp) if max_hp_raw is not None else hp
        rows.append(
            {
                "index": idx,
                "name": str(getattr(member, "name", f"Ally {idx + 1}")),
                "level": _safe_int(getattr(member, "level", 0), 0),
                "job": str(getattr(getattr(member, "job", None), "name", "Unknown")),
                "hp": hp,
                "max_hp": max_hp,
                "row": str(getattr(stats, "row", "front")),
                "portrait_key": getattr(member, "portrait_key", None),
                "equipment": {
                    "main_hand": getattr(eq, "main_hand", None),
                    "off_hand": getattr(eq, "off_hand", None),
                    "head": getattr(eq, "head", None),
                    "body": getattr(eq, "body", None),
                    "arms": getattr(eq, "arms", None),
                },
                "status": _build_member_status_snapshot(session, member),
            }
        )
    return rows


def _build_inventory_snapshot(session: BattleSession) -> list[dict[str, Any]]:
    state = getattr(session, "state", None)
    save = getattr(state, "save", {})
    inventory = save.get("inventory", {}) if isinstance(save, dict) else {}
    rows: list[dict[str, Any]] = []
    for item_type in ("Anywhere", "Field"):
        bucket = inventory.get(item_type, {})
        if not isinstance(bucket, dict):
            continue
        for name, count in sorted(bucket.items()):
            qty = _safe_int(count, 0)
            if qty <= 0:
                continue
            rows.append({"item_type": item_type, "name": name, "count": qty})
    return rows


def _get_saved_job_level_for_member(
    state: Any, member_index: int, job_name: str
) -> int:
    save = getattr(state, "save", {})
    if not isinstance(save, dict):
        return 1
    party = save.get("party")
    if not isinstance(party, list) or member_index < 0 or member_index >= len(party):
        return 1
    entry = party[member_index]
    if not isinstance(entry, dict):
        return 1
    job_levels = entry.get("job_levels")
    if not isinstance(job_levels, dict):
        return 1
    row = job_levels.get(job_name)
    if not isinstance(row, dict):
        return 1
    try:
        return max(1, int(row.get("level", 1)))
    except (TypeError, ValueError):
        return 1


def _build_job_candidates_by_member(
    session: BattleSession,
    job_attr: dict[str, dict[str, int]] | None = None,
) -> list[list[dict[str, Any]]]:
    state = getattr(session, "state", None)
    members = getattr(session, "party_members", [])
    jobs_by_name = getattr(state, "jobs_by_name", {}) if state is not None else {}

    if not isinstance(jobs_by_name, dict):
        return [[] for _ in members]

    job_names = sorted(
        name for name in jobs_by_name.keys() if isinstance(name, str) and name
    )
    rows: list[list[dict[str, Any]]] = []
    for member_index, member in enumerate(members):
        from_job = getattr(getattr(member, "job", None), "name", "")
        by_member: list[dict[str, Any]] = []
        for job_name in job_names:
            to_level = _get_saved_job_level_for_member(state, member_index, job_name)
            cp_cost = 0
            if (
                isinstance(job_attr, dict)
                and from_job in job_attr
                and job_name in job_attr
            ):
                cp_cost = compute_job_change_cp_cost(
                    from_job=from_job,
                    to_job=job_name,
                    to_job_level=to_level,
                    job_attr=job_attr,
                )
            by_member.append(
                {
                    "job_name": job_name,
                    "required_cp": int(cp_cost),
                    "saved_job_level": int(to_level),
                    "is_current": bool(job_name == from_job),
                }
            )
        rows.append(by_member)
    return rows


def _canon_job_code(value: str) -> str:
    return normalize_text_basic(value or "")


JOB_NAME_TO_CODE_WEB: dict[str, str] = {
    "Onion Knight": "OK",
    "Warrior": "Wa",
    "Monk": "Mo",
    "White Mage": "WM",
    "Black Mage": "BM",
    "Red Mage": "RM",
    "Ranger": "Ra",
    "Knight": "Kn",
    "Thief": "Th",
    "Scholar": "Sc",
    "Geomancer": "Ge",
    "Dragoon": "Dr",
    "Viking": "Vi",
    "Black Belt": "BB",
    "Evoker": "Ev",
    "Bard": "Ba",
    "Magus": "Ma",
    "Devout": "De",
    "Summoner": "Su",
    "Sage": "Sa",
    "Ninja": "Ni",
    "Mystic Knight": "MK",
}


def _actor_job_code(member: Any) -> str:
    job = getattr(member, "job", None)
    slug = str(getattr(job, "slug", "") or "").strip()
    if slug and len(slug) <= 3:
        return slug
    name = str(getattr(job, "name", "") or "").strip()
    if name in JOB_NAME_TO_CODE_WEB:
        return JOB_NAME_TO_CODE_WEB[name]
    inv = {_canon_job_code(k): v for k, v in JOB_NAME_TO_CODE_WEB.items()}
    name_norm = _canon_job_code(name)
    if name_norm in inv:
        return inv[name_norm]
    return slug or name


def _item_allowed_for_member(member: Any, item_raw: dict[str, Any]) -> bool:
    equipped_by = item_raw.get("EquippedBy") if isinstance(item_raw, dict) else None
    if not isinstance(equipped_by, list) or not equipped_by:
        return True
    actor_code = _canon_job_code(_actor_job_code(member))
    allow = {_canon_job_code(str(code)) for code in equipped_by}
    return actor_code in allow


def _is_two_handed_weapon(raw: dict[str, Any]) -> bool:
    if not isinstance(raw, dict):
        return False
    hands = raw.get("Hands")
    if isinstance(hands, int):
        return hands >= 2
    if isinstance(hands, str) and hands.isdigit():
        return int(hands) >= 2
    return bool(raw.get("TwoHanded"))


def _build_equip_candidates_by_member(
    session: BattleSession,
) -> list[dict[str, list[dict[str, Any]]]]:
    state = getattr(session, "state", None)
    save = getattr(state, "save", {}) if state is not None else {}
    inventory = save.get("inventory", {}) if isinstance(save, dict) else {}
    weapons = getattr(state, "weapons", {}) if state is not None else {}
    armors = getattr(state, "armors", {}) if state is not None else {}
    weapon_stock = inventory.get("Weapon", {}) if isinstance(inventory, dict) else {}
    armor_stock = inventory.get("Armor", {}) if isinstance(inventory, dict) else {}
    if not isinstance(weapons, dict):
        weapons = {}
    if not isinstance(armors, dict):
        armors = {}
    if not isinstance(weapon_stock, dict):
        weapon_stock = {}
    if not isinstance(armor_stock, dict):
        armor_stock = {}
    weapon_stock_norm = {
        normalize_name(name): _safe_int(count, 0)
        for name, count in weapon_stock.items()
        if isinstance(name, str)
    }
    armor_stock_norm = {
        normalize_name(name): _safe_int(count, 0)
        for name, count in armor_stock.items()
        if isinstance(name, str)
    }

    def _stock_count(item_type: str, item_name: str) -> int:
        bucket = weapon_stock if item_type == "Weapon" else armor_stock
        bucket_norm = weapon_stock_norm if item_type == "Weapon" else armor_stock_norm
        exact = _safe_int(bucket.get(item_name, 0), 0) if isinstance(bucket, dict) else 0
        if exact > 0:
            return exact
        return _safe_int(bucket_norm.get(normalize_name(item_name), 0), 0)

    out: list[dict[str, list[dict[str, Any]]]] = []
    slot_to_armor_type = {"head": "Helm", "body": "Armor", "arms": "Gloves"}

    for member in getattr(session, "party_members", []):
        by_slot: dict[str, list[dict[str, Any]]] = {}

        for slot in ("main_hand", "off_hand"):
            rows: list[dict[str, Any]] = [{"kind": "none", "name": None}]
            for name, raw in weapons.items():
                if not isinstance(name, str) or not isinstance(raw, dict):
                    continue
                stock_count = _stock_count("Weapon", name)
                if stock_count <= 0:
                    continue
                if not _item_allowed_for_member(member, raw):
                    continue
                if slot == "off_hand" and _is_two_handed_weapon(raw):
                    continue
                rows.append(
                    {
                        "kind": "weapon",
                        "name": name,
                        "count": stock_count,
                        "atk": _safe_int(raw.get("AttackPower", 0), 0),
                        "acc": _safe_int(raw.get("HitRate", 0), 0),
                    }
                )

            if slot == "off_hand":
                for name, raw in armors.items():
                    if not isinstance(name, str) or not isinstance(raw, dict):
                        continue
                    stock_count = _stock_count("Armor", name)
                    if stock_count <= 0:
                        continue
                    if str(raw.get("ArmorType", "")) != "Shield":
                        continue
                    if not _item_allowed_for_member(member, raw):
                        continue
                    rows.append(
                        {
                            "kind": "armor",
                            "name": name,
                            "count": stock_count,
                            "def": _safe_int(raw.get("Defense", 0), 0),
                            "eva": _safe_int(raw.get("EvasionPenalty", 0), 0),
                        }
                    )
            by_slot[slot] = rows

        for slot, armor_type in slot_to_armor_type.items():
            rows = [{"kind": "none", "name": None}]
            for name, raw in armors.items():
                if not isinstance(name, str) or not isinstance(raw, dict):
                    continue
                stock_count = _stock_count("Armor", name)
                if stock_count <= 0:
                    continue
                if str(raw.get("ArmorType", "")) != armor_type:
                    continue
                if not _item_allowed_for_member(member, raw):
                    continue
                rows.append(
                    {
                        "kind": "armor",
                        "name": name,
                        "count": stock_count,
                        "def": _safe_int(raw.get("Defense", 0), 0),
                        "eva": _safe_int(raw.get("EvasionPenalty", 0), 0),
                        "mdef": _safe_int(raw.get("MagicDefense", 0), 0),
                    }
                )
            by_slot[slot] = rows

        out.append(by_slot)
    return out


def _equipment_item_type(
    session: BattleSession,
    item_name: str | None,
) -> str | None:
    if not isinstance(item_name, str) or not item_name:
        return None
    state = getattr(session, "state", None)
    weapons = getattr(state, "weapons", {}) if state is not None else {}
    armors = getattr(state, "armors", {}) if state is not None else {}
    if isinstance(weapons, dict) and item_name in weapons:
        return "Weapon"
    if isinstance(armors, dict) and item_name in armors:
        return "Armor"
    return None


def _equipment_inventory_counter(
    session: BattleSession,
    equipment: EquipmentSet | None,
) -> Counter[tuple[str, str]]:
    eq = equipment or EquipmentSet()
    counts: Counter[tuple[str, str]] = Counter()
    for slot in ("main_hand", "off_hand", "head", "body", "arms"):
        item_name = getattr(eq, slot, None)
        item_type = _equipment_item_type(session, item_name)
        if item_type is None or not isinstance(item_name, str) or not item_name:
            continue
        counts[(item_type, item_name)] += 1
    return counts


def _apply_equipment_inventory_delta(
    session: BattleSession,
    *,
    before: EquipmentSet | None,
    after: EquipmentSet | None,
) -> None:
    save = getattr(getattr(session, "state", None), "save", {})
    before_counts = _equipment_inventory_counter(session, before)
    after_counts = _equipment_inventory_counter(session, after)

    for item_key, before_qty in before_counts.items():
        delta = before_qty - after_counts.get(item_key, 0)
        if delta <= 0:
            continue
        item_type, item_name = item_key
        inc_inventory_item(save, item_type, item_name, delta)

    for item_key, after_qty in after_counts.items():
        delta = after_qty - before_counts.get(item_key, 0)
        if delta <= 0:
            continue
        item_type, item_name = item_key
        if get_inventory_item_count(save, item_type, item_name) < delta:
            raise InputValidationError(
                "equipment item is not in inventory",
                details={"item_type": item_type, "item_name": item_name},
            )
        for _ in range(delta):
            if not dec_inventory_item(save, item_type, item_name):
                raise InputValidationError(
                    "equipment item is not in inventory",
                    details={"item_type": item_type, "item_name": item_name},
                )


def _build_menu_state_payload(
    session: BattleSession,
    *,
    job_attr: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    state = getattr(session, "state", None)
    save = getattr(state, "save", {}) if state is not None else {}
    jobs = getattr(state, "jobs_by_name", {})
    job_names = sorted(jobs.keys()) if isinstance(jobs, dict) else []
    gil = _safe_int(save.get("gil", 0), 0) if isinstance(save, dict) else 0
    cp = _safe_int(save.get("CP", 0), 0) if isinstance(save, dict) else 0
    menu_magic_setup = _ensure_menu_magic_setup(session)
    return {
        "party": _build_party_menu_snapshot(session),
        "inventory": _build_inventory_snapshot(session),
        "magic_candidates_by_member": _build_magic_command_candidates_by_member(
            session
        ),
        "magic_setup": menu_magic_setup,
        "jobs": job_names,
        "job_candidates_by_member": _build_job_candidates_by_member(session, job_attr),
        "equip_candidates_by_member": _build_equip_candidates_by_member(session),
        "resources": {"gil": gil, "cp": cp, "cp_max": 255},
    }


def _refresh_session_party(session: BattleSession) -> None:
    hp_by_name = {m.name: int(m.state.hp) for m in session.party_members}
    session.party_members = build_party_members_from_save(
        save=session.state.save,
        jobs_by_name=session.state.jobs_by_name,
        weapons=session.state.weapons,
        armors=session.state.armors,
        level_table=session.level_table,
    )
    for member in session.party_members:
        hp = hp_by_name.get(member.name)
        if hp is not None:
            member.state.hp = max(0, min(hp, int(member.state.max_hp or hp)))

    session.party_magic_info = build_party_magic_info(session.state)
    session.party_magic_lists = build_party_magic_lists(session.state)
    setattr(session, "menu_magic_setup", None)


def _persist_menu_magic_setup_to_save(
    session: BattleSession, setup: dict[str, Any]
) -> None:
    save = getattr(getattr(session, "state", None), "save", None)
    if not isinstance(save, dict):
        return
    party = save.get("party")
    equipped = setup.get("equipped_by_member", [])
    if not isinstance(party, list) or not isinstance(equipped, list):
        return

    for idx, entry in enumerate(party):
        if not isinstance(entry, dict) or idx >= len(equipped):
            continue
        member_rows = equipped[idx] if isinstance(equipped[idx], dict) else {}
        slots_by_level: dict[int, list[str | None]] = {}
        for lv in range(1, 9):
            raw_row = member_rows.get(str(lv)) or [None, None, None]
            row: list[str | None] = []
            if isinstance(raw_row, list):
                for slot_value in raw_row[:3]:
                    row.append(slot_value if isinstance(slot_value, str) else None)
            while len(row) < 3:
                row.append(None)
            slots_by_level[lv] = row
        dump_equipped_magic_slots_to_entry(entry, slots_by_level)


def _require_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise InputValidationError(f"{key} must be int")
    return value


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise InputValidationError(f"{key} must be non-empty string")
    return value


def _magic_type_prefix(magic_type: Any) -> str:
    raw_label = getattr(magic_type, "value", magic_type)
    label = str(raw_label or "").strip()
    if label == "Black Magic":
        return "●"
    if label == "White Magic":
        return "〇"
    if label == "Summon Magic":
        return "◎"
    return ""


def _format_magic_candidate_label(*, spell_name: str, magic_type: Any) -> str:
    prefix = _magic_type_prefix(magic_type)
    return f"{prefix}{spell_name}"


def _build_magic_command_candidates_by_member(
    session: BattleSession,
) -> list[list[dict[str, Any]]]:
    candidates: list[list[dict[str, Any]]] = []
    party_magic_lists = getattr(session, "party_magic_lists", [])
    party_members = list(getattr(session, "party_members", []))
    for member_idx, row in enumerate(party_magic_lists):
        member = party_members[member_idx] if member_idx < len(party_members) else None
        state = getattr(member, "state", None)
        mp_pool = getattr(state, "mp_pool", {}) if state is not None else {}
        max_mp_pool = getattr(state, "max_mp_pool", {}) if state is not None else {}
        if not isinstance(mp_pool, dict):
            mp_pool = {}
        if not isinstance(max_mp_pool, dict):
            max_mp_pool = {}

        names: list[dict[str, Any]] = []
        for cand in row or []:
            if not isinstance(cand, (list, tuple)) or len(cand) < 3:
                continue
            name = cand[0]
            if not isinstance(name, str) or not name:
                continue
            magic_type = cand[1]
            level = max(1, _safe_int(cand[2], 1))
            remain = _safe_int(mp_pool.get(level, 0), 0)
            max_uses = _safe_int(max_mp_pool.get(level, remain), remain)
            names.append(
                {
                    "name": name,
                    "type": str(getattr(magic_type, "value", magic_type)),
                    "level": level,
                    "remaining_uses": remain,
                    "max_uses": max_uses,
                    "label": _format_magic_candidate_label(
                        spell_name=name,
                        magic_type=magic_type,
                    ),
                    "group_label": (
                        f"LV{level} ({remain}/{max_uses})"
                        if max_uses > 0
                        else f"LV{level} ({remain})"
                    ),
                }
            )
        candidates.append(names)
    return candidates


def _build_magic_spell_meta(session: BattleSession) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for name, raw in getattr(session, "spells_expanded", {}).items():
        if not isinstance(name, str) or not name:
            continue
        if not isinstance(raw, dict):
            continue
        target_norm = normalize_text_basic(raw.get("Target") or "")
        can_select_all = target_norm in {"one/all enemies", "one/all allies", "one/all"}
        auto_all_target = target_norm in {"all enemies", "all allies"}
        healing_type = str(healing_spell_kind(raw) or "")
        target_mode = "enemy_only"
        if healing_type in {"hp", "status", "revive", "protect", "haste", "reflect"}:
            target_mode = "any" if healing_type == "hp" else "ally_only"
        rows[name] = {
            "target": str(raw.get("Target") or ""),
            "target_norm": target_norm,
            "can_select_all": can_select_all,
            "auto_all_target": auto_all_target,
            "healing_type": healing_type,
            "target_mode": target_mode,
            "type": str(raw.get("Type") or ""),
            "level": _safe_int(raw.get("Level", 1), 1),
        }
    return rows


def _ensure_menu_magic_setup(session: BattleSession) -> dict[str, Any]:
    existing = getattr(session, "menu_magic_setup", None)
    if isinstance(existing, dict):
        return existing

    spell_meta = _build_magic_spell_meta(session)
    save = getattr(getattr(session, "state", None), "save", {})
    stock_by_level = build_magic_stock_by_level(save, spell_meta)
    equipped_by_member: list[dict[str, list[str | None]]] = []
    has_equipped_magic = False
    for entry in save.get("party", []) if isinstance(save, dict) else []:
        if not isinstance(entry, dict):
            continue
        slots = load_equipped_magic_slots_from_entry(entry)
        if any(spell_name for row in slots.values() for spell_name in row):
            has_equipped_magic = True
        equipped_by_member.append({str(lv): list(slots[lv]) for lv in range(1, 9)})

    if not has_equipped_magic and not any(
        stock_by_level.get(str(lv)) for lv in range(1, 9)
    ):
        slots_by_level: dict[str, list[tuple[int, str]]] = {
            str(lv): [] for lv in range(1, 9)
        }
        for name, info in spell_meta.items():
            level = _safe_int(info.get("level", 1), 1)
            level = max(1, min(8, level))
            magic_type = str(info.get("type") or "")
            if "Black" in magic_type:
                type_order = 0
            elif "White" in magic_type:
                type_order = 1
            elif "Summon" in magic_type:
                type_order = 2
            else:
                continue
            slots_by_level[str(level)].append((type_order, name))
        for lv in range(1, 9):
            grouped = sorted(slots_by_level[str(lv)], key=lambda row: (row[0], row[1]))
            black = [name for typ, name in grouped if typ == 0][:3]
            white = [name for typ, name in grouped if typ == 1][:3]
            summon = [name for typ, name in grouped if typ == 2][:1]
            stock_by_level[str(lv)] = black + white + summon

    setup = {
        "stock_by_level": stock_by_level,
        "equipped_by_member": equipped_by_member,
    }
    setattr(session, "menu_magic_setup", setup)
    return setup


def _build_battle_commands_by_member(
    session: BattleSession,
) -> list[list[dict[str, str]]]:
    candidates: list[list[dict[str, str]]] = []
    for member in session.party_members:
        member_candidates: list[dict[str, str]] = []
        job_raw = getattr(getattr(member, "job", None), "raw", {})
        if isinstance(job_raw, dict):
            for i in range(1, 5):
                command_row = job_raw.get(f"BattleCommand{i}")
                if not isinstance(command_row, dict):
                    continue
                command = command_row.get("Command")
                if not isinstance(command, str) or not command.strip():
                    continue
                command_name = command.strip()
                member_candidates.append(
                    {
                        "command": command_name,
                        "kind": normalize_battle_command(command_name),
                    }
                )

        if not member_candidates:
            fallback = ["Fight", "Defend", "Item", "Run"]
            member_candidates = [
                {"command": cmd, "kind": normalize_battle_command(cmd)}
                for cmd in fallback
            ]
        candidates.append(member_candidates)
    return candidates


def _build_member_progress_snapshot(member: Any) -> dict[str, Any]:
    base = getattr(member, "base", None)
    return {
        "name": str(getattr(member, "name", "")),
        "level": _safe_int(getattr(base, "level", 0), 0),
        "exp": _safe_int(getattr(base, "total_exp", 0), 0),
        "job_level": _safe_int(getattr(base, "job_level", 0), 0),
        "job_skill_point": _safe_int(getattr(base, "job_skill_point", 0), 0),
    }


def _build_party_progress_snapshot(session: BattleSession) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for member in session.party_members:
        snap = _build_member_progress_snapshot(member)
        rows[snap["name"]] = snap
    return rows


def _build_resource_progress_snapshot(session: BattleSession) -> dict[str, int]:
    save = getattr(getattr(session, "state", None), "save", None)
    if not isinstance(save, dict):
        return {"gil": 0, "cp": 0}
    return {
        "gil": _safe_int(save.get("gil", 0), 0),
        "cp": _safe_int(save.get("CP", 0), 0),
    }


def _format_victory_progress_logs(
    *,
    before_progress: dict[str, dict[str, Any]],
    after_progress: dict[str, dict[str, Any]],
    before_resources: dict[str, int],
    after_resources: dict[str, int],
    rewards: dict[str, Any],
) -> list[str]:
    lines: list[str] = ["=== Battle Rewards ==="]
    lines.append(f"EXP +{_safe_int(rewards.get('gained_exp', 0), 0)}")
    gil_before = _safe_int(before_resources.get("gil", 0), 0)
    gil_after = _safe_int(after_resources.get("gil", gil_before), gil_before)
    cp_before = _safe_int(before_resources.get("cp", 0), 0)
    cp_after = _safe_int(after_resources.get("cp", cp_before), cp_before)
    lines.append(
        f"Gil +{_safe_int(rewards.get('gained_gil', 0), 0)} ({gil_before} -> {gil_after})"
    )
    lines.append(
        f"CP +{_safe_int(rewards.get('gained_cp', 0), 0)} ({cp_before} -> {cp_after})"
    )

    for name, after in after_progress.items():
        before = before_progress.get(name, {})

        level_before = _safe_int(before.get("level", after.get("level", 0)), 0)
        level_after = _safe_int(after.get("level", level_before), level_before)
        exp_before = _safe_int(before.get("exp", after.get("exp", 0)), 0)
        exp_after = _safe_int(after.get("exp", exp_before), exp_before)
        if level_after != level_before:
            lines.append(f"{name}: Level {level_before} -> {level_after}")
        if exp_after != exp_before:
            lines.append(f"{name}: EXP {exp_before} -> {exp_after}")

        job_before = _safe_int(before.get("job_level", after.get("job_level", 0)), 0)
        job_after = _safe_int(after.get("job_level", job_before), job_before)
        sp_before = _safe_int(
            before.get("job_skill_point", after.get("job_skill_point", 0)),
            0,
        )
        sp_after = _safe_int(after.get("job_skill_point", sp_before), sp_before)
        sp_delta = sp_after - sp_before

        if job_after != job_before:
            lines.append(
                f"{name}: Job Lv {job_before} -> {job_after} (SP {sp_before} -> {sp_after}, +{sp_delta})"
            )
        elif sp_delta > 0:
            lines.append(f"{name}: Skill Point +{sp_delta} ({sp_before} -> {sp_after})")

    dropped = rewards.get("dropped_item", [])
    if isinstance(dropped, list) and dropped:
        lines.append("Drop: " + ", ".join(str(x) for x in dropped))

    return lines


def _build_special_command_candidates(session: BattleSession) -> list[str]:
    candidates: list[str] = []
    for member in session.party_members:
        job_raw = getattr(getattr(member, "job", None), "raw", {})
        if not isinstance(job_raw, dict):
            continue
        for i in range(1, 11):
            command_row = job_raw.get(f"BattleCommand{i}")
            if not isinstance(command_row, dict):
                continue
            command = command_row.get("Command")
            if not isinstance(command, str) or not command:
                continue
            if normalize_battle_command(command) != "special":
                continue
            if command not in candidates:
                candidates.append(command)
    return candidates


def create_app(
    *,
    session: BattleSession | None = None,
    rng: Random | None = None,
    enemy_names: Sequence[str] | None = None,
) -> Flask:
    template_dir = Path(__file__).resolve().parents[1] / "templates"
    app = Flask(__name__, template_folder=str(template_dir))
    register_flask_error_handlers(app)

    if session is not None:
        battle_session = session
        selection_context = {
            "groups": [],
            "selected_group": "",
            "selected_location": "",
            "selected_enemy_names": [e.get("name", "") for e in []],
            "enabled": False,
        }
    else:
        state = init_runtime_state()
        explicit_groups = load_explicit_groups("assets/data/explicit_groups.json")
        location_entries = build_location_index(state.monsters)
        location_groups = build_groups(
            location_entries, explicit_groups=explicit_groups
        )

        groups_payload: list[dict[str, Any]] = []
        location_to_entry: dict[str, Any] = {}
        for group in location_groups:
            locations = []
            for child in group.children:
                locations.append(child.location)
                location_to_entry[child.location] = child
            groups_payload.append(
                {"group_name": group.group_name, "locations": locations}
            )

        initial_group = groups_payload[0]["group_name"] if groups_payload else ""
        initial_location = (
            groups_payload[0]["locations"][0]
            if groups_payload and groups_payload[0]["locations"]
            else ""
        )
        initial_entry = location_to_entry.get(initial_location)
        selected_enemy_names = (
            pick_enemy_names(initial_entry, state.monsters, k_min=2, k_max=6)
            if initial_entry
            else sorted(state.monsters.keys())[:3]
        )
        battle_session = build_battle_session(
            state=state, enemy_names=selected_enemy_names
        )

        selection_context = {
            "groups": groups_payload,
            "selected_group": initial_group,
            "selected_location": initial_location,
            "selected_enemy_names": selected_enemy_names,
            "enabled": True,
            "state": state,
            "location_to_entry": location_to_entry,
        }

    round_rng = rng or Random()
    job_attr: dict[str, dict[str, int]] | None = None
    try:
        job_attr = load_job_attribution("assets/data/job_attribution.csv")
    except OSError:
        job_attr = None

    battle_start_progress = _build_party_progress_snapshot(battle_session)
    battle_start_resources = _build_resource_progress_snapshot(battle_session)

    @app.get("/")
    def index():
        nonlocal battle_session, battle_start_progress, battle_start_resources
        if selection_context.get("enabled"):
            selected_group = request.args.get(
                "location_group", selection_context["selected_group"]
            )
            selected_location = request.args.get(
                "location", selection_context["selected_location"]
            )

            groups = selection_context["groups"]
            valid_group_names = {g["group_name"] for g in groups}
            if selected_group not in valid_group_names and groups:
                selected_group = groups[0]["group_name"]

            group_row = next(
                (g for g in groups if g["group_name"] == selected_group), None
            )
            valid_locations = set(group_row["locations"]) if group_row else set()
            if (
                selected_location not in valid_locations
                and group_row
                and group_row["locations"]
            ):
                selected_location = group_row["locations"][0]

            location_entry = selection_context["location_to_entry"].get(
                selected_location
            )
            if location_entry is not None:
                enemy_names_for_location = pick_enemy_names(
                    location_entry,
                    selection_context["state"].monsters,
                    k_min=2,
                    k_max=6,
                )
                if (
                    selected_group != selection_context["selected_group"]
                    or selected_location != selection_context["selected_location"]
                ):
                    battle_session = build_battle_session(
                        state=selection_context["state"],
                        enemy_names=enemy_names_for_location,
                    )
                    battle_start_progress = _build_party_progress_snapshot(
                        battle_session
                    )
                    battle_start_resources = _build_resource_progress_snapshot(
                        battle_session
                    )
                    selection_context["selected_enemy_names"] = enemy_names_for_location

            selection_context["selected_group"] = selected_group
            selection_context["selected_location"] = selected_location

        return render_template(
            "top.html",
            expected_action_count=len(battle_session.party_members),
            default_lifecycle="ready_for_actions",
            initial_session_status=_build_session_status_snapshot(battle_session),
            location_groups=selection_context["groups"],
            selected_location_group=selection_context["selected_group"],
            selected_location=selection_context["selected_location"],
            selected_enemy_names=selection_context.get("selected_enemy_names", []),
            battle_commands_by_member=_build_battle_commands_by_member(battle_session),
            magic_command_candidates_by_member=_build_magic_command_candidates_by_member(
                battle_session
            ),
            magic_spell_meta_by_name=_build_magic_spell_meta(battle_session),
            item_command_candidates=_build_battle_item_command_candidates(
                battle_session
            ),
            item_battle_meta_by_name=_build_battle_item_meta(
                battle_session.state.items_by_name
            ),
            special_command_candidates=_build_special_command_candidates(
                battle_session
            ),
        )

    @app.post("/battle/round")
    def post_battle_round():
        nonlocal battle_start_progress, battle_start_resources
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError(
                "request body must be JSON object",
                details={"actual": type(payload).__name__},
            )

        request_dto = parse_execute_round_input_dict(payload)
        request_dto = _normalize_planned_actions_length(
            request_dto,
            expected_count=len(battle_session.party_members),
        )
        output_dto = execute_round_dto(
            session=battle_session,
            request=request_dto,
            rng=round_rng,
        )
        response_payload = to_json_ready_dict(output_dto)

        if output_dto.end_reason == "enemy_defeated" and hasattr(
            battle_session, "level_table"
        ):
            rewards = apply_victory_rewards(
                party_members=battle_session.party_members,
                enemies=battle_session.enemies,
                state=battle_session.state,
                level_table=battle_session.level_table,
            )
            after_progress = _build_party_progress_snapshot(battle_session)
            after_resources = _build_resource_progress_snapshot(battle_session)
            rewards["gil_before"] = _safe_int(battle_start_resources.get("gil", 0), 0)
            rewards["gil_after"] = _safe_int(after_resources.get("gil", 0), 0)
            rewards["cp_before"] = _safe_int(battle_start_resources.get("cp", 0), 0)
            rewards["cp_after"] = _safe_int(after_resources.get("cp", 0), 0)
            response_payload["logs"] = list(
                response_payload.get("logs", [])
            ) + _format_victory_progress_logs(
                before_progress=battle_start_progress,
                after_progress=after_progress,
                before_resources=battle_start_resources,
                after_resources=after_resources,
                rewards=rewards,
            )
            response_payload["victory_rewards"] = rewards
        response_payload["session_status"] = _build_session_status_snapshot(
            battle_session
        )
        response_payload["selected_location_group"] = selection_context.get(
            "selected_group", ""
        )
        response_payload["selected_location"] = selection_context.get(
            "selected_location", ""
        )
        if output_dto.lifecycle.battle_finished:
            battle_start_progress = _build_party_progress_snapshot(battle_session)
            battle_start_resources = _build_resource_progress_snapshot(battle_session)
        return jsonify(response_payload), 200

    @app.get("/assets/enemy-sprites/<path:filename>")
    def get_enemy_sprite(filename: str):
        safe_name = Path(filename).name
        if not safe_name.lower().endswith(".png"):
            return jsonify({"error": "png only"}), 400
        sprite_dir = Path(__file__).resolve().parents[1] / "assets/images/enemy_sprites"
        return send_from_directory(str(sprite_dir), safe_name)

    @app.get("/assets/portraits/<string:portrait_key>")
    def get_portrait_image(portrait_key: str):
        safe_key = Path(portrait_key).name
        if not safe_key:
            return jsonify({"error": "portrait_key is required"}), 400

        base_dir = Path(__file__).resolve().parents[1] / "assets/images"
        candidates = [
            base_dir / "faces" / f"{safe_key}.jpg",
            base_dir / "faces" / f"{safe_key}.jpeg",
            base_dir / "faces" / f"{safe_key}.png",
            base_dir / f"{safe_key}.jpg",
            base_dir / f"{safe_key}.jpeg",
            base_dir / f"{safe_key}.png",
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return send_from_directory(str(candidate.parent), candidate.name)

        return jsonify({"error": "portrait not found"}), 404

    @app.get("/assets/ui/location-group-bg/<path:group_name>")
    def get_location_group_bg(group_name: str):
        safe_name = Path(group_name).name
        maps_dir = Path(__file__).resolve().parents[1] / "assets/images/maps"
        filename = _resolve_location_group_bg_filename(maps_dir, safe_name)
        if filename is not None:
            return send_from_directory(str(maps_dir), filename)

        return "", 404

    @app.get("/menu")
    def menu_page():
        return render_template(
            "menu.html",
            initial_menu_state=_build_menu_state_payload(
                battle_session, job_attr=job_attr
            ),
        )

    @app.get("/menu/item")
    def menu_item_page():
        return render_template(
            "menu_item.html",
            initial_menu_state=_build_menu_state_payload(
                battle_session, job_attr=job_attr
            ),
        )

    @app.get("/menu/magic")
    def menu_magic_page():
        return render_template(
            "menu_magic.html",
            initial_menu_state=_build_menu_state_payload(
                battle_session, job_attr=job_attr
            ),
            magic_spell_meta=_build_magic_spell_meta(battle_session),
        )

    @app.get("/menu/equip")
    def menu_equip_page():
        return render_template(
            "menu_equip.html",
            initial_menu_state=_build_menu_state_payload(
                battle_session, job_attr=job_attr
            ),
        )

    @app.get("/menu/status")
    def menu_status_page():
        return render_template(
            "menu_status.html",
            initial_menu_state=_build_menu_state_payload(
                battle_session, job_attr=job_attr
            ),
        )

    @app.get("/menu/job")
    def menu_job_page():
        return render_template(
            "menu_job.html",
            initial_menu_state=_build_menu_state_payload(
                battle_session, job_attr=job_attr
            ),
        )

    @app.get("/assets/status-icons/<path:filename>")
    def get_status_icon(filename: str):
        safe_name = Path(filename).name
        if not safe_name.lower().endswith(".png"):
            return jsonify({"error": "png only"}), 400
        icon_dir = Path(__file__).resolve().parents[1] / "assets/images/status_icons"
        return send_from_directory(str(icon_dir), safe_name)

    @app.get("/menu/state")
    def get_menu_state():
        return (
            jsonify(_build_menu_state_payload(battle_session, job_attr=job_attr)),
            200,
        )

    @app.post("/menu/use-item")
    def post_menu_use_item():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError("request body must be JSON object")

        user_index = _require_int(payload, "user_index")
        item_name = _require_str(payload, "item_name")
        target_index_raw = payload.get("target_index")
        target_index = target_index_raw if isinstance(target_index_raw, int) else None
        item_type = (
            payload.get("item_type")
            if isinstance(payload.get("item_type"), str)
            else None
        )

        use_item = make_use_field_item_fn(
            party=battle_session.party_members,
            items_by_name=battle_session.state.items_by_name,
            save_dict=battle_session.state.save,
        )
        ok = use_item(user_index, item_name, target_index, item_type)
        return (
            jsonify(
                {
                    "ok": ok,
                    "menu_state": _build_menu_state_payload(
                        battle_session, job_attr=job_attr
                    ),
                }
            ),
            200,
        )

    @app.post("/menu/cast-magic")
    def post_menu_cast_magic():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError("request body must be JSON object")

        caster_index = _require_int(payload, "caster_index")
        spell_name = _require_str(payload, "spell_name")
        target_index_raw = payload.get("target_index")
        target_index = target_index_raw if isinstance(target_index_raw, int) else None

        def _build_magic_fn(member_index: int) -> list[tuple[str, int, int]]:
            rows = battle_session.party_magic_lists[member_index] or []
            return [(str(name), int(level), 1) for (name, _magic_type, level) in rows]

        cast_magic = make_cast_field_magic_fn(
            party=battle_session.party_members,
            spells_by_name=battle_session.spells_expanded,
            build_magic_fn=_build_magic_fn,
            save_dict=battle_session.state.save,
        )
        ok = cast_magic(caster_index, spell_name, target_index)
        return (
            jsonify(
                {
                    "ok": ok,
                    "menu_state": _build_menu_state_payload(
                        battle_session, job_attr=job_attr
                    ),
                }
            ),
            200,
        )

    @app.post("/menu/magic/learn")
    def post_menu_magic_learn():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError("request body must be JSON object")

        member_index = _require_int(payload, "member_index")
        level = _require_int(payload, "level")
        slot_index = _require_int(payload, "slot_index")
        spell_name = _require_str(payload, "spell_name")

        setup = _ensure_menu_magic_setup(battle_session)
        stock = setup.get("stock_by_level", {})
        equipped = setup.get("equipped_by_member", [])

        if member_index < 0 or member_index >= len(equipped):
            raise InputValidationError("member_index out of range")
        if level < 1 or level > 8:
            raise InputValidationError("level out of range")
        if slot_index < 0 or slot_index > 2:
            raise InputValidationError("slot_index out of range")

        lv_key = str(level)
        stock_row = stock.get(lv_key, [])
        if spell_name not in stock_row:
            raise InputValidationError("spell_name is not in stock")

        row = equipped[member_index].get(lv_key, [None, None, None])
        old = row[slot_index]
        if isinstance(old, str) and old:
            stock_row.append(old)
        row[slot_index] = spell_name
        if spell_name in stock_row:
            stock_row.remove(spell_name)
        equipped[member_index][lv_key] = row
        stock[lv_key] = sorted(stock_row)
        _persist_menu_magic_setup_to_save(battle_session, setup)
        _refresh_session_party(battle_session)

        return (
            jsonify(
                {
                    "ok": True,
                    "menu_state": _build_menu_state_payload(
                        battle_session, job_attr=job_attr
                    ),
                }
            ),
            200,
        )

    @app.post("/menu/magic/remove")
    def post_menu_magic_remove():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError("request body must be JSON object")

        member_index = _require_int(payload, "member_index")
        level = _require_int(payload, "level")
        slot_index = _require_int(payload, "slot_index")

        setup = _ensure_menu_magic_setup(battle_session)
        stock = setup.get("stock_by_level", {})
        equipped = setup.get("equipped_by_member", [])

        if member_index < 0 or member_index >= len(equipped):
            raise InputValidationError("member_index out of range")
        if level < 1 or level > 8:
            raise InputValidationError("level out of range")
        if slot_index < 0 or slot_index > 2:
            raise InputValidationError("slot_index out of range")

        lv_key = str(level)
        row = equipped[member_index].get(lv_key, [None, None, None])
        old = row[slot_index]
        if not isinstance(old, str) or not old:
            return (
                jsonify(
                    {
                        "ok": False,
                        "menu_state": _build_menu_state_payload(
                            battle_session, job_attr=job_attr
                        ),
                    }
                ),
                200,
            )
        row[slot_index] = None
        equipped[member_index][lv_key] = row
        stock_row = stock.get(lv_key, [])
        stock_row.append(old)
        stock[lv_key] = sorted(stock_row)
        _persist_menu_magic_setup_to_save(battle_session, setup)
        _refresh_session_party(battle_session)

        return (
            jsonify(
                {
                    "ok": True,
                    "menu_state": _build_menu_state_payload(
                        battle_session, job_attr=job_attr
                    ),
                }
            ),
            200,
        )

    @app.post("/menu/magic/swap")
    def post_menu_magic_swap():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError("request body must be JSON object")

        from_member_index = _require_int(payload, "from_member_index")
        to_member_index = _require_int(payload, "to_member_index")
        level = _require_int(payload, "level")
        slot_index = _require_int(payload, "slot_index")

        setup = _ensure_menu_magic_setup(battle_session)
        equipped = setup.get("equipped_by_member", [])

        if from_member_index < 0 or from_member_index >= len(equipped):
            raise InputValidationError("from_member_index out of range")
        if to_member_index < 0 or to_member_index >= len(equipped):
            raise InputValidationError("to_member_index out of range")
        if level < 1 or level > 8:
            raise InputValidationError("level out of range")
        if slot_index < 0 or slot_index > 2:
            raise InputValidationError("slot_index out of range")

        lv_key = str(level)
        row_a = equipped[from_member_index].get(lv_key, [None, None, None])
        row_b = equipped[to_member_index].get(lv_key, [None, None, None])
        row_a[slot_index], row_b[slot_index] = row_b[slot_index], row_a[slot_index]
        equipped[from_member_index][lv_key] = row_a
        equipped[to_member_index][lv_key] = row_b
        _persist_menu_magic_setup_to_save(battle_session, setup)
        _refresh_session_party(battle_session)

        return (
            jsonify(
                {
                    "ok": True,
                    "menu_state": _build_menu_state_payload(
                        battle_session, job_attr=job_attr
                    ),
                }
            ),
            200,
        )

    @app.post("/menu/magic/use")
    def post_menu_magic_use():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError("request body must be JSON object")

        caster_index = _require_int(payload, "caster_index")
        level = _require_int(payload, "level")
        slot_index = _require_int(payload, "slot_index")
        target_index = _require_int(payload, "target_index")

        setup = _ensure_menu_magic_setup(battle_session)
        equipped = setup.get("equipped_by_member", [])

        if caster_index < 0 or caster_index >= len(equipped):
            raise InputValidationError("caster_index out of range")
        if level < 1 or level > 8:
            raise InputValidationError("level out of range")
        if slot_index < 0 or slot_index > 2:
            raise InputValidationError("slot_index out of range")
        if target_index < 0 or target_index >= len(battle_session.party_members):
            raise InputValidationError("target_index out of range")

        lv_key = str(level)
        row = equipped[caster_index].get(lv_key, [None, None, None])
        spell_name = row[slot_index]
        if not isinstance(spell_name, str) or not spell_name:
            return (
                jsonify(
                    {
                        "ok": False,
                        "menu_state": _build_menu_state_payload(
                            battle_session, job_attr=job_attr
                        ),
                    }
                ),
                200,
            )

        def _build_magic_fn(member_index: int) -> list[tuple[str, int, int]]:
            member_rows = equipped[member_index]
            out: list[tuple[str, int, int]] = []
            for lv in range(1, 9):
                spells = member_rows.get(str(lv), [None, None, None])
                for slot_spell in spells:
                    if isinstance(slot_spell, str) and slot_spell:
                        out.append((slot_spell, lv, 1))
            return out

        cast_magic = make_cast_field_magic_fn(
            party=battle_session.party_members,
            spells_by_name=battle_session.spells_expanded,
            build_magic_fn=_build_magic_fn,
            save_dict=battle_session.state.save,
        )

        ok = cast_magic(caster_index, spell_name, target_index)
        return (
            jsonify(
                {
                    "ok": ok,
                    "menu_state": _build_menu_state_payload(
                        battle_session, job_attr=job_attr
                    ),
                }
            ),
            200,
        )

    @app.post("/menu/change-equipment")
    def post_menu_change_equipment():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError("request body must be JSON object")

        member_index = _require_int(payload, "member_index")
        slot = _require_str(payload, "slot")
        item_name_raw = payload.get("item_name")
        item_name = (
            item_name_raw if isinstance(item_name_raw, str) and item_name_raw else None
        )

        if member_index < 0 or member_index >= len(battle_session.party_members):
            raise InputValidationError("member_index out of range")
        if slot not in {"main_hand", "off_hand", "head", "body", "arms"}:
            raise InputValidationError("slot is invalid")

        member = battle_session.party_members[member_index]
        before_equipment = deepcopy(
            member.equipment if member.equipment is not None else EquipmentSet()
        )
        next_equipment = deepcopy(before_equipment)
        setattr(next_equipment, slot, item_name)
        next_equipment, _removed_logs = apply_job_equipment_restrictions(
            next_equipment, member.job
        )
        _apply_equipment_inventory_delta(
            battle_session,
            before=before_equipment,
            after=next_equipment,
        )
        member.equipment = next_equipment
        member.stats = compute_character_final_stats(
            member.base,
            member.equipment,
            battle_session.state.weapons,
            battle_session.state.armors,
            job_name=member.job.name,
        )
        sync_equipment_to_save(member, battle_session.state.save)
        return (
            jsonify(
                {
                    "ok": True,
                    "menu_state": _build_menu_state_payload(
                        battle_session, job_attr=job_attr
                    ),
                }
            ),
            200,
        )

    @app.post("/menu/unequip-all")
    def post_menu_unequip_all():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError("request body must be JSON object")

        member_index = _require_int(payload, "member_index")
        if member_index < 0 or member_index >= len(battle_session.party_members):
            raise InputValidationError("member_index out of range")

        member = battle_session.party_members[member_index]
        before_equipment = deepcopy(
            member.equipment if member.equipment is not None else EquipmentSet()
        )
        next_equipment = EquipmentSet()
        next_equipment, _removed_logs = apply_job_equipment_restrictions(
            next_equipment, member.job
        )
        _apply_equipment_inventory_delta(
            battle_session,
            before=before_equipment,
            after=next_equipment,
        )
        member.equipment = next_equipment
        member.stats = compute_character_final_stats(
            member.base,
            member.equipment,
            battle_session.state.weapons,
            battle_session.state.armors,
            job_name=member.job.name,
        )
        sync_equipment_to_save(member, battle_session.state.save)
        return (
            jsonify(
                {
                    "ok": True,
                    "menu_state": _build_menu_state_payload(
                        battle_session, job_attr=job_attr
                    ),
                }
            ),
            200,
        )

    @app.post("/menu/change-job")
    def post_menu_change_job():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError("request body must be JSON object")

        member_index = _require_int(payload, "member_index")
        job_name = _require_str(payload, "job_name")
        if member_index < 0 or member_index >= len(battle_session.party_members):
            raise InputValidationError("member_index out of range")
        if job_name not in battle_session.state.jobs_by_name:
            raise InputValidationError("job_name is invalid")

        member = battle_session.party_members[member_index]
        from_job = str(getattr(getattr(member, "job", None), "name", ""))
        to_job_level = _get_saved_job_level_for_member(
            battle_session.state,
            member_index,
            job_name,
        )
        required_cp = 0
        if isinstance(job_attr, dict) and from_job in job_attr and job_name in job_attr:
            required_cp = compute_job_change_cp_cost(
                from_job=from_job,
                to_job=job_name,
                to_job_level=to_job_level,
                job_attr=job_attr,
            )

        save = battle_session.state.save
        current_cp = _safe_int(save.get("CP", 0), 0)
        if current_cp < required_cp:
            return (
                jsonify(
                    {
                        "ok": False,
                        "reason": "not_enough_cp",
                        "required_cp": int(required_cp),
                        "current_cp": int(current_cp),
                        "menu_state": _build_menu_state_payload(
                            battle_session,
                            job_attr=job_attr,
                        ),
                    }
                ),
                200,
            )

        save["CP"] = max(0, current_cp - required_cp)
        party_entry = save["party"][member_index]
        party_entry["job"] = job_name
        _refresh_session_party(battle_session)
        return (
            jsonify(
                {
                    "ok": True,
                    "required_cp": int(required_cp),
                    "menu_state": _build_menu_state_payload(
                        battle_session,
                        job_attr=job_attr,
                    ),
                }
            ),
            200,
        )

    @app.post("/menu/reorder")
    def post_menu_reorder():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError("request body must be JSON object")
        order = payload.get("order")
        if not isinstance(order, list) or not all(isinstance(i, int) for i in order):
            raise InputValidationError("order must be list[int]")
        expected = list(range(len(battle_session.party_members)))
        if sorted(order) != expected:
            raise InputValidationError("order must be permutation of current indices")

        battle_session.party_members = [battle_session.party_members[i] for i in order]
        battle_session.state.save["party"] = [
            battle_session.state.save["party"][i] for i in order
        ]
        battle_session.party_magic_lists = [
            battle_session.party_magic_lists[i] for i in order
        ]
        battle_session.party_magic_info = [
            battle_session.party_magic_info[i] for i in order
        ]
        return (
            jsonify(
                {
                    "ok": True,
                    "menu_state": _build_menu_state_payload(
                        battle_session, job_attr=job_attr
                    ),
                }
            ),
            200,
        )

    @app.post("/menu/toggle-row")
    def post_menu_toggle_row():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError("request body must be JSON object")

        member_index = _require_int(payload, "member_index")
        if member_index < 0 or member_index >= len(battle_session.party_members):
            raise InputValidationError("member_index out of range")

        member = battle_session.party_members[member_index]
        current_row = str(getattr(member.base, "row", "front")).lower()
        next_row = "back" if current_row == "front" else "front"
        member.base.row = next_row
        if member.stats is not None:
            member.stats.row = next_row
        save_party = battle_session.state.save.get("party", [])
        if member_index < len(save_party) and isinstance(
            save_party[member_index], dict
        ):
            save_party[member_index]["row"] = next_row

        return (
            jsonify(
                {
                    "ok": True,
                    "member_index": member_index,
                    "row": next_row,
                    "menu_state": _build_menu_state_payload(
                        battle_session, job_attr=job_attr
                    ),
                }
            ),
            200,
        )

    @app.get("/menu/save/download")
    def get_menu_save_download():
        payload = json.dumps(
            battle_session.state.save, ensure_ascii=False, indent=2
        ).encode("utf-8")
        return send_file(
            io.BytesIO(payload),
            mimetype="application/json",
            as_attachment=True,
            download_name="ffiii_savedata.json",
        )

    @app.post("/menu/save")
    def post_menu_save():
        save_savedata(
            Path("assets/data/ffiii_savedata.json"), battle_session.state.save
        )
        return (
            jsonify(
                {
                    "ok": True,
                    "message": "セーブしました",
                    "download_url": "/menu/save/download",
                    "filename": "ffiii_savedata.json",
                }
            ),
            200,
        )

    return app


app = create_app()


def run_dev_server() -> None:
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_dev_server()
