# web_wasm/bootstrap_runtime.py
import json
from typing import Callable, SupportsIndex, SupportsInt, cast

from combat.wasm_api import WasmBattleEngine, build_session_status_snapshot
from combat.runtime_state import init_runtime_state
from combat.usecases import build_battle_session
from random import Random
from assets.data.data_loader import load_explicit_groups
from combat.enemy_selection import build_groups, build_location_index, pick_enemy_names
from system.cp_system import compute_job_change_cp_cost, load_job_attribution
from utils.name_normalize import normalize_name

state = init_runtime_state()

location_entries = build_location_index(state.monsters)
explicit_groups = {}
try:
    explicit_groups = load_explicit_groups("/tmp/explicit_groups.json")
except (OSError, ValueError):
    explicit_groups = {}
location_groups = build_groups(
    location_entries,
    explicit_groups=explicit_groups,
)
groups_payload = []
location_to_entry = {}
for group in location_groups:
    locations = []
    for child in group.children:
        locations.append(str(child.location))
        location_to_entry[str(child.location)] = child
    groups_payload.append(
        {
            "group_name": str(group.group_name),
            "locations": locations,
        }
    )

default_group = groups_payload[0]["group_name"] if groups_payload else ""
default_location = (
    groups_payload[0]["locations"][0]
    if groups_payload and groups_payload[0]["locations"]
    else ""
)

engine: WasmBattleEngine | None = None
try:
    job_attr = load_job_attribution("/assets/data/job_attribution.csv")
except Exception:
    job_attr = {}

_FIXED_PARTY_SLOT_KEYS = ["runeth", "arc", "refia", "ingus"]
_PARTY_ALIAS_MAP = {
    "luneth": "runeth",
}


def _merge_save_data(base, overlay):
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = {
            key: _merge_save_data(value, None)
            for key, value in base.items()
        }
        for key, value in overlay.items():
            merged[key] = _merge_save_data(base.get(key), value)
        return merged
    if isinstance(base, list) and isinstance(overlay, list):
        merged = []
        max_len = max(len(base), len(overlay))
        for idx in range(max_len):
            base_value = base[idx] if idx < len(base) else None
            overlay_value = overlay[idx] if idx < len(overlay) else None
            merged.append(_merge_save_data(base_value, overlay_value))
        return merged
    if overlay is None:
        if isinstance(base, dict):
            return {
                key: _merge_save_data(value, None)
                for key, value in base.items()
            }
        if isinstance(base, list):
            return [_merge_save_data(value, None) for value in base]
        return base
    if isinstance(overlay, dict):
        return {
            key: _merge_save_data(None, value)
            for key, value in overlay.items()
        }
    if isinstance(overlay, list):
        return [_merge_save_data(None, value) for value in overlay]
    return overlay


def _normalize_party_identity_key(raw):
    raw_text = str(raw or "").strip()
    if not raw_text:
        return ""
    key = raw_text
    if key.lower().startswith("ch_"):
        key = key[3:]
    key = normalize_name(
        key.replace(".png", "")
        .replace(".jpg", "")
        .replace(".jpeg", "")
        .replace(".webp", "")
    )
    return _PARTY_ALIAS_MAP.get(key, key)


def _party_entry_identity_keys(entry, fallback_index=-1):
    if not isinstance(entry, dict):
        return []
    keys = []
    for raw in (
        entry.get("portrait_key"),
        entry.get("image_name"),
        entry.get("name"),
    ):
        key = _normalize_party_identity_key(raw)
        if key and key not in keys:
            keys.append(key)
    slot_index = _safe_int(entry.get("index", fallback_index), fallback_index)
    if 0 <= slot_index < len(_FIXED_PARTY_SLOT_KEYS):
        slot_key = _FIXED_PARTY_SLOT_KEYS[slot_index]
        if slot_key not in keys:
            keys.append(slot_key)
    return keys


def _job_level_rows(entry):
    rows = entry.get("job_levels") if isinstance(entry, dict) else None
    return rows if isinstance(rows, dict) else {}


