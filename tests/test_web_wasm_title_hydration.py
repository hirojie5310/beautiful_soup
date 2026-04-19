from __future__ import annotations

import copy
import json


def test_get_menu_state_json_includes_party_after_loading_save() -> None:
    from web_wasm import bootstrap_runtime

    original_save = copy.deepcopy(bootstrap_runtime.state.save)
    original_engine = bootstrap_runtime.engine
    selected_group = bootstrap_runtime.default_group
    selected_location = bootstrap_runtime.default_location

    try:
        bootstrap_runtime.boot_engine_for_location_with_save_json(
            selected_group,
            selected_location,
            json.dumps(original_save, ensure_ascii=False),
            7,
        )

        menu_state = json.loads(bootstrap_runtime.get_menu_state_json())

        assert isinstance(menu_state.get("party"), list)
        assert len(menu_state["party"]) == len(original_save.get("party", []))
        assert menu_state["party"][0]["name"] == original_save["party"][0]["name"]
        assert "hp" in menu_state["party"][0]
        assert "mp_levels" in menu_state["party"][0]
        assert menu_state["party"][0]["equipment"] == original_save["party"][0]["equipment"]
    finally:
        bootstrap_runtime.state.save = original_save
        bootstrap_runtime.engine = original_engine


def test_get_menu_state_json_keeps_magic_setup_empty_for_new_game_like_save() -> None:
    from web_wasm import bootstrap_runtime

    original_save = copy.deepcopy(bootstrap_runtime.state.save)
    original_engine = bootstrap_runtime.engine
    selected_group = bootstrap_runtime.default_group
    selected_location = bootstrap_runtime.default_location

    try:
        blank_magic = {f"LV{level}": [None, None, None] for level in range(1, 9)}
        new_game_like_save = {
            "schema_version": 2,
            "gil": 0,
            "CP": 0,
            "inventory": {},
            "item_stock": {},
            "party": [
                {
                    "name": "Runeth",
                    "current_job": "Onion Knight",
                    "job": "Onion Knight",
                    "Magic": blank_magic,
                    "equipment": {
                        "main_hand": "Knife",
                        "off_hand": None,
                        "head": None,
                        "body": "Vest",
                        "arms": None,
                    },
                }
            ],
        }

        bootstrap_runtime.boot_engine_for_location_with_save_json(
            selected_group,
            selected_location,
            json.dumps(new_game_like_save, ensure_ascii=False),
            7,
        )

        menu_state = json.loads(bootstrap_runtime.get_menu_state_json())
        assert menu_state["magic_setup"]["stock_by_level"] == {
            str(level): [] for level in range(1, 9)
        }
        assert menu_state["magic_setup"]["equipped_by_member"][0] == {
            str(level): [None, None, None] for level in range(1, 9)
        }
    finally:
        bootstrap_runtime.state.save = original_save
        bootstrap_runtime.engine = original_engine
