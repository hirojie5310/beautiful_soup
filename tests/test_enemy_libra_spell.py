# tests/test_enemy_libra_spell.py
from random import Random
from typing import Any, cast

from combat.models import (
    BattleActorState,
    FinalCharacterStats,
    FinalEnemyStats,
    PartyMemberRuntime,
    PlannedEnemyAction,
)
from combat.runtime_state import RuntimeState
from combat.turn_logic import run_enemy_turn


def _char_stats() -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=1079,
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
        elemental_resists=frozenset({"fire"}),
        elemental_absorbs=frozenset({"ice"}),
        elemental_weaks=frozenset({"lightning"}),
    )


def _enemy_stats() -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Xande",
        hp=21000,
        level=50,
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


def _state() -> RuntimeState:
    return RuntimeState(
        monsters={},
        weapons={},
        armors={},
        spells={},
        items_by_name={},
        jobs_by_name={},
        save={},
    )


def test_enemy_libra_shows_hp_and_element_traits_without_damage() -> None:
    char_stats = _char_stats()
    enemy_stats = _enemy_stats()
    char_state = BattleActorState(hp=706, max_hp=1079)
    enemy_state = BattleActorState(hp=21000, max_hp=21000)
    logs: list[str] = []
    libra_spell = {
        "Name": "Libra",
        "Power": 999,
        "Multiplier": 1,
        "Accuracy": 1.0,
        "Reflectable": "No",
        "Target": "One Enemy",
    }

    result = run_enemy_turn(
        char_name="Ingus",
        enemy_name="Xande",
        char_stats=char_stats,
        enemy_stats=enemy_stats,
        enemy_json={
            "SpecialAttackRate": 1.0,
            "Special Attacks": [{"Attack": "Libra", "Rate": 1.0}],
            "Spells": [libra_spell],
        },
        char_state=char_state,
        enemy_state=enemy_state,
        char_attack_kind="physical",
        dmg_to_enemy=0,
        char_conf=False,
        char_is_mini_or_toad=False,
        logs=logs,
        state=_state(),
        rng=Random(0),
        party_members=[
            PartyMemberRuntime(
                name="Ingus",
                level=char_stats.level,
                job=cast(Any, None),
                base=cast(Any, None),
                stats=char_stats,
                state=char_state,
            )
        ],
        planned_enemy_action=PlannedEnemyAction(
            kind="special", spell_name="Libra", spell_json=libra_spell
        ),
    )

    assert result.end_reason == "continue"
    assert char_state.hp == 706
    assert any("Xandeの《Libra》！" in line for line in logs)
    assert any("IngusのHPは706/1079だ。" in line for line in logs)
    assert any("IngusはLightning属性に弱い。" in line for line in logs)
    assert any("IngusはIce属性を吸収する。" in line for line in logs)
    assert any("IngusはFire属性に強い。" in line for line in logs)
