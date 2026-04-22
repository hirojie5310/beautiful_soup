from __future__ import annotations

import sys
import types
import unittest
from random import Random

jsonschema = types.ModuleType("jsonschema")


class Draft202012Validator:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def iter_errors(self, payload):
        return []


jsonschema.Draft202012Validator = Draft202012Validator
sys.modules.setdefault("jsonschema", jsonschema)

from combat.models import BattleActorState, FinalCharacterStats, FinalEnemyStats, SpellInfo
from combat.turn_logic import run_character_turn


def _char_stats(*, intelligence: int = 40) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=999,
        strength=24,
        agility=20,
        vitality=12,
        intelligence=intelligence,
        mind=10,
        row="front",
        main_power=1,
        main_accuracy=100,
        main_atk_multiplier=1,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=0,
        off_two=False,
        off_long=False,
        defense=10,
        defense_multiplier=0,
        evasion_percent=0,
        magic_defense=0,
        magic_def_multiplier=0,
        magic_resistance=0,
        shield_count=0,
    )


def _enemy_stats(*, hp: int = 120) -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Goblin",
        hp=hp,
        level=10,
        job_level=1,
        attack_power=1,
        attack_multiplier=1,
        accuracy_percent=1,
        defense=1,
        defense_multiplier=0,
        evasion_percent=0,
        magic_defense=0,
        magic_def_multiplier=0,
        magic_resistance_percent=0,
        agility=1,
    )


class SummonDamageStatusPlaceholderTest(unittest.TestCase):
    def test_damage_summon_with_dash_status_still_deals_damage(self) -> None:
        char_stats = _char_stats()
        enemy_stats = _enemy_stats(hp=120)
        char_state = BattleActorState(hp=999, max_hp=999)
        char_state.mp_pool[2] = 5
        char_state.max_mp_pool[2] = 5
        enemy_state = BattleActorState(hp=120, max_hp=120)
        logs: list[str] = []

        damage, result = run_character_turn(
            char_name="Runeth",
            enemy_name="Goblin",
            char_stats=char_stats,
            enemy_stats=enemy_stats,
            enemy_json={},
            char_state=char_state,
            enemy_state=enemy_state,
            char_attack_kind="magic",
            char_battle_command="Magic",
            char_weapon_hand="main",
            char_spell=SpellInfo(
                power=32,
                accuracy_percent=100,
                magic_type="summon",
                elements=["ice"],
            ),
            char_spell_json={
                "Name": "Shiva: Diamond Dust",
                "Type": "Summon",
                "Level": 2,
                "Target": "All Enemies",
                "Power": 32,
                "Accuracy": 100,
                "Status": "-",
            },
            char_spell_healing_type=None,
            char_spell_name="Shiva: Diamond Dust",
            char_item=None,
            logs=logs,
            rng=Random(0),
            target_side="enemy",
            target_index=0,
            aoe_selected_override=True,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.end_reason, "enemy_defeated")
        self.assertGreater(damage, 0)
        self.assertLess(enemy_state.hp, 120)
        self.assertTrue(any("Goblinに" in line and "のダメージ" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
