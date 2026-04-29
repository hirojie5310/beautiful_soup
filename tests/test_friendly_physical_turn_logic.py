# tests/test_friendly_physical_turn_logic.py
from random import Random
from types import SimpleNamespace

from combat.models import BattleActorState, FinalCharacterStats, FinalEnemyStats, SpellInfo
from combat.phys_damage import physical_damage_char_to_enemy
from combat.turn_logic import run_character_turn


def test_turn_logic_module_imports_cleanly() -> None:
    from combat.turn_logic import run_character_turn as imported

    assert imported is run_character_turn


def _char_stats(
    *,
    row: str = "front",
    main_power: int = 20,
    main_accuracy: int = 100,
    main_atk_multiplier: int = 2,
    off_power: int = 0,
    off_accuracy: int = 0,
    off_atk_multiplier: int = 1,
    defense: int = 50,
) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=999,
        strength=20,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=10,
        row=row,
        main_power=main_power,
        main_accuracy=main_accuracy,
        main_atk_multiplier=main_atk_multiplier,
        main_two=False,
        main_long=False,
        off_power=off_power,
        off_accuracy=off_accuracy,
        off_atk_multiplier=off_atk_multiplier,
        off_two=False,
        off_long=False,
        defense=defense,
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


def test_physical_attack_to_ally_does_not_use_target_defense() -> None:
    attacker_stats = _char_stats(main_power=20, defense=0)
    ally_stats = _char_stats(main_power=5, defense=80)
    enemy_stats = _enemy_stats()
    attacker_state = BattleActorState(hp=999, max_hp=999)
    ally_state = BattleActorState(hp=120, max_hp=999)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    party = [
        SimpleNamespace(name="Refia", stats=attacker_stats, state=attacker_state),
        SimpleNamespace(name="Ingus", stats=ally_stats, state=ally_state),
    ]
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Refia",
        enemy_name="Goblin",
        char_stats=attacker_stats,
        enemy_stats=enemy_stats,
        enemy_json={},
        char_state=attacker_state,
        enemy_state=enemy_state,
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
        target_side="ally",
        target_index=1,
        party_members=party,
    )

    assert damage == 0
    assert result is None
    assert ally_state.hp == 72
    assert enemy_state.hp == 500
    assert any("Ingus" in line for line in logs)


def test_physical_attack_to_enemy_sums_main_and_off_hand_damage() -> None:
    attacker_stats = _char_stats(
        main_power=20,
        main_accuracy=100,
        main_atk_multiplier=2,
        off_power=12,
        off_accuracy=100,
        off_atk_multiplier=3,
        defense=0,
    )
    enemy_stats = _enemy_stats()
    attacker_state = BattleActorState(hp=999, max_hp=999)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    logs: list[str] = []

    expected_rng = Random(7)
    main_res = physical_damage_char_to_enemy(
        attacker_stats,
        enemy_stats,
        hand="main",
        rng=expected_rng,
        use_expectation=False,
        attacker_state=attacker_state,
    )
    off_res = physical_damage_char_to_enemy(
        attacker_stats,
        enemy_stats,
        hand="off",
        rng=expected_rng,
        use_expectation=False,
        attacker_state=attacker_state,
    )
    expected_damage = main_res.damage + off_res.damage
    expected_hits = main_res.hit_count + off_res.hit_count

    damage, result = run_character_turn(
        char_name="Refia",
        enemy_name="Goblin",
        char_stats=attacker_stats,
        enemy_stats=enemy_stats,
        enemy_json={},
        char_state=attacker_state,
        enemy_state=enemy_state,
        char_attack_kind="physical",
        char_battle_command="Fight",
        char_weapon_hand="main",
        char_spell=None,
        char_spell_json=None,
        char_spell_healing_type=None,
        char_spell_name=None,
        char_item=None,
        logs=logs,
        rng=Random(7),
    )

    assert result is None
    assert damage == expected_damage
    assert enemy_state.hp == 500 - expected_damage
    assert any(f"（{expected_hits}ヒット）" in line for line in logs)


def test_offensive_magic_to_ally_hits_selected_ally_not_enemy() -> None:
    caster_stats = _char_stats(main_power=0, defense=0)
    caster_stats.intelligence = 40
    ally_stats = _char_stats(main_power=5, defense=80)
    ally_stats.magic_defense = 4
    ally_stats.magic_def_multiplier = 1
    enemy_stats = _enemy_stats()

    caster_state = BattleActorState(hp=999, max_hp=999)
    caster_state.mp_pool[1] = 1
    caster_state.max_mp_pool[1] = 1
    ally_state = BattleActorState(hp=180, max_hp=999)
    enemy_state = BattleActorState(hp=500, max_hp=500)
    party = [
        SimpleNamespace(name="Refia", stats=caster_stats, state=caster_state),
        SimpleNamespace(name="Ingus", stats=ally_stats, state=ally_state),
    ]
    spell = SpellInfo(
        power=24,
        accuracy_percent=100,
        magic_type="black",
        elements=["fire"],
    )
    spell_json = {
        "Name": "Fire",
        "Type": "Black Magic",
        "Level": 1,
        "Target": "One/All",
        "BasePower": 24,
        "BaseAccuracy": 1.0,
        "Element": "Fire",
        "Effect": "Deal fire damage",
    }
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
        char_spell=spell,
        char_spell_json=spell_json,
        char_spell_healing_type=None,
        char_spell_name="Fire",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="ally",
        target_index=1,
        party_members=party,
    )

    assert damage > 0
    assert result is None
    assert ally_state.hp == 180 - damage
    assert enemy_state.hp == 500
    assert any("Ingus" in line for line in logs)
