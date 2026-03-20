# tests/test_initiative_weight.py
import random

from combat.char_build import compute_character_final_stats
from combat.enemy_build import compute_enemy_final_stats
from combat.initiative import calc_initiative
from combat.models import BaseCharacter, EquipmentSet


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