def _highest_job_level_name(job_levels):
    best_name = ""
    best_level = -1
    for job_name, row in job_levels.items():
        if not isinstance(job_name, str) or not job_name:
            continue
        if isinstance(row, dict):
            level = _safe_int(row.get("level", 0), 0)
        else:
            level = _safe_int(row, 0)
        if level > best_level:
            best_name = job_name
            best_level = level
    return best_name


def _repair_party_entry_job(entry, base_entry=None):
    if not isinstance(entry, dict):
        return entry
    job_levels = _job_level_rows(entry)
    current_job = str(entry.get("job") or "").strip()
    if current_job and (not job_levels or current_job in job_levels):
        return entry

    base_job = str(base_entry.get("job") or "").strip() if isinstance(base_entry, dict) else ""
    if base_job and (not job_levels or base_job in job_levels):
        entry["job"] = base_job
        return entry

    highest_job = _highest_job_level_name(job_levels)
    if highest_job:
        entry["job"] = highest_job
    return entry


def _align_party_to_base(base_party, overlay_party):
    if not isinstance(overlay_party, list):
        return overlay_party
    if not isinstance(base_party, list) or not base_party:
        return [
            {
                **entry,
                "index": idx,
            }
            if isinstance(entry, dict)
            else entry
            for idx, entry in enumerate(overlay_party)
        ]

    unused = set(range(len(overlay_party)))
    aligned = []
    for slot_index, base_entry in enumerate(base_party):
        base_keys = set(_party_entry_identity_keys(base_entry, slot_index))
        match_idx = None
        for idx in list(unused):
            overlay_entry = overlay_party[idx]
            overlay_keys = set(_party_entry_identity_keys(overlay_entry, idx))
            if base_keys & overlay_keys:
                match_idx = idx
                break
        if match_idx is None and slot_index in unused:
            match_idx = slot_index
        if match_idx is None and unused:
            match_idx = min(unused)
        if match_idx is None:
            continue
        unused.discard(match_idx)
        overlay_entry = overlay_party[match_idx]
        merged_entry = _merge_save_data(base_entry, overlay_entry)
        if isinstance(merged_entry, dict):
            merged_entry["index"] = slot_index
            if isinstance(base_entry, dict):
                if base_entry.get("name"):
                    merged_entry["name"] = base_entry.get("name")
                if isinstance(base_entry.get("job_levels"), dict):
                    merged_entry["job_levels"] = _merge_save_data(
                        base_entry.get("job_levels"),
                        merged_entry.get("job_levels"),
                    )
                if base_entry.get("portrait_key") is not None:
                    merged_entry["portrait_key"] = base_entry.get("portrait_key")
                if base_entry.get("image_name") is not None:
                    merged_entry["image_name"] = base_entry.get("image_name")
            merged_entry = _repair_party_entry_job(merged_entry, base_entry)
        aligned.append(merged_entry)

    for idx in sorted(unused):
        overlay_entry = overlay_party[idx]
        if isinstance(overlay_entry, dict):
            extra = dict(overlay_entry)
            extra["index"] = len(aligned)
            aligned.append(extra)
        else:
            aligned.append(overlay_entry)
    return aligned


def _mp_from_mp_levels(entry):
    if not isinstance(entry, dict):
        return None
    mp_levels = entry.get("mp_levels")
    if not isinstance(mp_levels, dict):
        return None
    mp = {}
    has_value = False
    for level in range(1, 9):
        row = mp_levels.get(str(level))
        current = None
        if isinstance(row, dict):
            current = row.get("current")
        if current is None:
            continue
        mp[f"L{level}MP"] = _safe_int(current, 0)
        has_value = True
    return mp if has_value else None


def _normalize_loaded_save(save_data):
    if not isinstance(save_data, dict):
        return save_data
    normalized = _merge_save_data(None, save_data)
    party = normalized.get("party")
    if not isinstance(party, list):
        return normalized
    for entry in party:
        if not isinstance(entry, dict):
            continue
        derived_mp = _mp_from_mp_levels(entry)
        if isinstance(derived_mp, dict):
            entry["mp"] = derived_mp
    return normalized


def get_location_selection_json():
    payload = {
        "groups": groups_payload,
        "selected_group": default_group,
        "selected_location": default_location,
    }
    return json.dumps(payload, ensure_ascii=False)


