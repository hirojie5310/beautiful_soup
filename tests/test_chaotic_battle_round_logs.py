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
from combat.runtime_state import init_runtime_state


def _member(
    *,
    name: str,
    agility: int,
    strength: int = 24,
    intelligence: int = 10,
    main_power: int = 40,
    max_hp: int = 999,
) -> PartyMemberRuntime:
    stats = FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=max_hp,
        strength=strength,
        agility=agility,
        vitality=12,
        intelligence=intelligence,
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
        strength=stats.strength,
        agility=stats.agility,
        vitality=stats.vitality,
        intelligence=stats.intelligence,
        mind=stats.mind,
    )
    state = BattleActorState(hp=stats.max_hp, max_hp=stats.max_hp)
    return PartyMemberRuntime(
        name=name,
        level=20,
        job=Job(name="Knight", slug="knight", earned="start", stats_by_level={}, raw={}),
        base=base,
        stats=stats,
        state=state,
    )


def _divide_enemy(*, hp: int = 120, agility: int = 5) -> EnemyRuntime:
    stats = FinalEnemyStats(
        name="Eater",
        hp=hp,
        level=30,
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
        agility=agility,
    )
    state = BattleActorState(hp=hp, max_hp=hp)
    return EnemyRuntime(
        name="Eater",
        stats=stats,
        state=state,
        json={
            "name": "Eater",
            "Level": 30,
            "Special Attacks": [{"Attack": "Divide", "Rate": 1.0}],
            "SpecialAttackRate": 0.4,
        },
    )


def test_chaotic_round_logs_divide_summon_aoe_and_skipped_party_action() -> None:
    state = init_runtime_state(Path("."))
    state.spells = {
        **state.spells,
        "Chaos Flare": {
            "Name": "Chaos Flare",
            "Type": "Black Magic",
            "Level": 1,
            "Target": "All Enemies",
            "Effect": "Deal Fire damage",
            "Element": "Fire",
            "BaseAccuracy": 1.0,
            "BasePower": 999,
        },
    }

    refia = _member(name="Refia", agility=40, main_power=40)
    arc = _member(name="Arc", agility=10, intelligence=99, main_power=10)
    arc.state.mp_pool[1] = 10
    arc.state.max_mp_pool[1] = 10
    ingus = _member(name="Ingus", agility=1, main_power=10)

    greater_demon = build_enemies(
        enemy_defs_by_name=state.monsters,
        spells_by_name=state.spells,
        enemy_names=["Greater Demon"],
    )[0]
    greater_demon.stats.agility = 20

    eater = _divide_enemy(hp=120, agility=5)
    enemies = [eater, greater_demon]

    logs, side_result, _events = simulate_one_round_multi_party(
        party_members=[refia, arc, ingus],
        enemies=enemies,
        planned_actions=[
            PlannedAction(
                kind="physical",
                command="Fight",
                target_side="enemy",
                target_index=0,
            ),
            PlannedAction(
                kind="magic",
                command="Magic",
                spell_name="Chaos Flare",
                target_side="enemy",
                target_index=0,
                target_all=True,
            ),
            PlannedAction(
                kind="physical",
                command="Fight",
                target_side="enemy",
                target_index=0,
            ),
        ],
        state=state,
        rng=Random(1),
        spells_by_name=state.spells,
    )

    assert side_result.end_reason == "enemy_defeated"
    assert any("▶ Refia の行動（Fight）" in line for line in logs)
    assert any("Eaterの《Divide》！ 同じ敵が現れた。" == line for line in logs)
    assert any("◆ Greater Demon の行動" in line for line in logs)
    assert any("Greater Demonの《Summon》！ Iron Clawsが現れた。" == line for line in logs)
    assert any("▶ Arc の行動（Magic）" in line for line in logs)
    assert any("▶ Ingus の行動（Fight）" in line for line in logs)
    assert any("Ingusは敵が全滅していたため行動できなかった。" in line for line in logs)
    assert len(enemies) >= 4
