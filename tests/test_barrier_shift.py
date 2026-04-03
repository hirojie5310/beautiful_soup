from pathlib import Path
from random import Random
from types import SimpleNamespace

from combat.enemy_build import build_enemies
from combat.battle_sim import simulate_one_round_multi_party, _plan_enemy_action
from combat.elements import element_relation_and_hits_for_monster
from combat.models import (
    BattleActorState,
    FinalCharacterStats,
    FinalEnemyStats,
    PartyMemberRuntime,
    PlannedAction,
    PlannedEnemyAction,
)
from combat.runtime_state import RuntimeState, init_runtime_state
from combat.turn_logic import run_enemy_turn


def _runtime_state() -> RuntimeState:
    return RuntimeState(
        monsters={},
        weapons={},
        armors={},
        spells={},
        items_by_name={},
        jobs_by_name={},
        save={},
        base_dir=Path("."),
    )


def _char_stats() -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=999,
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


def _enemy_stats(name: str = "Hein") -> FinalEnemyStats:
    return FinalEnemyStats(
        name=name,
        hp=1600,
        level=13,
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


def test_plan_enemy_action_initializes_barrier_and_uses_it_three_rounds_after_initial_state() -> None:
    enemy_json = {
        "name": "Hein",
        "SpecialAttackRate": 1.0,
        "Special Attacks": [
            {"Attack": "Fira", "Rate": 1.0},
            {"Attack": "Barrier Shift (every third round)", "Rate": 1.0},
        ],
        "Spells": [
            {"Name": "Fira"},
            {"Name": "Barrier Shift"},
        ],
        "ElementalVulnerability": {
            "Absorb": ["Fire", "Ice", "Lightning", "Air", "Earth", "Holy", "Dark"]
        },
    }

    first = _plan_enemy_action(enemy_json=enemy_json, state=_runtime_state(), rng=Random(0))
    second = _plan_enemy_action(
        enemy_json=enemy_json,
        state=_runtime_state(),
        rng=Random(1),
    )
    third = _plan_enemy_action(enemy_json=enemy_json, state=_runtime_state(), rng=Random(2))
    fourth = _plan_enemy_action(enemy_json=enemy_json, state=_runtime_state(), rng=Random(3))

    current = enemy_json["_battle_elemental_vulnerability"]
    weakness = current["Weakness"][0]

    assert first.kind in ("normal", "special")
    assert second.kind in ("normal", "special")
    assert third.kind in ("normal", "special")
    assert weakness in ("fire", "ice", "lightning")
    assert fourth == PlannedEnemyAction(
        kind="special",
        spell_name="Barrier Shift",
        spell_json={"Name": "Barrier Shift"},
    )


def test_barrier_shift_spell_updates_enemy_vulnerability_without_damage() -> None:
    char_stats = _char_stats()
    enemy_stats = _enemy_stats()
    char_state = BattleActorState(hp=500, max_hp=999)
    enemy_state = BattleActorState(hp=1600, max_hp=1600)
    enemy_json = {
        "name": "Hein",
        "SpecialAttackRate": 1.0,
        "Special Attacks": [{"Attack": "Barrier Shift (every third round)", "Rate": 1.0}],
        "Spells": [{"Name": "Barrier Shift", "Reflectable": "No", "Target": "One Enemy"}],
        "ElementalVulnerability": {
            "Absorb": [
                "Fire",
                "Ice",
                "Lightning",
                "Air",
                "Earth",
                "Holy",
                "Dark",
                "Recovery",
            ]
        },
    }
    logs: list[str] = []

    result = run_enemy_turn(
        char_name="Refia",
        enemy_name="Hein",
        char_stats=char_stats,
        enemy_stats=enemy_stats,
        enemy_json=enemy_json,
        char_state=char_state,
        enemy_state=enemy_state,
        char_attack_kind="physical",
        dmg_to_enemy=0,
        char_conf=False,
        char_is_mini_or_toad=False,
        logs=logs,
        state=_runtime_state(),
        rng=Random(0),
        party_members=[
            PartyMemberRuntime(
                name="Refia",
                level=char_stats.level,
                job=None,  # type: ignore[arg-type]
                base=None,  # type: ignore[arg-type]
                stats=char_stats,
                state=char_state,
            )
        ],
        planned_enemy_action=PlannedEnemyAction(
            kind="special",
            spell_name="Barrier Shift",
            spell_json={"Name": "Barrier Shift", "Reflectable": "No", "Target": "One Enemy"},
        ),
    )

    current = enemy_json["_battle_elemental_vulnerability"]
    weakness = current["Weakness"][0]
    relation, hits = element_relation_and_hits_for_monster(enemy_json, [weakness])

    assert result.end_reason == "continue"
    assert char_state.hp == 500
    assert relation == "weak"
    assert hits == [weakness]
    assert any("Barrier Shift" in line for line in logs)


def test_barrier_shift_override_changes_element_relation() -> None:
    enemy_json = {
        "ElementalVulnerability": {"Absorb": ["Fire", "Ice", "Lightning"]},
        "_battle_elemental_vulnerability": {
            "Weakness": ["fire"],
            "Absorb": ["ice", "lightning"],
        },
    }

    fire_relation, fire_hits = element_relation_and_hits_for_monster(enemy_json, ["fire"])
    ice_relation, ice_hits = element_relation_and_hits_for_monster(enemy_json, ["ice"])

    assert fire_relation == "weak"
    assert fire_hits == ["fire"]
    assert ice_relation == "absorb"
    assert ice_hits == ["ice"]


def test_amon_uses_barrier_shift_on_fourth_round_after_initial_state() -> None:
    state = init_runtime_state(Path("."))

    enemies = build_enemies(
        enemy_defs_by_name=state.monsters,
        spells_by_name=state.spells,
        enemy_names=["Amon"],
    )

    char_stats = FinalCharacterStats(
        level=50,
        job_level=50,
        job_skill_point=0,
        max_hp=9999,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=10,
        row="front",
        main_power=1,
        main_accuracy=99,
        main_atk_multiplier=1,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=0,
        off_two=False,
        off_long=False,
        defense=200,
        defense_multiplier=10,
        evasion_percent=50,
        magic_defense=200,
        magic_def_multiplier=10,
        magic_resistance=50,
        shield_count=0,
    )
    party = [
        PartyMemberRuntime(
            name="Test",
            level=50,
            job=SimpleNamespace(raw={}),
            base=SimpleNamespace(level=50, job_level=50),
            stats=char_stats,
            state=BattleActorState(hp=9999, max_hp=9999),
        )
    ]
    actions = [PlannedAction(kind="defend", command="Defend")]

    fourth_turn_logs: list[str] = []
    for turn in range(1, 5):
        logs, result, _ = simulate_one_round_multi_party(
            party_members=party,
            enemies=enemies,
            planned_actions=actions,
            state=state,
            rng=Random(turn),
            save=state.save,
            spells_by_name=state.spells,
            items_by_name=state.items_by_name,
        )
        if turn == 4:
            fourth_turn_logs = logs
        assert result.end_reason == "continue"

    assert any("Amonの《Barrier Shift》！" in line for line in fourth_turn_logs)
    assert enemies[0].json["_battle_round_counter"] == 3
    assert enemies[0].json["_battle_elemental_vulnerability"]["Weakness"][0] in (
        "fire",
        "ice",
        "lightning",
    )


def test_hein_announces_initial_barrier_shift_state_in_first_round() -> None:
    state = init_runtime_state(Path("."))

    enemies = build_enemies(
        enemy_defs_by_name=state.monsters,
        spells_by_name=state.spells,
        enemy_names=["Hein"],
    )

    char_stats = FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=9999,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=10,
        row="front",
        main_power=1,
        main_accuracy=99,
        main_atk_multiplier=1,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=0,
        off_two=False,
        off_long=False,
        defense=200,
        defense_multiplier=10,
        evasion_percent=50,
        magic_defense=200,
        magic_def_multiplier=10,
        magic_resistance=50,
        shield_count=0,
    )
    party = [
        PartyMemberRuntime(
            name="Test",
            level=20,
            job=SimpleNamespace(raw={}),
            base=SimpleNamespace(level=20, job_level=20),
            stats=char_stats,
            state=BattleActorState(hp=9999, max_hp=9999),
        )
    ]
    actions = [PlannedAction(kind="defend", command="Defend")]

    logs, result, _ = simulate_one_round_multi_party(
        party_members=party,
        enemies=enemies,
        planned_actions=actions,
        state=state,
        rng=Random(1),
        save=state.save,
        spells_by_name=state.spells,
        items_by_name=state.items_by_name,
    )

    assert result.end_reason == "continue"
    assert any("Heinの《Barrier Shift》！" in line for line in logs)
    assert not any("属性が弱点になった" in line for line in logs)