def boot_engine_for_location(location_group, location, seed=7):
    selected_group = str(location_group or "")
    selected_location = str(location or "")
    entry = location_to_entry.get(selected_location)
    if entry is None:
        enemy_names = sorted(state.monsters.keys())[:3]
    else:
        enemy_names = pick_enemy_names(entry, state.monsters, k_min=2, k_max=6)

    create_from_state = cast(
        Callable[..., WasmBattleEngine] | None,
        getattr(WasmBattleEngine, "create_from_state", None),
    )
    if create_from_state is not None:
        created_engine: WasmBattleEngine = create_from_state(
            state=state,
            enemy_names=enemy_names,
            seed=seed,
            selected_location_group=selected_group,
            selected_location=selected_location,
        )
    else:
        # python_bundle.zip 側が古く create_from_state を持たない場合の互換フォールバック
        session = build_battle_session(state=state, enemy_names=enemy_names)
        created_engine = WasmBattleEngine(
            session=session,
            rng=Random(seed),
            selected_location_group=selected_group,
            selected_location=selected_location,
            battle_start_progress=None,
        )

    globals()["engine"] = created_engine
    created_engine.full_recover_party_payload()
    return json.dumps(created_engine.build_initial_payload(), ensure_ascii=False)


def get_initial_payload_json():
    runtime_engine = engine if isinstance(engine, WasmBattleEngine) else None
    if runtime_engine is None:
        return json.dumps({}, ensure_ascii=False)
    return json.dumps(runtime_engine.build_initial_payload(), ensure_ascii=False)


def _saved_job_level(save_entry, job_name):
    if not isinstance(save_entry, dict):
        return 1
    job_levels = save_entry.get("job_levels")
    if not isinstance(job_levels, dict):
        return 1
    row = job_levels.get(job_name)
    if isinstance(row, dict):
        raw = row.get("level", 1)
    else:
        raw = row
    return max(1, _safe_int(raw, 1))


def _safe_int(value: object, default: int = 0) -> int:
    candidate: SupportsInt | SupportsIndex | str | bytes | bytearray
    if isinstance(value, (str, bytes, bytearray)):
        candidate = value
    elif isinstance(value, (SupportsInt, SupportsIndex)):
        candidate = value
    else:
        return default

    try:
        return int(candidate)
    except (TypeError, ValueError, OverflowError):
        return default


def _canon_job_code(text):
    t = str(text or "").strip()
    if not t:
        return ""
    return t.replace(" ", "").replace("_", "").replace("-", "").lower()


