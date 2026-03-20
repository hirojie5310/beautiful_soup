# tests/test_initiative_weight.py
import random

from combat.char_build import compute_character_final_stats
from combat.enemy_build import compute_enemy_final_stats
from combat.initiative import calc_initiative
from combat.models import BaseCharacter, EquipmentSet, PlannedAction, PlannedEnemyAction
from combat.battle_sim import (
    _spell_weight_for_character_action,
    _spell_weight_for_enemy_action,
)


def test_calc_initiative_uses_agility_weight_and_random_range() -> None:
    rng = random.Random(0)

    value = calc_initiative(agility=10, weight=7, rng=rng)

    assert value == 19


def test_compute_enemy_final_stats_reads_weight_from_monster_json() -> None:
    stats = compute_enemy_final_stats(
        {
            "name": "Test Enemy",
            "HP": 100,
            "Level": 10,
            "Attack": {"Count": 2, "Accuracy": 0.8},
            "Evasion": {"Count": 1, "Rate": 0.2},
            "MagicResistance": {"Count": 1, "Rate": 0.1},
            "Weight": 6,
        }
    )

    assert stats.weight == 6


def test_compute_character_final_stats_sums_equipment_weight() -> None:
    base = BaseCharacter(
        level=10,
        total_exp=0,
        job_level=10,
        job_skill_point=0,
        max_hp=100,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=10,
    )
    eq = EquipmentSet(
        main_hand="Mythril Sword",
        off_hand="Buckler",
        head="Leather Cap",
        body="Leather Armor",
        arms="Bronze Bracers",
    )
    weapons = {
        "Mythril Sword": {"BasePower": 10, "BaseAccuracy": 0.9, "Weight": 2},
    }
    armors = {
        "Buckler": {
            "Defense": 1,
            "Evasion": 0.05,
            "BaseMagicDefense": 0,
            "ArmorType": "Shield",
            "Weight": 1,
        },
        "Leather Cap": {
            "Defense": 1,
            "Evasion": 0.0,
            "BaseMagicDefense": 0,
            "ArmorType": "Head",
            "Weight": 3,
        },
        "Leather Armor": {
            "Defense": 3,
            "Evasion": 0.0,
            "BaseMagicDefense": 0,
            "ArmorType": "Body",
            "Weight": 4,
        },
        "Bronze Bracers": {
            "Defense": 1,
            "Evasion": 0.0,
            "BaseMagicDefense": 0,
            "ArmorType": "Arms",
            "Weight": 5,
        },
    }

    stats = compute_character_final_stats(base, eq, weapons, armors, job_name="Warrior")

    assert stats.weight == 15


def test_compute_character_final_stats_applies_dict_bonus_to_stats() -> None:
    base = BaseCharacter(
        level=10,
        total_exp=0,
        job_level=10,
        job_skill_point=0,
        max_hp=100,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=10,
    )
    eq = EquipmentSet(main_hand="Onion Sword", body="White Robe")
    weapons = {
        "Onion Sword": {
            "BasePower": 200,
            "BaseAccuracy": 1.0,
            "Weight": 1,
            "Bonus": {"Strength": 5, "Agility": 5, "Vitality": 5},
        }
    }
    armors = {
        "White Robe": {
            "Defense": 20,
            "Evasion": 0.12,
            "BaseMagicDefense": 14,
            "ArmorType": "Armor",
            "Weight": 0,
            "Bonus": {"Mind": 5},
        }
    }

    stats = compute_character_final_stats(base, eq, weapons, armors, job_name="Warrior")

    assert stats.strength == 15
    assert stats.agility == 15
    assert stats.vitality == 15
    assert stats.mind == 15
    assert stats.main_power == 203
    assert stats.main_accuracy == 105
    assert stats.defense == 27
    assert stats.magic_resistance == 12


def test_compute_character_final_stats_applies_legacy_string_bonus_to_stats() -> None:
    base = BaseCharacter(
        level=10,
        total_exp=0,
        job_level=10,
        job_skill_point=0,
        max_hp=100,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=10,
    )
    eq = EquipmentSet(off_hand="Genji Shield")
    weapons = {}
    armors = {
        "Genji Shield": {
            "Defense": 20,
            "Evasion": 0.18,
            "BaseMagicDefense": 35,
            "ArmorType": "Shield",
            "Weight": 1,
            "Bonus": "Agility +5, Strength +5",
        }
    }

    stats = compute_character_final_stats(base, eq, weapons, armors, job_name="Warrior")

    assert stats.strength == 15
    assert stats.agility == 15
    assert stats.vitality == 10
    assert stats.defense == 25
    assert stats.evasion_percent == 21


def test_spell_weight_for_character_magic_action_reads_spell_json() -> None:
    action = PlannedAction(kind="magic", command="Magic", spell_name="Fire")
    spells = {"Fire": {"Weight": 4}}

    assert _spell_weight_for_character_action(action, spells) == 4


def test_spell_weight_for_character_non_magic_action_is_zero() -> None:
    action = PlannedAction(kind="physical", command="Fight", spell_name="Fire")
    spells = {"Fire": {"Weight": 4}}

    assert _spell_weight_for_character_action(action, spells) == 0


def test_spell_weight_for_enemy_special_action_reads_embedded_spell_weight() -> None:
    action = PlannedEnemyAction(
        kind="special",
        spell_name="Lightning",
        spell_json={"Name": "Lightning", "Weight": 6},
    )

    assert _spell_weight_for_enemy_action(action, {"Lightning": {"Weight": 3}}) == 6


def test_spell_weight_for_enemy_special_action_falls_back_to_base_spell_json() -> None:
    action = PlannedEnemyAction(
        kind="special",
        spell_name="Lightning",
        spell_json={"Name": "Lightning"},
    )

    assert _spell_weight_for_enemy_action(action, {"Lightning": {"Weight": 3}}) == 3


def test_spell_weight_for_enemy_normal_action_is_zero() -> None:
    action = PlannedEnemyAction(kind="normal")

    assert _spell_weight_for_enemy_action(action, {"Lightning": {"Weight": 3}}) == 0
