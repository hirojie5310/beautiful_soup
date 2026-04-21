# teststest_magic_heal_formula.py
from combat.magic_damage import magic_heal_amount_to_char
from combat.models import FinalCharacterStats, SpellInfo


def _caster(
    *, level: int, mind: int, job_level: int, job_skill_point: int
) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=level,
        job_level=job_level,
        job_skill_point=job_skill_point,
        max_hp=9999,
        strength=1,
        agility=1,
        vitality=1,
        intelligence=1,
        mind=mind,
        row="front",
        main_power=0,
        main_accuracy=0,
        main_atk_multiplier=1,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=1,
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


def test_white_heal_uses_job_level_in_multiplier() -> None:
    caster = _caster(level=32, mind=64, job_level=96, job_skill_point=1)
    cure = SpellInfo(power=40, accuracy_percent=100, magic_type="white", elements=[])

    heal = magic_heal_amount_to_char(
        caster=caster,
        spell=cure,
        use_expectation=True,
        target_count=4,
        spell_name="Cure",
        spell_json={"field_heal_hp": 50},
    )

    # 期待値モード: base_per_hit = int(40 * 1.25) = 50
    # mult = 1 + 64//16 + 32//16 + 96//32 = 10
    # 魔法命中率は NES 上限 99% なので expected_hits = 10 * 0.99 = 9.9
    assert heal == 495


def test_curaja_single_target_is_full_heal_value() -> None:
    caster = _caster(level=20, mind=20, job_level=20, job_skill_point=0)
    curaja = SpellInfo(power=80, accuracy_percent=100, magic_type="white", elements=[])

    heal_single = magic_heal_amount_to_char(
        caster=caster,
        spell=curaja,
        use_expectation=True,
        target_count=1,
        spell_name="Curaja",
        spell_json={"field_heal_hp": 9999},
    )
    heal_multi = magic_heal_amount_to_char(
        caster=caster,
        spell=curaja,
        use_expectation=True,
        target_count=4,
        spell_name="Curaja",
        spell_json={"field_heal_hp": 9999},
    )

    assert heal_single == 9999
    assert heal_multi != 9999


def test_curaja_non_single_target_never_uses_full_heal_shortcut() -> None:
    caster = _caster(level=20, mind=20, job_level=20, job_skill_point=0)
    curaja = SpellInfo(power=80, accuracy_percent=100, magic_type="white", elements=[])

    heal_zero = magic_heal_amount_to_char(
        caster=caster,
        spell=curaja,
        use_expectation=True,
        target_count=0,
        spell_name="Curaja",
        spell_json={"field_heal_hp": 9999},
    )
    heal_multi = magic_heal_amount_to_char(
        caster=caster,
        spell=curaja,
        use_expectation=True,
        target_count=4,
        spell_name="Curaja",
        spell_json={"field_heal_hp": 9999},
    )

    assert heal_zero == heal_multi
