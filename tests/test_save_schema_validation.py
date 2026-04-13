from __future__ import annotations

import json

from assets.data.data_loader import (
    load_save_envelope_schema,
    validate_save_data,
    validate_save_envelope,
)
from combat.runtime_state import init_runtime_state


def test_save_schema_file_loads() -> None:
    schema = load_save_envelope_schema()

    assert schema["title"] == "FF3 Save Envelope"
    assert "saveData" in schema["$defs"]


def test_validate_save_data_accepts_runtime_state_save() -> None:
    state = init_runtime_state()
    validate_save_data(json.loads(json.dumps(state.save)))


def test_validate_save_envelope_accepts_v2_style_payload() -> None:
    state = init_runtime_state()
    save = json.loads(json.dumps(state.save))
    save["schema_version"] = 2
    save["party"][0]["current_job"] = str(save["party"][0].get("job") or "")
    save["party"][0]["mp_levels"] = {
        str(level): {"current": int(save["party"][0].get("mp", {}).get(f"L{level}MP", 0))}
        for level in range(1, 9)
    }

    validate_save_envelope(
        {
            "version": 1,
            "saved_at": "2026-04-14T07:00:00Z",
            "selected_location_group": "Bahamut's Lair",
            "selected_location": "Bahamut's Lair",
            "menu_state": {"resources": {"gil": int(save.get("gil", 0))}},
            "save": save,
        }
    )
