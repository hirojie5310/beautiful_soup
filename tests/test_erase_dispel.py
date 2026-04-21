from random import Random

from combat.models import BattleActorState, FinalCharacterStats, FinalEnemyStats
from combat.status_effects import apply_status_spell_to_enemy


def _enemy_stats() -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Ifrit",
        hp=500,
        level=20,
        job_level=1,
        attack_power=1,
        attack_multiplier=1,
        accuracy_percent=1,
        defense=10,
        defense_multiplier=1,
        evasion_percent=0,
        magic_defense=12,
        magic_def_multiplier=1,
        magic_resistance_percent=0,
        agility=1,
    )


def _caster_stats() -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=1,
        job_skill_point=0,
        max_hp=999,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=20,
        row="front",
        main_power=1,
        main_accuracy=1,
        main_atk_multiplier=1,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=0,
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


def test_erase_dispels_enemy_buffs_without_name_fallback() -> None:
    enemy_stats = _enemy_stats()
    enemy_stats.haste_power_bonus = 14
    enemy_stats.haste_multiplier_bonus = 2
    enemy_stats.protect_defense_bonus = 9
    enemy_stats.protect_magic_defense_bonus = 9
    enemy_stats.defense += 9
    enemy_stats.magic_defense += 9
    enemy_state = BattleActorState(hp=500, max_hp=500, reflect_charges=1)
    logs: list[str] = []

    handled = apply_status_spell_to_enemy(
        spell_json={
            "Name": "Null Field",
            "effect_category": "remove_reflect",
            "dispel_effects": "Protect, Haste, Reflect",
        },
        enemy_state=enemy_state,
        enemy_json={"Level": 20, "StatusAilmentVulnerability": {"Immune": []}},
        enemy_name="Ifrit",
        rng=Random(0),
        logs=logs,
        caster_stats=_caster_stats(),
        enemy_stats=enemy_stats,
    )

    assert handled is True
    assert enemy_state.reflect_charges == 0
    assert enemy_stats.haste_power_bonus == 0
    assert enemy_stats.haste_multiplier_bonus == 0
    assert enemy_stats.protect_defense_bonus == 0
    assert enemy_stats.protect_magic_defense_bonus == 0
    assert enemy_stats.defense == 10
    assert enemy_stats.magic_defense == 12
    assert any("解除" in line for line in logs)
