from __future__ import annotations

import json

from adapters.flask_app import _build_equip_candidates_by_member as build_flask_candidates
from adapters.flask_app import _item_allowed_for_member as flask_item_allowed
from combat.runtime_state import init_runtime_state
from combat.usecases import build_battle_session
from ui_pygame.field_effects import (
    dec_inventory_item,
    get_inventory_item_count,
    inc_inventory_item,
)
from web_wasm.bootstrap_runtime import (
    _build_equip_candidates_by_member as build_wasm_candidates,
)


def _build_session_with_equipment_inventory():
    state = init_runtime_state()
    state.save = json.loads(json.dumps(state.save))
    state.save["inventory"] = {"Weapon": {}, "Armor": {}}
    session = build_battle_session(
        state=state,
        enemy_names=sorted(state.monsters.keys())[:3],
    )
    member = session.party_members[0]

    weapon_name = next(
        name
        for name, raw in state.weapons.items()
        if isinstance(name, str)
        and isinstance(raw, dict)
        and flask_item_allowed(member, raw)
    )
    armor_name = next(
        name
        for name, raw in state.armors.items()
        if isinstance(name, str)
        and isinstance(raw, dict)
        and raw.get("ArmorType") == "Helm"
        and flask_item_allowed(member, raw)
    )
    return session, weapon_name, armor_name


def test_inventory_helpers_increment_and_decrement_equipment_stock():
    save = {"inventory": {"Weapon": {}}}

    assert get_inventory_item_count(save, "Weapon", "Mythril Sword") == 0
    assert inc_inventory_item(save, "Weapon", "Mythril Sword")
    assert inc_inventory_item(save, "Weapon", "Mythril Sword", 2)
    assert get_inventory_item_count(save, "Weapon", "Mythril Sword") == 3
    assert dec_inventory_item(save, "Weapon", "Mythril Sword")
    assert get_inventory_item_count(save, "Weapon", "Mythril Sword") == 2


def test_flask_equip_candidates_only_include_items_in_inventory():
    session, weapon_name, armor_name = _build_session_with_equipment_inventory()
    other_weapon_name = next(
        name for name in session.state.weapons.keys() if isinstance(name, str) and name != weapon_name
    )
    session.state.save["inventory"]["Weapon"][weapon_name] = 1
    session.state.save["inventory"]["Armor"][armor_name] = 1

    rows = build_flask_candidates(session)[0]

    main_names = {row.get("name") for row in rows["main_hand"] if row.get("name")}
    head_names = {row.get("name") for row in rows["head"] if row.get("name")}

    assert weapon_name in main_names
    assert armor_name in head_names
    assert other_weapon_name not in main_names
    assert "none" in {row.get("kind") for row in rows["main_hand"]}


def test_wasm_equip_candidates_only_include_items_in_inventory():
    session, weapon_name, armor_name = _build_session_with_equipment_inventory()
    other_weapon_name = next(
        name for name in session.state.weapons.keys() if isinstance(name, str) and name != weapon_name
    )
    session.state.save["inventory"]["Weapon"][weapon_name] = 1
    session.state.save["inventory"]["Armor"][armor_name] = 1

    rows = build_wasm_candidates(session)[0]

    main_names = {row.get("name") for row in rows["main_hand"] if row.get("name")}
    head_names = {row.get("name") for row in rows["head"] if row.get("name")}

    assert weapon_name in main_names
    assert armor_name in head_names
    assert other_weapon_name not in main_names
