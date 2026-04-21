# adapters/flask_menu_actions.py
from __future__ import annotations

from typing import Callable, Optional

from combat.spell_metadata import (
    spell_default_target_side,
    spell_effect_category,
    spell_status_text,
)
from combat.enums import Status
from ui_pygame.field_effects import (
    FIELD_ITEM_TYPES,
    clear_status,
    dec_inventory_item,
    get_battle_state,
    set_hp,
    sync_hp_status_to_save,
    sync_mp_to_save,
)
from utils.text_normalize import normalize_text_basic


def _status_keys_from_text(raw: object) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    return [normalize_text_basic(part) for part in text.split(",") if part.strip()]


def _field_spell_heal_amount(spell: dict) -> int:
    return int(spell.get("field_heal_hp", 0) or 0)


def _field_spell_revive_mode(spell: dict) -> str:
    return normalize_text_basic(spell.get("field_revive_hp") or "")


def _field_item_effect_category(item: dict) -> str:
    return normalize_text_basic(item.get("effect_category") or "")


def _field_item_status_keys(item: dict) -> list[str]:
    spell_info = item.get("SpellInfo") or {}
    return _status_keys_from_text(
        item.get("status_ailment")
        or item.get("StatusAilment")
        or item.get("StatusAilments")
        or spell_info.get("status_ailment")
        or spell_info.get("StatusAilment")
        or spell_info.get("StatusAilments")
    )


def make_cast_field_magic_fn(
    *,
    party,
    spells_by_name: dict[str, dict],
    build_magic_fn: Callable[[int], list[tuple[str, int, int]]],
    save_dict: Optional[dict] = None,
) -> Callable[[int, str, Optional[int]], bool]:
    def _get_cost(caster_idx: int, spell_name: str) -> tuple[int, int] | None:
        for n, lv, _cost in build_magic_fn(caster_idx):
            if str(n) == spell_name:
                return int(lv), 1
        return None

    def _consume_mp(actor, lv: int, cost: int) -> bool:
        st = get_battle_state(actor)
        if st is None:
            return False
        cur = int(st.mp_pool.get(lv, 0))
        if cur < cost:
            return False
        st.mp_pool[lv] = cur - cost
        return True

    def cast_field_magic(
        caster_idx: int, spell_name: str, target_idx: int | None
    ) -> bool:
        caster = party[caster_idx]
        spell = spells_by_name.get(spell_name)
        if not spell:
            return False

        cost_info = _get_cost(caster_idx, spell_name)
        if cost_info is None:
            return False
        lv, cost = cost_info

        effect_category = spell_effect_category(spell)
        status_keys = _status_keys_from_text(spell_status_text(spell))
        target_side = spell_default_target_side(spell, healing_type=None)

        if target_side not in {"Ally", "Any"}:
            return False
        if target_idx is None:
            return False
        target = party[target_idx]

        changed = False
        if effect_category == "heal_hp":
            amt = _field_spell_heal_amount(spell)
            if amt >= 9999:
                changed = set_hp(target, target.max_hp)
            else:
                changed = set_hp(target, int(target.hp) + amt)
        elif effect_category == "revive":
            if int(target.hp) > 0:
                changed = False
            elif _field_spell_revive_mode(spell) == "full":
                changed = set_hp(target, target.max_hp)
            else:
                changed = set_hp(target, max(1, target.max_hp // 2))
        elif effect_category == "status_recovery":
            for key in status_keys:
                changed = clear_status(target, key, save_dict) or changed

        if not changed:
            return False
        if not _consume_mp(caster, lv, cost):
            return False

        sync_mp_to_save(caster, save_dict)
        sync_hp_status_to_save(target, save_dict)
        return True

    return cast_field_magic


def make_use_field_item_fn(
    *,
    party,
    items_by_name: dict[str, dict],
    save_dict: Optional[dict] = None,
) -> Callable[[int, str, Optional[int], Optional[str]], bool]:
    def _find_item_type(item_name: str, hint: str | None) -> str | None:
        if hint in FIELD_ITEM_TYPES:
            return hint
        if not isinstance(save_dict, dict):
            return None
        inv = save_dict.get("inventory", {})
        for itype in FIELD_ITEM_TYPES:
            bucket = inv.get(itype, {})
            if isinstance(bucket, dict) and int(bucket.get(item_name, 0) or 0) > 0:
                return itype
        return None

    def _restore_mp_all(target) -> bool:
        st = get_battle_state(target)
        if st is None:
            return False
        changed = False
        for lv in range(1, 9):
            cur = int(st.mp_pool.get(lv, 0))
            mx = int(st.max_mp_pool.get(lv, cur))
            if cur < mx:
                st.mp_pool[lv] = mx
                changed = True
        return changed

    def use_field_item(
        user_idx: int,
        item_name: str,
        target_idx: int | None,
        item_type_hint: str | None = None,
    ) -> bool:
        if user_idx < 0 or user_idx >= len(party):
            return False
        item = items_by_name.get(item_name, {})
        if not item:
            return False
        item_type = item.get("ItemType")
        if item_type not in FIELD_ITEM_TYPES:
            return False

        inv_type = _find_item_type(item_name, item_type_hint)
        if inv_type is None:
            return False

        target = None
        target_side_raw = normalize_text_basic(item.get("default_target_side") or "")
        if target_side_raw in {"ally", "any"}:
            if target_idx is None or target_idx < 0 or target_idx >= len(party):
                return False
            target = party[target_idx]

        changed = False
        effect_category = _field_item_effect_category(item)
        status_keys = _field_item_status_keys(item)
        amt = int(item.get("Value", 0) or 0)

        if effect_category == "heal_hp":
            if target is None:
                return False
            changed = set_hp(target, int(target.hp) + amt)
        elif effect_category == "heal_full":
            if target is None:
                return False
            hp_changed = set_hp(target, target.max_hp)
            mp_changed = _restore_mp_all(target)
            changed = hp_changed or mp_changed
        elif effect_category == "status_recovery":
            if target is None:
                return False
            for key in status_keys:
                changed = clear_status(target, key, save_dict) or changed
        elif effect_category == "revive":
            if target is None:
                return False
            if int(target.hp) <= 0:
                changed = set_hp(target, max(1, target.max_hp // 2))

        if not changed:
            return False
        if not dec_inventory_item(save_dict or {}, inv_type, item_name):
            return False

        if target is not None:
            sync_hp_status_to_save(target, save_dict)
        return True

    return use_field_item
