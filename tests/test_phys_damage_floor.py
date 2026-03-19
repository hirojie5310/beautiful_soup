# test_phys_damage_floor.py
import random

from combat.models import FinalCharacterStats, FinalEnemyStats
from combat.phys_damage import (
    physical_damage_char_to_ally,
    physical_damage_char_to_enemy,
    physical_damage_enemy_to_char,
)


class ScriptedRandom(random.Random):
    def __new__(cls, rolls: list[float], uniform_value: float = 1.25):
        return super().__new__(cls)

    def __init__(self, rolls: list[float], uniform_value: float = 1.25):
        super().__init__(0)
        self._rolls = iter(rolls)
        self._uniform_value = uniform_value

    def random(self) -> float:
        return next(self._rolls)

    def uniform(self, a: float, b: float) -> float:
        return self._uniform_value


def make_char(
    *,
    row: str = "front",
    main_power: int = 10,
    main_accuracy: int = 100,
    main_atk_multiplier: int = 2,
    defense: int = 20,
    defense_multiplier: int = 0,
    evasion_percent: int = 0,
) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=10,
        job_level=10,
        job_skill_point=0,
        max_hp=100,
        strength=10,
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
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=0,
        off_two=False,
        off_long=False,
        defense=defense,
        defense_multiplier=defense_multiplier,
        evasion_percent=evasion_percent,
        magic_defense=0,
        magic_def_multiplier=0,
        magic_resistance=0,
        shield_count=0,
    )


def make_enemy(
    *,
    attack_power: int = 10,
    attack_multiplier: int = 2,
    accuracy_percent: int = 100,
    defense: int = 20,
    defense_multiplier: int = 0,
    evasion_percent: int = 0,
) -> FinalEnemyStats:
    return FinalEnemyStats(
        name="Test Enemy",
        hp=100,
        level=10,
        job_level=10,
        attack_power=attack_power,
        attack_multiplier=attack_multiplier,
        accuracy_percent=accuracy_percent,
        defense=defense,
        defense_multiplier=defense_multiplier,
        evasion_percent=evasion_percent,
        magic_defense=0,
        magic_def_multiplier=0,
        magic_resistance_percent=0,
        agility=10,
    )


def test_char_to_enemy_floor_applies_after_total_hits() -> None:
    char = make_char(main_power=10, main_atk_multiplier=2)
    enemy = make_enemy(defense=20)

    result = physical_damage_char_to_enemy(char, enemy, use_expectation=True)

    assert result.hit_count == 2
    assert result.damage == 1


def test_enemy_to_char_floor_applies_after_total_hits() -> None:
    enemy = make_enemy(attack_power=10, attack_multiplier=2)
    char = make_char(defense=20, defense_multiplier=0, evasion_percent=0)

    damage = physical_damage_enemy_to_char(enemy, char, use_expectation=True)

    assert damage == 1


def test_char_hit_percent_is_capped_to_99_before_blind_penalty() -> None:
    char = make_char(main_power=10, main_accuracy=120, main_atk_multiplier=10)
    enemy = make_enemy(defense=0)

    result = physical_damage_char_to_enemy(
        char, enemy, use_expectation=True, blind=True
    )

    assert result.hit_count == 5
    assert result.damage == 58


def test_enemy_hit_percent_is_capped_to_99_before_back_row_penalty() -> None:
    enemy = make_enemy(attack_power=10, attack_multiplier=10, accuracy_percent=120)
    char = make_char(row="back", defense=0, defense_multiplier=0, evasion_percent=0)

    damage = physical_damage_enemy_to_char(enemy, char, use_expectation=True)

    assert damage == 58


def test_char_hit_count_uses_per_hit_rolls_in_random_mode() -> None:
    char = make_char(main_power=10, main_accuracy=99, main_atk_multiplier=4)
    enemy = make_enemy(defense=0, defense_multiplier=2, evasion_percent=50)
    rng = ScriptedRandom([0.10, 0.20, 0.30, 0.995, 0.10, 0.90, 0.99])

    result = physical_damage_char_to_enemy(
        char,
        enemy,
        rng=rng,
        use_expectation=False,
    )

    assert result.hit_count == 2
    assert result.damage == 24
    assert result.is_critical is False


def test_enemy_hit_count_uses_per_hit_rolls_in_random_mode() -> None:
    enemy = make_enemy(attack_power=10, attack_multiplier=4, accuracy_percent=99)
    char = make_char(defense=0, defense_multiplier=2, evasion_percent=50)
    rng = ScriptedRandom([0.10, 0.20, 0.30, 0.995, 0.10, 0.90, 0.99])

    damage, is_critical, net_hits = physical_damage_enemy_to_char(
        enemy,
        char,
        rng=rng,
        use_expectation=False,
        return_crit=True,
    )

    assert damage == 24
    assert is_critical is False
    assert net_hits == 2.0


def test_char_to_ally_uses_zero_defense_for_friendly_target() -> None:
    attacker = make_char(main_power=20, main_accuracy=100, main_atk_multiplier=2)
    target = make_char(defense=50, defense_multiplier=0, evasion_percent=0)

    result = physical_damage_char_to_ally(attacker, target, use_expectation=True)

    assert result.hit_count == 2
    assert result.damage == 49
