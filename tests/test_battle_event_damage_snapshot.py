from __future__ import annotations

from combat.battle_sim import (
    _annotate_block_damage_display_values,
    _append_enemy_diff_events,
)
from combat.models import BattleActorState, EnemyRuntime, FinalEnemyStats


def test_append_enemy_diff_events_records_old_and_new_hp() -> None:
    enemy = EnemyRuntime(
        name="Goblin",
        stats=FinalEnemyStats(
            name="Goblin",
            hp=50,
            level=1,
            job_level=1,
            attack_power=1,
            attack_multiplier=1,
            accuracy_percent=1,
            defense=1,
            defense_multiplier=0,
            evasion_percent=0,
            magic_defense=0,
            magic_def_multiplier=0,
            magic_resistance_percent=0,
            agility=1,
        ),
        state=BattleActorState(hp=30, max_hp=50),
        json={},
    )

    events: list[dict] = []
    block_events: list[dict] = []
    _append_enemy_diff_events(
        enemies=[enemy],
        old_hp_map=[40],
        old_status_map=[set()],
        events=events,
        actor_side="char",
        actor_index=0,
        focus_target_index=0,
        block_events=block_events,
    )

    assert events[0]["type"] == "damage"
    assert events[0]["value"] == 10
    assert events[0]["old_hp"] == 40
    assert events[0]["new_hp"] == 30
    assert block_events[0]["old_hp"] == 40
    assert block_events[0]["new_hp"] == 30


def test_annotate_block_damage_display_values_uses_logged_overkill_damage() -> None:
    enemy = EnemyRuntime(
        name="Goblin",
        stats=FinalEnemyStats(
            name="Goblin",
            hp=5,
            level=1,
            job_level=1,
            attack_power=1,
            attack_multiplier=1,
            accuracy_percent=1,
            defense=1,
            defense_multiplier=0,
            evasion_percent=0,
            magic_defense=0,
            magic_def_multiplier=0,
            magic_resistance_percent=0,
            agility=1,
        ),
        state=BattleActorState(hp=0, max_hp=5),
        json={},
        display_name="Goblin",
    )
    block_events = [
        {
            "type": "damage",
            "target_side": "enemy",
            "target_index": 0,
            "actor_side": "char",
            "actor_index": 0,
            "value": 5,
            "old_hp": 5,
            "new_hp": 0,
        }
    ]
    events = [dict(block_events[0])]

    _annotate_block_damage_display_values(
        block_events=block_events,
        all_events=events,
        logs=["Runethの物理攻撃！ Goblinに12のダメージ。（Goblin 残りHP: 0）"],
        party_members=[],
        enemies=[enemy],
    )

    assert block_events[0]["display_value"] == 12
    assert events[0]["display_value"] == 12
