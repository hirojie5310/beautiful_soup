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
