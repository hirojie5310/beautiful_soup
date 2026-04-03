from pathlib import Path
from random import Random

from combat.battle_sim import simulate_one_round_multi_party
from combat.enemy_build import build_enemies
from combat.models import (
    BaseCharacter,
    BattleActorState,
    FinalCharacterStats,
    Job,
    PartyMemberRuntime,
    PlannedAction,
)
from combat.runtime_state import init_runtime_state


def _member(*, name: str = "Refia") -> PartyMemberRuntime:
    stats = FinalCharacterStats(
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
        main_power=40,
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


def _state():
    return init_runtime_state(Path("."))


def test_greater_demon_summon_adds_iron_claws() -> None:
    state = _state()
    member = _member()
    enemies = build_enemies(
        enemy_defs_by_name=state.monsters,
        spells_by_name=state.spells,
        enemy_names=["Greater Demon"],
    )

    logs, side_result, _events = simulate_one_round_multi_party(
        party_members=[member],
        enemies=enemies,
        planned_actions=[
            PlannedAction(
                kind="defend",
                command="Defend",
                target_side="self",
            )
        ],
        state=state,
        rng=Random(1),
    )

    assert side_result.end_reason == "continue"
    assert len(enemies) == 2
    assert enemies[0].name == "Greater Demon"
    assert enemies[1].name == "Iron Claws"
    assert enemies[1].state.hp == enemies[1].state.max_hp
    assert any("Greater Demonの《Summon》！ Iron Clawsが現れた。" == line for line in logs)


def test_bluck_summon_reuses_dead_slot_and_refreshes_labels() -> None:
    state = _state()
    member = _member()
    enemies = build_enemies(
        enemy_defs_by_name=state.monsters,
        spells_by_name=state.spells,
        enemy_names=["Greater Demon", "Bluck", "Greater Demon"],
    )
    enemies[0].state.hp = 0

    logs, side_result, _events = simulate_one_round_multi_party(
        party_members=[member],
        enemies=enemies,
        planned_actions=[
            PlannedAction(
                kind="defend",
                command="Defend",
                target_side="self",
            )
        ],
        state=state,
        rng=Random(20),
    )

    assert side_result.end_reason == "continue"
    assert len(enemies) == 3
    assert [enemy.name for enemy in enemies].count("Kum Kum") == 1
    assert enemies[0].name == "Kum Kum"
    assert enemies[1].label == "Bluck"
    assert enemies[2].label == "Greater Demon"
    assert any("Bluckの《Summon》！ Kum Kumが現れた。" == line for line in logs)


def test_summon_respects_six_enemy_cap() -> None:
    state = _state()
    member = _member()
    enemies = build_enemies(
        enemy_defs_by_name=state.monsters,
        spells_by_name=state.spells,
        enemy_names=[
            "Greater Demon",
            "Greater Demon",
            "Greater Demon",
            "Greater Demon",
            "Greater Demon",
            "Greater Demon",
        ],
    )

    logs, side_result, _events = simulate_one_round_multi_party(
        party_members=[member],
        enemies=enemies,
        planned_actions=[
            PlannedAction(
                kind="defend",
                command="Defend",
                target_side="self",
            )
        ],
        state=state,
        rng=Random(1),
    )

    assert side_result.end_reason == "continue"
    assert len(enemies) == 6
    assert any("しかしこれ以上は呼び出せない" in line for line in logs)