JOB_NAME_TO_CODE = {
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


def _actor_job_code(member):
    slug = str(getattr(getattr(member, "job", None), "slug", "") or "").strip()
    if slug and len(slug) <= 3:
        return slug
    job_name = str(getattr(getattr(member, "job", None), "name", "") or "").strip()
    if job_name in JOB_NAME_TO_CODE:
        return JOB_NAME_TO_CODE[job_name]
    return job_name


def _item_allowed_for_member(member, item_raw):
    equipped_by = item_raw.get("EquippedBy") if isinstance(item_raw, dict) else None
    if not isinstance(equipped_by, list) or not equipped_by:
        return True
    allow = {_canon_job_code(code) for code in equipped_by}
    current_job = _canon_job_code(_actor_job_code(member))
    return current_job in allow if current_job else True


def _is_two_handed_weapon(item_raw):
    if not isinstance(item_raw, dict):
        return False
    if "Two-Handed" in item_raw:
        return True
    hands = item_raw.get("Hands")
    if isinstance(hands, int):
        return hands >= 2
    if isinstance(hands, str) and hands.isdigit():
        return int(hands) >= 2
    return bool(item_raw.get("TwoHanded"))


def _compact_bonus_label(bonus_raw):
    if not isinstance(bonus_raw, dict) or not bonus_raw:
        return ""

    key_map = {
        "Strength": "STR",
        "Agility": "AGI",
        "Vitality": "VIT",
        "Intelligence": "INT",
        "Mind": "MND",
        "Fire": "FIR",
        "Ice": "ICE",
        "Lightning": "LIT",
        "Earth": "ERT",
        "Air": "AIR",
        "Holy": "HLY",
    }
    parts = []
    for key, value in bonus_raw.items():
        short = key_map.get(str(key), str(key)[:3].upper())
        if isinstance(value, str) and value.strip().lower() == "up":
            parts.append(f"{short}↑")
            continue
        amount = _safe_int(value, 0)
        if amount == 0:
            continue
        parts.append(f"{short}{amount:+d}")

    return f"BON:{'/'.join(parts)}" if parts else ""


def _build_equip_candidates_by_member(session):
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

    def _stock_count(item_type, item_name):
        bucket = weapon_stock if item_type == "Weapon" else armor_stock
        bucket_norm = weapon_stock_norm if item_type == "Weapon" else armor_stock_norm
        exact = _safe_int(bucket.get(item_name, 0), 0) if isinstance(bucket, dict) else 0
        if exact > 0:
            return exact
        return _safe_int(bucket_norm.get(normalize_name(item_name), 0), 0)

    out = []
    slot_to_armor_type = {"head": "Helm", "body": "Armor", "arms": "Gloves"}

    for member in getattr(session, "party_members", []):
        by_slot = {}
        for slot in ("main_hand", "off_hand"):
            rows = [{"kind": "none", "name": None}]
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
                        "atk": _safe_int(
                            raw.get("BasePower", raw.get("AttackPower", 0)), 0
                        ),
                        "acc": _safe_int(
                            (
                                round(
                                    float(
                                        raw.get("BaseAccuracy", raw.get("HitRate", 0))
                                        or 0
                                    )
                                    * 100
                                )
                                if raw.get("BaseAccuracy", None) is not None
                                else raw.get("HitRate", 0)
                            ),
                            0,
                        ),
                        "bonus_label": _compact_bonus_label(raw.get("Bonus")),
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
                            "eva": _safe_int(
                                (
                                    round(
                                        float(
                                            raw.get(
                                                "Evasion", raw.get("EvasionPenalty", 0)
                                            )
                                            or 0
                                        )
                                        * 100
                                    )
                                    if raw.get("Evasion", None) is not None
                                    else raw.get("EvasionPenalty", 0)
                                ),
                                0,
                            ),
                            "bonus_label": _compact_bonus_label(raw.get("Bonus")),
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
                        "eva": _safe_int(
                            (
                                round(
                                    float(
                                        raw.get("Evasion", raw.get("EvasionPenalty", 0))
                                        or 0
                                    )
                                    * 100
                                )
                                if raw.get("Evasion", None) is not None
                                else raw.get("EvasionPenalty", 0)
                            ),
                            0,
                            ),
                        "bonus_label": _compact_bonus_label(raw.get("Bonus")),
                    }
                )
            by_slot[slot] = rows
        out.append(by_slot)
    return out


def _build_magic_spell_meta(session):
    rows = {}
    for name, raw in getattr(session, "spells_expanded", {}).items():
        if not isinstance(name, str) or not name:
            continue
        if not isinstance(raw, dict):
            continue
        rows[name] = {
            "type": str(raw.get("Type") or ""),
            "level": _safe_int(raw.get("Level", 1), 1),
        }
    return rows


def _load_equipped_magic_slots_from_entry(party_entry):
    raw_magic = {}
    if isinstance(party_entry, dict):
        for key in ("Magic", "magic"):
            if isinstance(party_entry.get(key), dict):
                raw_magic = cast(dict[str, object], party_entry.get(key))
                break
    out = {lv: [None, None, None] for lv in range(1, 9)}
    for lv in range(1, 9):
        raw_row = raw_magic.get(f"LV{lv}")
        if isinstance(raw_row, list):
            row = []
            for name in raw_row[:3]:
                row.append(name if isinstance(name, str) and name else None)
            while len(row) < 3:
                row.append(None)
            out[lv] = row
    return out