def test_initial_barrier_shift_log_appears_before_character_libra() -> None:
    state = init_runtime_state(Path("."))

    enemies = build_enemies(
        enemy_defs_by_name=state.monsters,
        spells_by_name=state.spells,
        enemy_names=["Hein"],
    )

    char_stats = FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=9999,
        strength=10,
        agility=99,
        vitality=10,
        intelligence=10,
        mind=10,
        row="front",
        main_power=1,
        main_accuracy=99,
        main_atk_multiplier=1,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=0,
        off_two=False,
        off_long=False,
        defense=200,
        defense_multiplier=10,
        evasion_percent=50,
        magic_defense=200,
        magic_def_multiplier=10,
        magic_resistance=50,
        shield_count=0,
    )
    party = [
        PartyMemberRuntime(
            name="Runeth",
            level=20,
            job=SimpleNamespace(raw={}),
            base=SimpleNamespace(level=20, job_level=20),
            stats=char_stats,
            state=BattleActorState(hp=9999, max_hp=9999),
        )
    ]
    party[0].state.mp_pool[4] = 24
    party[0].state.max_mp_pool[4] = 24
    actions = [
        PlannedAction(
            kind="magic",
            command="Magic",
            spell_name="Libra",
            target_side="enemy",
            target_index=0,
        )
    ]

    logs, result, _ = simulate_one_round_multi_party(
        party_members=party,
        enemies=enemies,
        planned_actions=actions,
        state=state,
        rng=Random(1),
        save=state.save,
        spells_by_name=state.spells,
        items_by_name=state.items_by_name,
    )

    assert result.end_reason == "continue"
    barrier_idx = next(
        i for i, line in enumerate(logs) if "Heinの《Barrier Shift》！" in line
    )
    libra_idx = next(i for i, line in enumerate(logs) if "Runethは《Libra》を唱えた！" in line)
    assert barrier_idx < libra_idx


