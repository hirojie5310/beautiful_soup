# tests/test_item_and_ally_status_guarantees.py
from random import Random
from types import SimpleNamespace

from combat.enums import Status
from combat.item_effects import apply_item_effect_to_actor, apply_status_item_to_enemy
from combat.progression import apply_item_stock_to_inventory
from combat.models import (
    BattleActorState,
    FinalCharacterStats,
    FinalEnemyStats,
    SpellInfo,
)
from combat.turn_logic import run_character_turn


def _char_stats(*, max_hp: int = 999, mind: int = 1) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=max_hp,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=mind,
        row="front",
        main_power=10,
        main_accuracy=10,
        main_atk_multiplier=1,
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


def test_haste_item_is_guaranteed_even_with_high_rng_roll() -> None:
    target_stats = _char_stats(mind=1)
    target_state = BattleActorState(hp=200, max_hp=200)
    item_json = {
        "Name": "Bacchus's Cider",
        "SpellEffect": "Haste",
        "SpellInfo": {
            "Effect": "Enhance Accuracy and Attack Multiplier",
            "BasePower": 5,
            "BaseAccuracy": 0.1,
        },
    }
    logs: list[str] = []

    apply_item_effect_to_actor(
        item_json,
        target_state,
        target_name="Refia",
        max_hp=target_stats.max_hp,
        logs=logs,
        target_stats=target_stats,
        rng=Random(0),
        actor_name="Refia",
    )

    assert target_stats.haste_power_bonus > 0
    assert target_stats.haste_multiplier_bonus > 0
    assert any("上がった" in line for line in logs)


def test_status_item_is_guaranteed_even_when_base_accuracy_is_low() -> None:
    enemy_state = BattleActorState(hp=100, max_hp=100)
    item_json = {
        "Name": "Mallet Bomb",
        "SpellInfo": {
            "Effect": "Inflict Mini",
            "BaseAccuracy": 0.01,
        },
    }
    logs: list[str] = []

    handled = apply_status_item_to_enemy(
        item_json=item_json,
        enemy_state=enemy_state,
        enemy_name="Goblin",
        rng=Random(0),
        logs=logs,
    )

    assert handled is True
    assert Status.MINI in enemy_state.statuses
    assert any("効いた" in line for line in logs)


def test_shining_curtain_is_guaranteed_to_apply_reflect() -> None:
    caster_stats = _char_stats()
    target_stats = _char_stats()
    enemy_stats = _enemy_stats()
    caster_state = BattleActorState(hp=300, max_hp=300)
    target_state = BattleActorState(hp=250, max_hp=250)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    party = [
        SimpleNamespace(name="Refia", stats=caster_stats, state=caster_state),
        SimpleNamespace(name="Ingus", stats=target_stats, state=target_state),
    ]
    save = {"inventory": {"Combat": {"Shining Curtain": 1}}}
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Refia",
        enemy_name="Goblin",
        char_stats=caster_stats,
        enemy_stats=enemy_stats,
        enemy_json={},
        char_state=caster_state,
        enemy_state=enemy_state,
        char_attack_kind="item",
        char_battle_command="Item",
        char_weapon_hand="main",
        char_spell=None,
        char_spell_json=None,
        char_spell_healing_type=None,
        char_spell_name=None,
        char_item={
            "Name": "Shining Curtain",
            "SpellInfo": {"Effect": "Grant Reflect", "BaseAccuracy": 0.01},
        },
        logs=logs,
        rng=Random(0),
        target_side="ally",
        target_index=1,
        party_members=party,
        save=save,
    )

    assert damage == 0
    assert result is None
    assert target_state.reflect_charges == 1
    assert save["inventory"]["Combat"] == {}


def test_ally_targeted_toad_is_guaranteed_to_apply_status() -> None:
    caster_stats = _char_stats()
    target_stats = _char_stats()
    enemy_stats = _enemy_stats()
    caster_state = BattleActorState(hp=300, max_hp=300)
    caster_state.mp_pool[3] = 1
    caster_state.max_mp_pool[3] = 1
    target_state = BattleActorState(hp=250, max_hp=250)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    party = [
        SimpleNamespace(name="Refia", stats=caster_stats, state=caster_state),
        SimpleNamespace(name="Ingus", stats=target_stats, state=target_state),
    ]
    logs: list[str] = []

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
        char_spell=SpellInfo(
            power=0,
            accuracy_percent=1,
            magic_type="white",
            elements=[],
        ),
        char_spell_json={
            "Name": "Toad",
            "Type": "White Magic",
            "Level": 3,
            "Target": "One Ally",
            "Effect": "Turn target into a toad",
        },
        char_spell_healing_type=None,
        char_spell_name="Toad",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="ally",
        target_index=1,
        party_members=party,
    )

    assert damage == 0
    assert result is None
    assert Status.TOAD in target_state.statuses
    assert caster_state.mp_pool[3] == 0
    assert any("TOAD状態" in line for line in logs)


def test_apply_item_stock_to_inventory_routes_by_item_type_and_equipment() -> None:
    save = {
        "inventory": {
            "Anywhere": {"Potion": 5},
            "Combat": {"Lamia Scale": 2, "Lilith's Kiss": 2},
            "Equipment": {"Onion Sword": 1},
        },
        "item_stock": {
            "Lamia Scale": 1,
            "Lilith's Kiss": 1,
            "Onion Helm": 1,
        },
    }

    apply_item_stock_to_inventory(save)

    assert save["inventory"]["Combat"]["Lamia Scale"] == 3
    assert save["inventory"]["Combat"]["Lilith's Kiss"] == 3
    assert save["inventory"]["Equipment"]["Onion Helm"] == 1
    assert "Lamia Scale" not in save["inventory"]["Anywhere"]
    assert "Lilith's Kiss" not in save["inventory"]["Anywhere"]
    assert "Onion Helm" not in save["inventory"]["Anywhere"]
    assert save["item_stock"] == {}
