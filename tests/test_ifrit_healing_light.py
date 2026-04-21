# tests/test_ifrit_healing_light.py
from random import Random
from types import SimpleNamespace

from combat.magic_damage import magic_heal_amount_to_char
from combat.models import (
    BattleActorState,
    FinalCharacterStats,
    FinalEnemyStats,
    SpellInfo,
)
from combat.turn_logic import run_character_turn


def _char_stats(*, max_hp: int = 5000) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=25,
        job_level=25,
        job_skill_point=0,
        max_hp=max_hp,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=40,
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
        name="Goblin",
        hp=500,
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


def test_ifrit_healing_light_all_allies_is_not_split() -> None:
    caster_stats = _char_stats(max_hp=5000)
    ally1_stats = _char_stats(max_hp=5000)
    ally2_stats = _char_stats(max_hp=5000)
    enemy_stats = _enemy_stats()

    caster_state = BattleActorState(hp=1200, max_hp=5000)
    caster_state.mp_pool[5] = 1
    caster_state.max_mp_pool[5] = 1
    ally1_state = BattleActorState(hp=100, max_hp=5000)
    ally2_state = BattleActorState(hp=200, max_hp=5000)
    enemy_state = BattleActorState(hp=500, max_hp=500)

    healing_light = SpellInfo(
        power=90,
        accuracy_percent=100,
        magic_type="summon",
        elements=[],
        auto_all_target=True,
    )
    spell_json = {
        "Name": "Ifrit: Healing Light",
        "Type": "Summon Magic",
        "Level": 5,
        "Target": "All Allies",
        "Power": 90,
        "Effect": "Restore target's HP",
        "effect_category": "heal_hp",
        "default_target_side": "Ally",
        "target_scope": "all",
    }
    party = [
        SimpleNamespace(name="Refia", stats=caster_stats, state=caster_state),
        SimpleNamespace(name="Ingus", stats=ally1_stats, state=ally1_state),
        SimpleNamespace(name="Arc", stats=ally2_stats, state=ally2_state),
    ]
    logs: list[str] = []

    expected_heal = magic_heal_amount_to_char(
        caster=caster_stats,
        spell=healing_light,
        rng=Random(0),
        use_expectation=False,
        target_count=3,
        spell_name="Ifrit: Healing Light",
    )

    damage, result = run_character_turn(
        char_name="Refia",
        enemy_name="Goblin",
        char_stats=caster_stats,
        enemy_stats=enemy_stats,
        enemy_json={},
        char_state=caster_state,
        enemy_state=enemy_state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=healing_light,
        char_spell_json=spell_json,
        char_spell_healing_type="hp",
        char_spell_name="Ifrit: Healing Light",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="ally",
        target_index=0,
        party_members=party,
        aoe_selected_override=False,
    )

    assert damage == 0
    assert result is None
    assert ally1_state.hp - 100 == expected_heal
    assert ally2_state.hp - 200 == expected_heal