def test_scheduled_barrier_shift_log_appears_before_character_libra_on_fourth_round() -> None:
    state = init_runtime_state(Path("."))

    enemies = build_enemies(
        enemy_defs_by_name=state.monsters,
        spells_by_name=state.spells,
        enemy_names=["Hein"],
    )

    char_stats = FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=9999,
        strength=10,
        agility=99,
        vitality=10,
        intelligence=10,
        mind=10,
        row="front",
        main_power=1,
        main_accuracy=99,
        main_atk_multiplier=1,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=0,
        off_two=False,
        off_long=False,
        defense=200,
        defense_multiplier=10,
        evasion_percent=50,
        magic_defense=200,
        magic_def_multiplier=10,
        magic_resistance=50,
        shield_count=0,
    )
    member_state = BattleActorState(hp=9999, max_hp=9999)
    member_state.mp_pool[4] = 24
    member_state.max_mp_pool[4] = 24
    party = [
        PartyMemberRuntime(
            name="Runeth",
            level=20,
            job=SimpleNamespace(raw={}),
            base=SimpleNamespace(level=20, job_level=20),
            stats=char_stats,
            state=member_state,
        )
    ]

    defend = [PlannedAction(kind="defend", command="Defend")]
    for turn in range(1, 4):
        logs, result, _ = simulate_one_round_multi_party(
            party_members=party,
            enemies=enemies,
            planned_actions=defend,
            state=state,
            rng=Random(turn),
            save=state.save,
            spells_by_name=state.spells,
            items_by_name=state.items_by_name,
        )
        assert result.end_reason == "continue"

    fourth_actions = [
        PlannedAction(
            kind="magic",
            command="Magic",
            spell_name="Libra",
            target_side="enemy",
            target_index=0,
        )
    ]
    logs, result, _ = simulate_one_round_multi_party(
        party_members=party,
        enemies=enemies,
        planned_actions=fourth_actions,
        state=state,
        rng=Random(4),
        save=state.save,
        spells_by_name=state.spells,
        items_by_name=state.items_by_name,
    )

    assert result.end_reason == "continue"
    barrier_idx = next(
        i for i, line in enumerate(logs) if "Heinの《Barrier Shift》！" in line
    )
    libra_idx = next(i for i, line in enumerate(logs) if "Runethは《Libra》を唱えた！" in line)
    assert barrier_idx < libra_idx