def _build_magic_stock_by_level(save, spell_meta):
    inventory = save.get("inventory", {}) if isinstance(save, dict) else {}
    inv_magic = {}
    if isinstance(inventory, dict):
        for key in ("Magic", "magic"):
            if isinstance(inventory.get(key), dict):
                inv_magic = cast(dict[str, object], inventory.get(key))
                break
    counts = {lv: {} for lv in range(1, 9)}
    for lv in range(1, 9):
        row = inv_magic.get(f"LV{lv}", {})
        if not isinstance(row, dict):
            continue
        for spell_name, qty in row.items():
            if isinstance(spell_name, str) and spell_name:
                counts[lv][spell_name] = max(0, _safe_int(qty, 0))
    for entry in save.get("party", []) if isinstance(save, dict) else []:
        if not isinstance(entry, dict):
            continue
        slots = _load_equipped_magic_slots_from_entry(entry)
        for lv in range(1, 9):
            for name in slots[lv]:
                if not isinstance(name, str) or not name:
                    continue
                remain = _safe_int(counts.get(lv, {}).get(name, 0), 0)
                if remain > 0:
                    counts[lv][name] = remain - 1
    type_order = {"Black Magic": 0, "White Magic": 1, "Summon Magic": 2}
    stock = {}
    for lv in range(1, 9):
        expanded = []
        for spell_name, qty in counts.get(lv, {}).items():
            mtype = str(spell_meta.get(spell_name, {}).get("type") or "")
            expanded.extend(
                [(type_order.get(mtype, 99), spell_name)] * max(0, _safe_int(qty, 0))
            )
        expanded.sort(key=lambda row: (row[0], row[1]))
        stock[str(lv)] = [name for _, name in expanded]
    return stock


def _ensure_menu_magic_setup(session):
    runtime_state = getattr(session, "state", None)
    raw_save = getattr(runtime_state, "save", {})
    save = raw_save if isinstance(raw_save, dict) else {}
    spell_meta = _build_magic_spell_meta(session)
    stock_by_level = _build_magic_stock_by_level(save, spell_meta)
    equipped_by_member = []
    has_equipped_magic = False
    for entry in save.get("party", []) if isinstance(save, dict) else []:
        if not isinstance(entry, dict):
            continue
        slots = _load_equipped_magic_slots_from_entry(entry)
        if any(name for lv in range(1, 9) for name in slots[lv]):
            has_equipped_magic = True
        equipped_by_member.append({str(lv): list(slots[lv]) for lv in range(1, 9)})
    if not has_equipped_magic and not any(
        stock_by_level.get(str(lv)) for lv in range(1, 9)
    ):
        slots_by_level = {str(lv): [] for lv in range(1, 9)}
        for name, info in spell_meta.items():
            if not isinstance(info, dict):
                continue
            level = max(1, min(8, _safe_int(info.get("level", 1), 1)))
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
    return {"stock_by_level": stock_by_level, "equipped_by_member": equipped_by_member}


