from pathlib import Path
from random import Random

from combat.battle_sim import simulate_one_round_multi_party
from combat.models import (
    BaseCharacter,
    BattleActorState,
    EnemyRuntime,
    FinalCharacterStats,
    FinalEnemyStats,
    Job,
    PartyMemberRuntime,
    PlannedAction,
)
from combat.runtime_state import RuntimeState
from combat.turn_logic import run_character_turn
from combat.enums import Status


def _char_stats(
    *,
    power: int = 40,
    accuracy: int = 100,
    multiplier: int = 2,
    weapon_elements: list[str] | None = None,
) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=999,
        strength=24,
        agility=20,
        vitality=12,
        intelligence=10,
        mind=10,
        row="front",
        main_power=power,
        main_accuracy=accuracy,
        main_atk_multiplier=multiplier,
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
        main_weapon_elements=list(weapon_elements or []),
    )


def _enemy_stats(*, hp: int = 120, level: int = 30) -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Eater",
        hp=hp,
        level=level,
        job_level=1,
        attack_power=1,
        attack_multiplier=1,
        accuracy_percent=1,
        defense=2,
        defense_multiplier=0,
        evasion_percent=0,
        magic_defense=1,
        magic_def_multiplier=1,
        magic_resistance_percent=0,
        agility=1,
    )


def _divide_enemy(*, hp: int = 120, level: int = 30) -> EnemyRuntime:
    stats = _enemy_stats(hp=hp, level=level)
    state = BattleActorState(hp=hp, max_hp=hp)
    return EnemyRuntime(
        name="Eater",
        stats=stats,
        state=state,
        json={
            "name": "Eater",
            "Level": level,
            "Special Attacks": [{"Attack": "Divide", "Rate": 1.0}],
            "SpecialAttackRate": 0.4,
        },
    )


def _member(*, name: str = "Refia", weapon_elements: list[str] | None = None) -> PartyMemberRuntime:
    stats = _char_stats(weapon_elements=weapon_elements)
    base = BaseCharacter(
        level=20,
        total_exp=0,
        job_level=20,
        job_skill_point=0,
        max_hp=stats.max_hp,
        strength=24,
        agility=20,
        vitality=12,
        intelligence=10,
        mind=10,
    )
    return PartyMemberRuntime(
        name=name,
        level=20,
        job=Job(name="Knight", slug="knight", earned="start", stats_by_level={}, raw={}),
        base=base,
        stats=stats,
        state=BattleActorState(hp=stats.max_hp, max_hp=stats.max_hp),
    )


def _runtime_state() -> RuntimeState:
    return RuntimeState(
        monsters={},
        weapons={},
        armors={},
        spells={},
        items_by_name={},
        jobs_by_name={},
        save={"party": [{"name": "Refia"}]},
        base_dir=Path("."),
    )


def test_non_dark_physical_attack_triggers_divide_and_clears_statuses() -> None:
    char_stats = _char_stats()
    char_state = BattleActorState(hp=999, max_hp=999)
    enemy = _divide_enemy()
    enemy.state.statuses.add(Status.TOAD)
    logs: list[str] = []
    enemies = [enemy]

    damage, result = run_character_turn(
        char_name="Refia",
        enemy_name=enemy.name,
        char_stats=char_stats,
        enemy_stats=enemy.stats,
        enemy_json=enemy.json,
        char_state=char_state,
        enemy_state=enemy.state,
        char_attack_kind="physical",
        char_battle_command="Fight",
        char_weapon_hand="main",
        char_spell=None,
        char_spell_json=None,
        char_spell_healing_type=None,
        char_spell_name=None,
        char_item=None,
        logs=logs,
        rng=Random(0),
        enemies=enemies,
        target_side="enemy",
        target_index=0,
    )

    assert result is None
    assert damage > 0
    assert len(enemies) == 2
    assert enemies[0].label == "Eater A"
    assert enemies[1].label == "Eater B"
    assert enemies[1].state.hp == enemies[0].state.hp
    assert enemies[1].state.max_hp == enemies[0].state.max_hp
    assert enemies[1].state.statuses == set()
    assert any("Divide" in line for line in logs)


def test_dark_physical_attack_does_not_trigger_divide() -> None:
    char_stats = _char_stats(weapon_elements=["dark"])
    char_state = BattleActorState(hp=999, max_hp=999)
    enemy = _divide_enemy()
    logs: list[str] = []
    enemies = [enemy]

    damage, result = run_character_turn(
        char_name="Refia",
        enemy_name=enemy.name,
        char_stats=char_stats,
        enemy_stats=enemy.stats,
        enemy_json=enemy.json,
        char_state=char_state,
        enemy_state=enemy.state,
        char_attack_kind="physical",
        char_battle_command="Fight",
        char_weapon_hand="main",
        char_spell=None,
        char_spell_json=None,
        char_spell_healing_type=None,
        char_spell_name=None,
        char_item=None,
        logs=logs,
        rng=Random(0),
        enemies=enemies,
        target_side="enemy",
        target_index=0,
    )

    assert result is None
    assert damage > 0
    assert len(enemies) == 1
    assert not any("Divide" in line for line in logs)


