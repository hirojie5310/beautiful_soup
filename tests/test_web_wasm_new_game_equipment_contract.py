from __future__ import annotations

from web_wasm.bootstrap_runtime import _align_party_to_base, _merge_save_data


def test_align_party_to_base_keeps_explicit_none_equipment_slots() -> None:
    base_party = [
        {
            "name": "Runeth",
            "portrait_key": "runeth",
            "equipment": {
                "main_hand": "Mythril Sword",
                "off_hand": "Ice Shield",
                "head": "Ribbon",
                "body": "Knight Armor",
                "arms": "Protect Ring",
            },
        }
    ]
    overlay_party = [
        {
            "name": "Runeth",
            "portrait_key": "runeth",
            "equipment": {
                "main_hand": "Knife",
                "off_hand": None,
                "head": None,
                "body": "Vest",
                "arms": None,
            },
        }
    ]

    aligned = _align_party_to_base(base_party, overlay_party)

    assert aligned[0]["equipment"] == {
        "main_hand": "Knife",
        "off_hand": None,
        "head": None,
        "body": "Vest",
        "arms": None,
    }


def test_merge_save_data_keeps_explicit_none_values_in_overlay_dict() -> None:
    merged = _merge_save_data(
        {
            "equipment": {
                "main_hand": "Sword",
                "off_hand": "Ice Shield",
                "head": "Ribbon",
                "body": "Armor",
                "arms": "Protect Ring",
            }
        },
        {
            "equipment": {
                "main_hand": "Knife",
                "off_hand": None,
                "head": None,
                "body": "Vest",
                "arms": None,
            }
        },
    )

    assert merged["equipment"] == {
        "main_hand": "Knife",
        "off_hand": None,
        "head": None,
        "body": "Vest",
        "arms": None,
    }
