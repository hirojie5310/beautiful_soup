# tests/test_battle_item_targeting.py
from __future__ import annotations

from combat.item_effects import infer_battle_item_target_side


def test_infer_battle_item_target_side_for_recovery_item() -> None:
    assert (
        infer_battle_item_target_side(
            {
                "Name": "Potion",
                "effect_category": "heal_hp",
                "default_target_side": "Ally",
            }
        )
        == "ally"
    )


def test_infer_battle_item_target_side_for_attack_item() -> None:
    assert (
        infer_battle_item_target_side(
            {
                "Name": "Bomb Fragment",
                "effect_category": "damage",
                "default_target_side": "Enemy",
            }
        )
        == "enemy"
    )


def test_infer_battle_item_target_side_for_status_item() -> None:
    assert (
        infer_battle_item_target_side(
            {
                "Name": "Faerie Claws",
                "effect_category": "status",
                "default_target_side": "Enemy",
                "status_ailment": "Confusion",
            }
        )
        == "enemy"
    )


def test_infer_battle_item_target_side_requires_explicit_item_metadata() -> None:
    assert (
        infer_battle_item_target_side(
            {
                "Name": "Mystery Potion",
                "SpellInfo": {"Effect": "Restore target's HP"},
            }
        )
        is None
    )
