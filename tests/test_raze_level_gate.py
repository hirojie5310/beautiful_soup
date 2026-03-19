# tests/test_raze_level_gate.py
import random

from combat.enums import Status
from combat.models import BattleActorState, FinalCharacterStats
from combat.status_effects import apply_status_spell_to_enemy


def make_caster(*, level: int, mind: int = 40) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=level,
        job_level=1,
        job_skill_point=0,
        max_hp=100,
        strength=1,
        agility=1,
        vitality=1,
        intelligence=1,
        mind=mind,
        row="front",
        main_power=1,
        main_accuracy=1,
        main_atk_multiplier=1,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=1,
        off_two=False,
        off_long=False,
        defense=1,
        defense_multiplier=1,
        evasion_percent=0,
        magic_defense=1,
        magic_def_multiplier=1,
        magic_resistance=0,
        shield_count=0,
    )


def test_raze_fails_when_target_level_meets_ff3_threshold():
    spell_json = {"Name": "Raze", "BaseAccuracy": 0.8, "Effect": "Inflict KO"}
    enemy_state = BattleActorState(hp=999, max_hp=999)
    enemy_json = {"Level": 15, "StatusAilmentVulnerability": {"Immune": []}}
    logs = []

    handled = apply_status_spell_to_enemy(
        spell_json=spell_json,
        enemy_state=enemy_state,
        enemy_json=enemy_json,
        enemy_name="Ifrit",
        rng=random.Random(0),
        logs=logs,
        caster_stats=make_caster(level=20),
    )

    assert handled is True
    assert enemy_state.hp == 999
    assert Status.KO not in enemy_state.statuses
    assert any("命中率0.0%" in line for line in logs)


def test_raze_can_hit_when_target_level_is_below_ff3_threshold():
    spell_json = {"Name": "Raze", "BaseAccuracy": 1.0, "Effect": "Inflict KO"}
    enemy_state = BattleActorState(hp=500, max_hp=500)
    enemy_json = {"Level": 14, "StatusAilmentVulnerability": {"Immune": []}}
    logs = []

    handled = apply_status_spell_to_enemy(
        spell_json=spell_json,
        enemy_state=enemy_state,
        enemy_json=enemy_json,
        enemy_name="Garuda",
        rng=random.Random(0),
        logs=logs,
        caster_stats=make_caster(level=20),
    )

    assert handled is True
    assert enemy_state.hp == 0
    assert Status.KO in enemy_state.statuses
    assert any("《Raze》の効果で倒れた" in line for line in logs)
