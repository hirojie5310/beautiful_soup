# tests/test_libra_spell.py
from random import Random
from types import SimpleNamespace

from combat.models import (
    BattleActorState,
    FinalCharacterStats,
    FinalEnemyStats,
    SpellInfo,
)
from combat.turn_logic import run_character_turn


def _char_stats() -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=9999,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=20,
        row="front",
        main_power=0,
        main_accuracy=0,
        main_atk_multiplier=1,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=1,
        off_two=False,
        off_long=False,
        defense=0,
        defense_multiplier=0,
        evasion_percent=0,
        magic_defense=0,
        magic_def_multiplier=0,
        magic_resistance=0,
        shield_count=0,
    )


def _enemy_stats() -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Killer Bee",
        hp=20,
        level=1,
        job_level=1,
        attack_power=1,
        attack_multiplier=1,
        accuracy_percent=1,
        defense=1,
        defense_multiplier=1,
        evasion_percent=0,
        magic_defense=1,
        magic_def_multiplier=1,
        magic_resistance_percent=0,
        agility=1,
    )


def test_libra_shows_hp_and_weakness_without_dealing_damage() -> None:
    caster_stats = _char_stats()
    enemy_stats = _enemy_stats()
    caster_state = BattleActorState(hp=120, max_hp=120)
    caster_state.mp_pool[4] = 24
    caster_state.max_mp_pool[4] = 24
    enemy_state = BattleActorState(hp=19, max_hp=20)
    libra = SpellInfo(power=0, accuracy_percent=100, magic_type="white", elements=[])
    spell_json = {
        "name": "Libra",
        "Type": "White Magic",
        "Level": 4,
        "Target": "One Enemy",
        "Reflectable": "No",
        "Effect": "View target's HP",
    }
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Runeth",
        enemy_name="Killer Bee A",
        char_stats=caster_stats,
        enemy_stats=enemy_stats,
        enemy_json={"ElementalVulnerability": {"Weakness": ["wind"]}},
        char_state=caster_state,
        enemy_state=enemy_state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=libra,
        char_spell_json=spell_json,
        char_spell_healing_type=None,
        char_spell_name="Libra",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="enemy",
        target_index=0,
        party_members=[
            SimpleNamespace(name="Runeth", stats=caster_stats, state=caster_state)
        ],
        aoe_selected_override=False,
    )

    assert result is None
    assert damage == 0
    assert enemy_state.hp == 19
    assert any("Runethは《Libra》を唱えた！" in line for line in logs)
    assert any("Killer Bee AのHPは19/20だ。" in line for line in logs)
    assert any("Killer Bee AはWind属性に弱い。" in line for line in logs)
