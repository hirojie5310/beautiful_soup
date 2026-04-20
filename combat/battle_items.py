from __future__ import annotations

from typing import Any

from combat.inventory import build_item_list
from combat.spell_metadata import spell_target_scope


def _weapon_name(weapon_json: dict[str, Any]) -> str:
    raw = weapon_json.get("Name") or weapon_json.get("name") or ""
    return str(raw).strip()


def is_weapon_spell_item(item_json: dict[str, Any] | None) -> bool:
    if not isinstance(item_json, dict):
        return False
    return str(item_json.get("BattleUseSource") or "").strip().lower() == "weapon"


def build_weapon_spell_item_definition(
    weapon_json: dict[str, Any],
    spells_by_name: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(weapon_json, dict):
        return None

    weapon_name = _weapon_name(weapon_json)
    spell_name = str(weapon_json.get("SpellCast") or "").strip()
    if not weapon_name or not spell_name:
        return None

    spell_json = spells_by_name.get(spell_name)
    if not isinstance(spell_json, dict):
        return None

    spell_info = {
        "BasePower": int(spell_json.get("BasePower", 0) or 0),
        "BaseAccuracy": 1.0,
        "Effect": spell_json.get("Effect") or "",
    }
    if spell_json.get("Element") is not None:
        spell_info["Element"] = spell_json.get("Element")
    if spell_json.get("Elements") is not None:
        spell_info["Elements"] = spell_json.get("Elements")
    if spell_json.get("Target") is not None:
        spell_info["Target"] = spell_json.get("Target")
    if spell_json.get("Type") is not None:
        spell_info["MagicType"] = spell_json.get("Type")

    weapon_item = {
        "Name": weapon_name,
        "ItemType": "Weapon",
        "BattleUseSource": "weapon",
        "SpellCast": spell_name,
        "SpellEffect": spell_name,
        "SpellInfo": spell_info,
        "Multiplier": 1,
        "Value": int(spell_json.get("BasePower", 0) or 0),
        "WeaponSpell": spell_json,
        "WeaponType": weapon_json.get("Type"),
    }
    for key in ("default_target_side", "target_scope", "effect_category", "status_ailment"):
        if spell_json.get(key) is not None:
            weapon_item[key] = spell_json.get(key)
    if "target_scope" not in weapon_item:
        weapon_item["target_scope"] = spell_target_scope(spell_json)
    return weapon_item


def build_battle_item_definitions(
    items_by_name: dict[str, dict[str, Any]],
    weapons_by_name: dict[str, dict[str, Any]],
    spells_by_name: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {
        str(name): item_json
        for name, item_json in (items_by_name or {}).items()
        if isinstance(name, str) and isinstance(item_json, dict)
    }

    for weapon_name, weapon_json in (weapons_by_name or {}).items():
        if not isinstance(weapon_name, str):
            continue
        weapon_item = build_weapon_spell_item_definition(weapon_json, spells_by_name)
        if weapon_item is None:
            continue
        merged[weapon_name] = weapon_item

    return merged


def count_battle_usable_weapon(
    save: dict[str, Any] | None,
    weapon_name: str,
) -> int:
    if not isinstance(save, dict) or not weapon_name:
        return 0

    total = 0

    inventory = save.get("inventory") or {}
    if isinstance(inventory, dict):
        for bucket_name in ("Weapon", "Equipment"):
            bucket = inventory.get(bucket_name)
            if isinstance(bucket, dict):
                total += int(bucket.get(weapon_name, 0) or 0)

    for member in save.get("party") or []:
        if not isinstance(member, dict):
            continue
        equipment = member.get("equipment") or {}
        if not isinstance(equipment, dict):
            continue
        if equipment.get("main_hand") == weapon_name:
            total += 1
        if equipment.get("off_hand") == weapon_name:
            total += 1

    return total


def build_battle_item_list(
    items_by_name: dict[str, dict[str, Any]],
    weapons_by_name: dict[str, dict[str, Any]],
    spells_by_name: dict[str, dict[str, Any]],
    save: dict[str, Any],
) -> list[tuple[str, str, int]]:
    item_list = list(build_item_list(items_by_name, save, in_battle=True))
    existing_names = {name for name, _, _ in item_list}

    for weapon_name, weapon_json in (weapons_by_name or {}).items():
        if not isinstance(weapon_name, str) or weapon_name in existing_names:
            continue
        if build_weapon_spell_item_definition(weapon_json, spells_by_name) is None:
            continue
        qty = count_battle_usable_weapon(save, weapon_name)
        if qty <= 0:
            continue
        item_list.append((weapon_name, "Weapon", qty))

    item_list.sort(key=lambda x: (x[1], x[0]))
    return item_list
