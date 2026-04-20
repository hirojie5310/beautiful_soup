from __future__ import annotations

from typing import Any, Dict

from utils.text_normalize import normalize_text_basic


SUPPORT_HEALING_KINDS = {"hp", "status", "revive", "protect", "haste", "reflect"}


def spell_display_name(spell_json: Dict[str, Any]) -> str:
    return str(spell_json.get("Name") or spell_json.get("name") or "")


def spell_effect_category(spell_json: Dict[str, Any]) -> str:
    return normalize_text_basic(spell_json.get("effect_category") or "")


def spell_target_scope(spell_json: Dict[str, Any]) -> str:
    scope = normalize_text_basic(spell_json.get("target_scope") or "")
    if scope in {"one", "all", "one_or_all"}:
        return scope

    target = normalize_text_basic(spell_json.get("Target") or spell_json.get("target") or "")
    if target in {"one/all enemies", "one/all allies", "one/all"}:
        return "one_or_all"
    if target in {"all enemies", "all allies"}:
        return "all"
    return "one"


def spell_can_select_all(spell_json: Dict[str, Any]) -> bool:
    return spell_target_scope(spell_json) == "one_or_all"


def spell_auto_all_target(spell_json: Dict[str, Any]) -> bool:
    return spell_target_scope(spell_json) == "all"


def spell_default_target_side(
    spell_json: Dict[str, Any],
    *,
    healing_type: str | None = None,
) -> str:
    side = normalize_text_basic(spell_json.get("default_target_side") or "")
    if side == "ally":
        return "Ally"
    if side == "enemy":
        return "Enemy"
    if side == "any":
        return "Any"

    target = normalize_text_basic(spell_json.get("Target") or spell_json.get("target") or "")
    is_ally_target = "ally" in target or "allies" in target
    is_enemy_target = "enemy" in target or "enemies" in target

    if healing_type == "hp":
        if spell_target_scope(spell_json) == "all" and is_ally_target:
            return "Ally"
        return "Any"
    if healing_type in SUPPORT_HEALING_KINDS:
        return "Ally"
    if is_ally_target:
        return "Ally"
    if is_enemy_target:
        return "Enemy"
    return "Enemy"


def spell_target_mode(
    spell_json: Dict[str, Any],
    *,
    healing_type: str | None = None,
) -> str:
    side = spell_default_target_side(spell_json, healing_type=healing_type)
    if side == "Any":
        return "any"
    if side == "Ally":
        return "ally_only"
    return "enemy_only"


def spell_status_text(spell_json: Dict[str, Any]) -> str:
    return str(
        spell_json.get("status_ailment")
        or spell_json.get("StatusAilment")
        or spell_json.get("StatusAilments")
        or spell_json.get("Status")
        or ""
    ).strip()
