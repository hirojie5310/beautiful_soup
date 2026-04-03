from random import Random

from combat.models import BattleActorState, FinalCharacterStats, FinalEnemyStats, SpellInfo
from combat.turn_logic import run_character_turn


def _char_stats(*, power: int = 300, intelligence: int = 40) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=999,
        strength=24,
        agility=20,
        vitality=12,
        intelligence=intelligence,
        mind=10,
        row="front",
        main_power=power,
        main_accuracy=100,
        main_atk_multiplier=4,
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


def _enemy_stats(*, hp: int = 50) -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Goblin",
        hp=hp,
        level=10,
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
    )


def test_enemy_physical_log_displays_raw_damage_even_on_overkill() -> None:
    char_stats = _char_stats(power=300)
    enemy_stats = _enemy_stats(hp=50)
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Refia",
        enemy_name="Goblin",
        char_stats=char_stats,
        enemy_stats=enemy_stats,
        enemy_json={},
        char_state=BattleActorState(hp=999, max_hp=999),
        enemy_state=BattleActorState(hp=50, max_hp=50),
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
    )

    assert result is None
    assert damage == 50
    raw_logged = [
        line for line in logs if "Goblinに" in line and "のダメージ" in line
    ]
    assert raw_logged
    assert not any("Goblinに50のダメージ" in line for line in raw_logged)


def test_enemy_magic_log_displays_raw_damage_even_on_overkill() -> None:
    char_stats = _char_stats(power=1, intelligence=40)
    enemy_stats = _enemy_stats(hp=50)
    char_state = BattleActorState(hp=999, max_hp=999)
    char_state.mp_pool[1] = 10
    logs: list[str] = []
    spell = SpellInfo(
        power=60,
        accuracy_percent=100,
        magic_type="black",
        elements=["fire"],
    )

    damage, result = run_character_turn(
        char_name="Refia",
        enemy_name="Goblin",
        char_stats=char_stats,
        enemy_stats=enemy_stats,
        enemy_json={},
        char_state=char_state,
        enemy_state=BattleActorState(hp=50, max_hp=50),
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=spell,
        char_spell_json={
            "Name": "Fire",
            "Type": "Black Magic",
            "Level": 1,
            "Target": "One Enemy",
            "Effect": "Deal Fire damage",
            "Element": "Fire",
            "BaseAccuracy": 1.0,
            "BasePower": 60,
        },
        char_spell_healing_type=None,
        char_spell_name="Fire",
        char_item=None,
        logs=logs,
        rng=Random(0),
    )

    assert result is not None
    assert damage == 50
    raw_logged = [
        line for line in logs if "Goblinに" in line and "のダメージ" in line
    ]
    assert raw_logged
    assert not any("Goblinに50のダメージ" in line for line in raw_logged)