def test_lethal_physical_attack_does_not_trigger_divide() -> None:
    char_stats = _char_stats(power=300, multiplier=4)
    char_state = BattleActorState(hp=999, max_hp=999)
    enemy = _divide_enemy(hp=50)
    logs: list[str] = []
    enemies = [enemy]

    damage, result = run_character_turn(
        char_name="Refia",
        enemy_name=enemy.name,
        char_stats=char_stats,
        enemy_stats=enemy.stats,
        enemy_json=enemy.json,
        char_state=char_state,
        enemy_state=enemy.state,
        char_attack_kind="physical",
        char_battle_command="Fight",
        char_weapon_hand="main",
        char_spell=None,
        char_spell_json=None,
        char_spell_healing_type=None,
        char_spell_name=None,
        char_item=None,
        logs=logs,
        rng=Random(0),
        enemies=enemies,
        target_side="enemy",
        target_index=0,
    )

    assert result is None
    assert damage >= 50
    assert enemy.state.hp == 0
    assert len(enemies) == 1
    assert not any("Divide" in line for line in logs)


def test_divide_respects_six_enemy_cap() -> None:
    member = _member()
    enemies = [_divide_enemy() for _ in range(6)]
    for i, enemy in enumerate(enemies):
        enemy.display_name = f"Eater {i + 1}"

    logs, side_result, _events = simulate_one_round_multi_party(
        party_members=[member],
        enemies=enemies,
        planned_actions=[
            PlannedAction(
                kind="physical",
                command="Fight",
                target_side="enemy",
                target_index=0,
            )
        ],
        state=_runtime_state(),
        rng=Random(0),
    )

    assert side_result.end_reason == "continue"
    assert len(enemies) == 6
    assert not any("Divide" in line for line in logs)


def test_simulate_round_handles_divide_without_event_diff_crash() -> None:
    member = _member()
    enemies = [_divide_enemy()]

    logs, side_result, events = simulate_one_round_multi_party(
        party_members=[member],
        enemies=enemies,
        planned_actions=[
            PlannedAction(
                kind="physical",
                command="Fight",
                target_side="enemy",
                target_index=0,
            )
        ],
        state=_runtime_state(),
        rng=Random(0),
    )

    assert side_result.end_reason == "continue"
    assert len(enemies) == 2
    assert any("Divide" in line for line in logs)
    assert isinstance(events, list)


def test_divide_is_not_selected_as_enemy_turn_special() -> None:
    member = _member()
    enemies = [_divide_enemy(), _divide_enemy()]

    logs, side_result, _events = simulate_one_round_multi_party(
        party_members=[member],
        enemies=enemies,
        planned_actions=[
            PlannedAction(
                kind="physical",
                command="Fight",
                target_side="enemy",
                target_index=0,
            )
        ],
        state=_runtime_state(),
        rng=Random(0),
    )

    assert side_result.end_reason == "continue"
    assert len(enemies) == 3
    assert sum(1 for line in logs if "《Divide》" in line) == 1


def test_divide_log_stays_generic_when_reusing_earlier_dead_slot() -> None:
    char_stats = _char_stats()
    char_state = BattleActorState(hp=999, max_hp=999)
    dead_enemy = _divide_enemy()
    dead_enemy.state.hp = 0
    source_enemy = _divide_enemy()
    source_enemy.display_name = "Eater A"
    later_enemy = _divide_enemy()
    later_enemy.display_name = "Eater B"
    logs: list[str] = []
    enemies = [dead_enemy, source_enemy, later_enemy]

    damage, result = run_character_turn(
        char_name="Refia",
        enemy_name=source_enemy.label,
        char_stats=char_stats,
        enemy_stats=source_enemy.stats,
        enemy_json=source_enemy.json,
        char_state=char_state,
        enemy_state=source_enemy.state,
        char_attack_kind="physical",
        char_battle_command="Fight",
        char_weapon_hand="main",
        char_spell=None,
        char_spell_json=None,
        char_spell_healing_type=None,
        char_spell_name=None,
        char_item=None,
        logs=logs,
        rng=Random(0),
        enemies=enemies,
        target_side="enemy",
        target_index=1,
    )

    assert result is None
    assert damage > 0
    assert any(line == "Eaterの《Divide》！ 同じ敵が現れた。" for line in logs)
