from combat.magic_damage import _calc_magic_accuracy
from combat.models import FinalCharacterStats, SpellInfo
from combat.status_effects import calc_buff_hit_percent
from combat.turn_logic import _terrain_accuracy_percent


def _char(*, intelligence: int = 10, mind: int = 10) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=10,
        job_level=10,
        job_skill_point=0,
        max_hp=100,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=intelligence,
        mind=mind,
        row="front",
        main_power=10,
        main_accuracy=99,
        main_atk_multiplier=1,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=0,
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


def test_calc_magic_accuracy_caps_at_99() -> None:
    caster = _char(intelligence=120)
    spell = SpellInfo(
        power=10,
        accuracy_percent=90,
        magic_type="black",
        elements=[],
    )

    assert _calc_magic_accuracy(caster, spell) == 99


def test_calc_buff_hit_percent_caps_at_99() -> None:
    assert calc_buff_hit_percent(0.75, 80) == 99


def test_terrain_accuracy_percent_caps_at_99() -> None:
    assert _terrain_accuracy_percent(1.0, 80) == 99
