# tests/test_battle_item_targeting.py
from __future__ import annotations

from combat.item_effects import infer_battle_item_target_side


def test_infer_battle_item_target_side_for_recovery_item() -> None:
    assert (
        infer_battle_item_target_side(
            {
                "Name": "Potion",
                "SpellEffect": "Recovery",
                "SpellInfo": {"Effect": "Restore target's HP"},
            }
        )
        == "ally"
    )


def test_infer_battle_item_target_side_for_attack_item() -> None:
    assert (
        infer_battle_item_target_side(
            {
                "Name": "Bomb Fragment",
                "SpellInfo": {"Effect": "Deal fire damage"},
            }
        )
        == "enemy"
    )


def test_infer_battle_item_target_side_for_status_item() -> None:
    assert (
        infer_battle_item_target_side(
            {
                "Name": "Faerie Claws",
                "SpellInfo": {"Effect": "Inflict Confusion"},
            }
        )
        == "enemy"
    )
