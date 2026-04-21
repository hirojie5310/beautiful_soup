from __future__ import annotations

from random import Random
from types import SimpleNamespace

from combat.battle_items import (
    build_battle_item_list,
    build_weapon_spell_item_definition,
)
from combat.item_effects import spell_from_item
from combat.models import BattleActorState
from combat.turn_logic import run_character_turn


def _make_char_stats(*, intelligence: int, mind: int):
    return SimpleNamespace(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=500,
        intelligence=intelligence,
        mind=mind,
    )


def _make_enemy_stats(*, magic_defense: int = 0):
    return SimpleNamespace(
        magic_defense=magic_defense,
    )


def test_build_battle_item_list_includes_spellcast_weapons_from_inventory_and_equipment():
    items_by_name = {
        "Potion": {
            "Name": "Potion",
            "ItemType": "Anywhere",
            "SpellInfo": {"Effect": "Restore target's HP"},
        }
    }
    weapons_by_name = {
        "Air Knife": {"name": "Air Knife", "SpellCast": "Aero"},
        "Salamand Sword": {"name": "Salamand Sword", "SpellCast": "Fire"},
        "Mythril Sword": {"name": "Mythril Sword"},
    }
    spells_by_name = {
        "Aero": {"name": "Aero", "Type": "White Magic", "Effect": "Deal Air damage", "BasePower": 45},
        "Fire": {"name": "Fire", "Type": "Black Magic", "Effect": "Deal Fire damage", "BasePower": 25},
    }
    save = {
        "inventory": {
            "Anywhere": {"Potion": 2},
            "Weapon": {"Salamand Sword": 1},
        },
        "party": [
            {"equipment": {"main_hand": "Air Knife", "off_hand": None}},
        ],
    }

    rows = build_battle_item_list(items_by_name, weapons_by_name, spells_by_name, save)

    assert ("Potion", "Anywhere", 2) in rows
    assert ("Salamand Sword", "Weapon", 1) in rows
    assert ("Air Knife", "Weapon", 1) in rows
    assert all(name != "Mythril Sword" for name, _, _ in rows)


def test_weapon_spell_item_is_not_consumed_and_uses_caster_intelligence():
    fire_staff = build_weapon_spell_item_definition(
        {"name": "Fire Staff", "SpellCast": "Fire"},
        {
            "Fire": {
                "name": "Fire",
                "Type": "Black Magic",
                "Effect": "Deal Fire damage",
                "BasePower": 25,
                "BaseAccuracy": 1.0,
            }
        },
    )
    assert fire_staff is not None

    save_low = {"inventory": {"Weapon": {"Fire Staff": 1}}}
    save_high = {"inventory": {"Weapon": {"Fire Staff": 1}}}

    low_damage, _ = run_character_turn(
        char_name="Refia",
        enemy_name="Goblin",
        char_stats=_make_char_stats(intelligence=10, mind=10),
        enemy_stats=_make_enemy_stats(magic_defense=0),
        enemy_json={},
        char_state=BattleActorState(hp=300),
        enemy_state=BattleActorState(hp=999),
        char_attack_kind="item",
        char_battle_command=None,
        char_weapon_hand="main",
        char_spell=None,
        char_spell_json=None,
        char_spell_healing_type=None,
        char_spell_name=None,
        char_item=fire_staff,
        logs=[],
        rng=Random(7),
        save=save_low,
    )

    high_damage, _ = run_character_turn(
        char_name="Refia",
        enemy_name="Goblin",
        char_stats=_make_char_stats(intelligence=50, mind=10),
        enemy_stats=_make_enemy_stats(magic_defense=0),
        enemy_json={},
        char_state=BattleActorState(hp=300),
        enemy_state=BattleActorState(hp=999),
        char_attack_kind="item",
        char_battle_command=None,
        char_weapon_hand="main",
        char_spell=None,
        char_spell_json=None,
        char_spell_healing_type=None,
        char_spell_name=None,
        char_item=fire_staff,
        logs=[],
        rng=Random(7),
        save=save_high,
    )

    assert save_low["inventory"]["Weapon"]["Fire Staff"] == 1
    assert save_high["inventory"]["Weapon"]["Fire Staff"] == 1
    assert high_damage > low_damage


def test_weapon_spell_item_spellinfo_uses_explicit_element_and_type_metadata():
    aero_knife = build_weapon_spell_item_definition(
        {"name": "Air Knife", "SpellCast": "Aero"},
        {
            "Aero": {
                "name": "Aero",
                "Type": "White Magic",
                "Element": "Air",
                "BasePower": 45,
                "BaseAccuracy": 1.0,
                "effect_category": "damage",
            }
        },
    )

    assert aero_knife is not None
    spell = spell_from_item(aero_knife)

    assert spell.elements == ["air"]
    assert spell.magic_type == "white"
