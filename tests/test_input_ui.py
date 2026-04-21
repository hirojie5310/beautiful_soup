from __future__ import annotations

from combat.input_ui import build_grouped_item_menu


def test_build_grouped_item_menu_uses_item_metadata_categories() -> None:
    item_list = [
        ("Potion", "Anywhere", 3),
        ("Phoenix Down", "Anywhere", 2),
        ("Echo Herbs", "Anywhere", 1),
        ("Bomb Fragment", "Combat", 4),
        ("Lamia Scale", "Combat", 1),
        ("Bacchus's Cider", "Combat", 1),
    ]
    items_by_name = {
        "Potion": {"effect_category": "heal_hp", "SpellInfo": {"Effect": ""}},
        "Phoenix Down": {"effect_category": "revive", "SpellInfo": {"Effect": ""}},
        "Echo Herbs": {
            "effect_category": "status_recovery",
            "status_ailment": "Silence",
            "SpellInfo": {"Effect": ""},
        },
        "Bomb Fragment": {
            "effect_category": "damage",
            "SpellInfo": {"Element": "Fire", "BasePower": 15, "Effect": ""},
        },
        "Lamia Scale": {
            "effect_category": "status",
            "status_ailment": "Confusion",
            "SpellInfo": {"Effect": ""},
        },
        "Bacchus's Cider": {
            "effect_category": "buff_attack",
            "SpellInfo": {"Effect": ""},
        },
    }

    lines, shown_names = build_grouped_item_menu(item_list, items_by_name)

    assert any("Restore（回復）: 1: Potion(3)" in line for line in lines)
    assert any("Revive（蘇生）: 2: Phoenix Down(2)" in line for line in lines)
    assert any("Cure（治療）: 3: Echo Herbs(1)" in line for line in lines)
    assert any("Damage（攻撃）: 4: Bomb Fragment(4)" in line for line in lines)
    assert any("Inflict（状態異常）: 5: Lamia Scale(1)" in line for line in lines)
    assert any("Support（補助/その他）: 6: Bacchus's Cider(1)" in line for line in lines)
    assert shown_names == [
        "Potion",
        "Phoenix Down",
        "Echo Herbs",
        "Bomb Fragment",
        "Lamia Scale",
        "Bacchus's Cider",
    ]
