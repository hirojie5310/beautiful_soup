from pathlib import Path
from random import Random

from combat.battle_sim import simulate_one_round_multi_party
from combat.enemy_build import build_enemies
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
from combat.runtime_state import RuntimeState, init_runtime_state


def _member(
    *,
    name: str = "Refia",
    agility: int = 20,
    main_power: int = 40,
) -> PartyMemberRuntime:
    stats = FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=999,
        strength=24,
        agility=agility,
        vitality=12,
        intelligence=10,
        mind=10,
        row="front",
        main_power=main_power,
        main_accuracy=100,
        main_atk_multiplier=2,
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
    base = BaseCharacter(
        level=20,
        total_exp=0,
        job_level=20,
        job_skill_point=0,
        max_hp=stats.max_hp,
        strength=24,
        agility=agility,
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


def _divide_enemy(*, hp: int = 120, level: int = 30) -> EnemyRuntime:
    stats = FinalEnemyStats(
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


def _action_headers(logs: list[str]) -> list[str]:
    return [line for line in logs if line.startswith("▶ ") or line.startswith("◆ ")]


def test_summoned_enemy_acts_and_has_event_block_on_followup_round() -> None:
    state = init_runtime_state(Path("."))
    member = _member()
    enemies = build_enemies(
        enemy_defs_by_name=state.monsters,
        spells_by_name=state.spells,
        enemy_names=["Greater Demon"],
    )

    first_logs, first_result, _first_events = simulate_one_round_multi_party(
        party_members=[member],
        enemies=enemies,
        planned_actions=[PlannedAction(kind="defend", command="Defend", target_side="self")],
        state=state,
        rng=Random(1),
    )

    assert first_result.end_reason == "continue"
    assert any("Greater Demonの《Summon》！ Iron Clawsが現れた。" == line for line in first_logs)
    assert len(enemies) == 2
    assert enemies[1].name == "Iron Claws"

    second_logs, second_result, _second_events = simulate_one_round_multi_party(
        party_members=[member],
        enemies=enemies,
        planned_actions=[PlannedAction(kind="defend", command="Defend", target_side="self")],
        state=state,
        rng=Random(0),
    )

    headers = _action_headers(second_logs)
    assert second_result.end_reason == "continue"
    assert "◆ Greater Demon の行動" in headers
    iron_claws_headers = [header for header in headers if header.startswith("◆ Iron Claws")]
    assert iron_claws_headers
    assert len(second_result.event_blocks) == len(headers)

    greater_idx = headers.index("◆ Greater Demon の行動")
    iron_claws_idx = headers.index(iron_claws_headers[0])
    assert second_result.event_blocks[greater_idx]
    assert second_result.event_blocks[iron_claws_idx]


def test_divided_enemy_acts_and_has_event_block_on_followup_round() -> None:
    member = _member(main_power=40)
    enemies = [_divide_enemy()]

    first_logs, first_result, _first_events = simulate_one_round_multi_party(
        party_members=[member],
        enemies=enemies,
        planned_actions=[
            PlannedAction(kind="physical", command="Fight", target_side="enemy", target_index=0)
        ],
        state=_runtime_state(),
        rng=Random(0),
    )

    assert first_result.end_reason == "continue"
    assert any("Eaterの《Divide》！ 同じ敵が現れた。" == line for line in first_logs)
    assert len(enemies) == 2
    assert enemies[0].label == "Eater A"
    assert enemies[1].label == "Eater B"

    second_logs, second_result, _second_events = simulate_one_round_multi_party(
        party_members=[member],
        enemies=enemies,
        planned_actions=[PlannedAction(kind="defend", command="Defend", target_side="self")],
        state=_runtime_state(),
        rng=Random(0),
    )

    headers = _action_headers(second_logs)
    assert second_result.end_reason == "continue"
    assert "◆ Eater A の行動" in headers
    assert "◆ Eater B の行動" in headers
    assert len(second_result.event_blocks) == len(headers)

    eater_a_idx = headers.index("◆ Eater A の行動")
    eater_b_idx = headers.index("◆ Eater B の行動")
    assert second_result.event_blocks[eater_a_idx]
    assert second_result.event_blocks[eater_b_idx]