def get_menu_state_json():
    if engine is None:
        return json.dumps({}, ensure_ascii=False)
    runtime_state = getattr(engine.session, "state", None)
    save = getattr(runtime_state, "save", {})
    jobs_by_name = getattr(runtime_state, "jobs_by_name", {})
    job_names = sorted(
        [
            name
            for name in (jobs_by_name.keys() if isinstance(jobs_by_name, dict) else [])
            if isinstance(name, str) and name
        ]
    )
    save_party = save.get("party", []) if isinstance(save, dict) else []
    by_member = []
    equip_by_member = []
    for idx, member in enumerate(engine.session.party_members):
        from_job = str(getattr(getattr(member, "job", None), "name", ""))
        save_entry = (
            save_party[idx]
            if isinstance(save_party, list) and idx < len(save_party)
            else {}
        )
        rows = []
        for job_name in job_names:
            to_level = _saved_job_level(save_entry, job_name)
            cp_cost = 0
            if (
                isinstance(job_attr, dict)
                and from_job in job_attr
                and job_name in job_attr
            ):
                cp_cost = int(
                    compute_job_change_cp_cost(
                        from_job=from_job,
                        to_job=job_name,
                        to_job_level=to_level,
                        job_attr=job_attr,
                    )
                )
            rows.append(
                {
                    "job_name": job_name,
                    "cp_cost": int(cp_cost),
                    "saved_job_level": int(to_level),
                    "is_current": bool(job_name == from_job),
                }
            )
        by_member.append(rows)
        eq = getattr(member, "equipment", None)
        if eq is None and isinstance(save_entry, dict):
            eq = save_entry.get("equipment")
        if isinstance(eq, dict):
            eq_dict = eq
        else:
            eq_dict = {
                "main_hand": getattr(eq, "main_hand", None),
                "off_hand": getattr(eq, "off_hand", None),
                "head": getattr(eq, "head", None),
                "body": getattr(eq, "body", None),
                "arms": getattr(eq, "arms", None),
            }
        equip_by_member.append(
            {
                "main_hand": eq_dict.get("main_hand"),
                "off_hand": eq_dict.get("off_hand"),
                "head": eq_dict.get("head"),
                "body": eq_dict.get("body"),
                "arms": eq_dict.get("arms"),
            }
        )
    cp = int(save.get("CP", 0)) if isinstance(save, dict) else 0
    gil = int(save.get("gil", 0)) if isinstance(save, dict) else 0
    items_by_name = getattr(runtime_state, "items_by_name", {})
    weapons_by_name = getattr(runtime_state, "weapons", {})
    armors_by_name = getattr(runtime_state, "armors", {})
    if not isinstance(items_by_name, dict):
        items_by_name = {}
    if not isinstance(weapons_by_name, dict):
        weapons_by_name = {}
    if not isinstance(armors_by_name, dict):
        armors_by_name = {}
    payload = {
        "jobs": job_names,
        "job_candidates_by_member": by_member,
        "equip_candidates_by_member": _build_equip_candidates_by_member(engine.session),
        "equipment_by_member": equip_by_member,
        "magic_setup": _ensure_menu_magic_setup(engine.session),
        "inventory_catalog": {
            "items": sorted(
                [
                    name
                    for name in items_by_name.keys()
                    if isinstance(name, str) and name
                ]
            ),
            "weapons": sorted(
                [
                    name
                    for name in weapons_by_name.keys()
                    if isinstance(name, str) and name
                ]
            ),
            "armors": sorted(
                [
                    name
                    for name in armors_by_name.keys()
                    if isinstance(name, str) and name
                ]
            ),
            "item_types": {
                name: str(item_json.get("ItemType") or "")
                for name, item_json in items_by_name.items()
                if isinstance(name, str) and name and isinstance(item_json, dict)
            },
        },
        "resources": {"cp": cp, "cp_max": 255, "gil": gil},
    }
    return json.dumps(payload, ensure_ascii=False)


def run_battle_round_wasm(js_input_json):
    if engine is None:
        return json.dumps(
            {"error": "engine is not initialized"},
            ensure_ascii=False,
        )
    return engine.execute_round_json(js_input_json)


def full_recover_party_json():
    if engine is None:
        return json.dumps({"session_status": None}, ensure_ascii=False)
    return json.dumps(engine.full_recover_party_payload(), ensure_ascii=False)


def get_session_status_json():
    if engine is None:
        return json.dumps({"session_status": None}, ensure_ascii=False)
    return json.dumps(
        {"session_status": build_session_status_snapshot(engine.session)},
        ensure_ascii=False,
    )


def boot_engine_for_location_with_save_json(
    location_group, location, save_json, seed=7
):
    global state
    parsed = json.loads(save_json)
    if not isinstance(parsed, dict):
        raise ValueError("save_json must be JSON object")
    parsed = _normalize_loaded_save(parsed)
    current_save = getattr(state, "save", {})
    base_save = current_save if isinstance(current_save, dict) else {}
    if isinstance(parsed, dict):
        parsed_party = parsed.get("party")
        base_party = base_save.get("party", []) if isinstance(base_save, dict) else []
        if isinstance(parsed_party, list):
            parsed["party"] = _align_party_to_base(base_party, parsed_party)
    state.save = _merge_save_data(base_save, parsed)
    return boot_engine_for_location(location_group, location, seed=seed)


def export_runtime_save_json():
    if engine is None:
        return ""
    runtime_state = getattr(engine.session, "state", None)
    save = getattr(runtime_state, "save", None)
    if not isinstance(save, dict):
        return ""
    return json.dumps(save, ensure_ascii=False)
