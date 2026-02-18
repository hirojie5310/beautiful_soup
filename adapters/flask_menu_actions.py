# adapters/flask_menu_actions.py
from __future__ import annotations

from typing import Callable, Optional

from combat.constants import FIELD_ITEM_TARGET_REQUIRED
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

STATUS_KEY_BY_SPELL = {
    "Poisona": "poison",
    "Blindna": "blind",
    "Stona": "petrification",
}
ESUNA_CURES = {
    "poison",
    "blind",
    "mini",
    "silence",
    "toad",
    "petrification",
    "partial petrification",
    "confusion",
    "sleep",
    "paralysis",
}
HEAL_SPELLS = {"Cure", "Cura", "Curaga", "Curaja"}
RAISE_SPELLS = {"Raise", "Arise"}


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

    def _heal_amount(spell_name: str) -> int:
        if spell_name == "Cure":
            return 50
        if spell_name == "Cura":
            return 150
        if spell_name == "Curaga":
            return 400
        if spell_name == "Curaja":
            return 9999
        return 0

    def cast_field_magic(
        caster_idx: int, spell_name: str, target_idx: int | None
    ) -> bool:
        caster = party[caster_idx]
        if spell_name not in spells_by_name:
            return False

        cost_info = _get_cost(caster_idx, spell_name)
        if cost_info is None:
            return False
        lv, cost = cost_info

        if spell_name in (
            HEAL_SPELLS | RAISE_SPELLS | set(STATUS_KEY_BY_SPELL) | {"Esuna"}
        ):
            if target_idx is None:
                return False
            target = party[target_idx]
        else:
            return False

        changed = False
        if spell_name in HEAL_SPELLS:
            amt = _heal_amount(spell_name)
            if amt >= 9999:
                changed = set_hp(target, target.max_hp)
            else:
                changed = set_hp(target, int(target.hp) + amt)
        elif spell_name in RAISE_SPELLS:
            if int(target.hp) > 0:
                changed = False
            elif spell_name == "Arise":
                changed = set_hp(target, target.max_hp)
            else:
                changed = set_hp(target, max(1, target.max_hp // 2))
        elif spell_name in STATUS_KEY_BY_SPELL:
            changed = clear_status(target, STATUS_KEY_BY_SPELL[spell_name], save_dict)
            if spell_name == "Stona":
                changed = (
                    clear_status(target, "Partial Petrification", save_dict) or changed
                )
        elif spell_name == "Esuna":
            for key in list(ESUNA_CURES):
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
    def _canon(s: str) -> str:
        return normalize_text_basic(s)

    def _needs_target(item_name: str) -> bool:
        return _canon(item_name) in FIELD_ITEM_TARGET_REQUIRED

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

    def _heal_amount_by_item(item_name: str) -> int:
        n = _canon(item_name)
        if n == "potion":
            return 90
        if n in ("hi-potion", "hi potion"):
            return 360
        return 0

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
        if _needs_target(item_name):
            if target_idx is None or target_idx < 0 or target_idx >= len(party):
                return False
            target = party[target_idx]

        changed = False
        amt = _heal_amount_by_item(item_name)
        spell_eff = item.get("SpellEffect")

        if amt > 0:
            if target is None:
                return False
            changed = set_hp(target, int(target.hp) + amt)
        elif item_name == "Elixir":
            if target is None:
                return False
            changed = set_hp(target, target.max_hp) or _restore_mp_all(target)
        elif isinstance(spell_eff, str) and spell_eff:
            if target is None:
                return False
            if spell_eff == "Poisona":
                changed = clear_status(target, "poison", save_dict)
            elif spell_eff == "Blindna":
                changed = clear_status(target, "blind", save_dict)
            elif spell_eff == "Stona":
                changed = clear_status(target, "petrification", save_dict)
                changed = (
                    clear_status(target, "Partial Petrification", save_dict) or changed
                )
            elif spell_eff == "Raise":
                if int(target.hp) <= 0:
                    changed = set_hp(target, max(1, target.max_hp // 2))
            elif spell_eff == "Arise":
                if int(target.hp) <= 0:
                    changed = set_hp(target, target.max_hp)

        if not changed:
            return False
        if not dec_inventory_item(save_dict or {}, inv_type, item_name):
            return False

        if target is not None:
            sync_hp_status_to_save(target, save_dict)
        return True

    return use_field_item
