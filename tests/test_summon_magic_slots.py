# tests/test_summon_magic_slots.py
from pathlib import Path
from random import Random
from types import SimpleNamespace
from typing import cast

from assets.data.data_loader import load_jobs, load_spells
from combat.battle_sim import _build_character_action_inputs
from combat.battle_sim import simulate_one_round_multi_party
from combat.magic_menu import (
    build_party_magic_lists_from_party,
    expand_spells_for_summons,
)
from combat.models import (
    BaseCharacter,
    BattleActorState,
    EnemyRuntime,
    FinalCharacterStats,
    FinalEnemyStats,
    Job,
    PlannedAction,
    PartyMemberRuntime,
)
from combat.constants import JOB_CAST_CODE
from combat.runtime_state import RuntimeState


def _load_master_data():
    spells = load_spells(Path("assets/data/ffiii_spells.json"))
    jobs = load_jobs(Path("assets/data/ffiii_jobs_compact.json"))
    return spells, jobs


def test_sage_equipped_parent_summon_resolves_to_deterministic_child():
    spells, jobs = _load_master_data()
    party_entries = [
        {
            "name": "Runeth",
            "job": "Sage",
            "Magic": {
                "LV1": [None, None, None],
                "LV2": ["Shiva", None, None],
                "LV3": [None, None, None],
                "LV4": [None, None, None],
                "LV5": [None, None, None],
                "LV6": [None, None, None],
                "LV7": [None, None, None],
                "LV8": [None, None, None],
            },
        }
    ]

    rows = build_party_magic_lists_from_party(
        party_entries=party_entries,
        jobs_by_name=jobs,
        spells_by_name=spells,
        job_cast_code=JOB_CAST_CODE,
    )

    assert [row[0] for row in rows[0]] == ["Shiva: Diamond Dust"]


def test_evoker_equipped_parent_summon_keeps_parent_name_in_menu():
    spells, jobs = _load_master_data()
    party_entries = [
        {
            "name": "Arc",
            "job": "Evoker",
            "Magic": {
                "LV1": [None, None, None],
                "LV2": ["Shiva", None, None],
                "LV3": [None, None, None],
                "LV4": [None, None, None],
                "LV5": [None, None, None],
                "LV6": [None, None, None],
                "LV7": [None, None, None],
                "LV8": [None, None, None],
            },
        }
    ]

    rows = build_party_magic_lists_from_party(
        party_entries=party_entries,
        jobs_by_name=jobs,
        spells_by_name=spells,
        job_cast_code=JOB_CAST_CODE,
    )

    assert [row[0] for row in rows[0]] == ["Shiva"]


def test_mystic_knight_equipped_parent_summon_is_hidden_from_magic_menu():
    spells, jobs = _load_master_data()
    party_entries = [
        {
            "name": "Luneth",
            "job": "Mystic Knight",
            "Magic": {
                "LV1": [None, None, None],
                "LV2": [None, None, None],
                "LV3": [None, None, None],
                "LV4": [None, None, None],
                "LV5": [None, None, None],
                "LV6": [None, None, None],
                "LV7": [None, None, None],
                "LV8": ["Bahamut", None, None],
            },
        }
    ]

    rows = build_party_magic_lists_from_party(
        party_entries=party_entries,
        jobs_by_name=jobs,
        spells_by_name=spells,
        job_cast_code=JOB_CAST_CODE,
    )

    assert [row[0] for row in rows[0]] == []


def test_ranger_equipped_parent_summon_is_hidden_from_magic_menu():
    spells, jobs = _load_master_data()
    party_entries = [
        {
            "name": "Ingus",
            "job": "Ranger",
            "Magic": {
                "LV1": [None, None, None],
                "LV2": [None, None, None],
                "LV3": [None, None, None],
                "LV4": [None, None, None],
                "LV5": [None, None, None],
                "LV6": [None, None, None],
                "LV7": [None, None, None],
                "LV8": ["Bahamut", None, None],
            },
        }
    ]

    rows = build_party_magic_lists_from_party(
        party_entries=party_entries,
        jobs_by_name=jobs,
        spells_by_name=spells,
        job_cast_code=JOB_CAST_CODE,
    )

    assert [row[0] for row in rows[0]] == []


def test_evoker_cast_uses_random_child_from_parent_summon():
    spells, jobs = _load_master_data()
    expanded = expand_spells_for_summons(spells)
    actor = cast(PartyMemberRuntime, SimpleNamespace(job=jobs["Evoker"]))
    action = PlannedAction(kind="magic", command="Magic", spell_name="Shiva")

    seen = set()
    for seed in range(12):
        (
            char_attack_kind,
            _char_battle_command,
            _char_spell,
            _char_spell_json,
            _char_spell_healing_type,
            char_spell_name,
            _char_item,
        ) = _build_character_action_inputs(
            action=action,
            actor=actor,
            spells_by_name=expanded,
            items_by_name=None,
            logs=[],
            rng=Random(seed),
        )
        assert char_attack_kind == "magic"
        seen.add(char_spell_name)

    assert seen == {"Shiva: Mesmerize", "Shiva: Icy Stare"}


def test_expand_summons_keeps_child_specific_cast_by() -> None:
    spells, _jobs = _load_master_data()

    expanded = expand_spells_for_summons(spells)

    assert "name" not in expanded["Shiva: Mesmerize"]
    assert expanded["Shiva: Mesmerize"]["cast_by"] == ["Ev"]
    assert expanded["Shiva: Icy Stare"]["cast_by"] == ["Ev"]
    assert expanded["Shiva: Diamond Dust"]["cast_by"] == ["Sa", "Su"]


def test_evoker_action_log_shows_resolved_child_summon_name():
    spells = {
        "Shiva": {
            "name": "Shiva",
            "Type": "Summon Magic",
            "Target": "All Enemies",
            "CastBy": ["Ev"],
            "Spells": [
                {
                    "Name": "Shiva: Mesmerize",
                    "Type": "Summon",
                    "Power": 0,
                    "Accuracy": 1.0,
                    "Target": "All Enemies",
                    "CastBy": ["Ev"],
                    "Status": "Sleep",
                },
                {
                    "Name": "Shiva: Icy Stare",
                    "Type": "Summon",
                    "Power": 0,
                    "Accuracy": 1.0,
                    "Target": "All Enemies",
                    "CastBy": ["Ev"],
                    "Status": "Paralyze",
                },
            ],
        }
    }
    expanded = expand_spells_for_summons(spells)

    stats = FinalCharacterStats(
        level=10,
        job_level=1,
        job_skill_point=0,
        max_hp=180,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=12,
        mind=12,
        row="front",
        main_power=10,
        main_accuracy=80,
        main_atk_multiplier=1,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=1,
        off_two=False,
        off_long=False,
        defense=8,
        defense_multiplier=1,
        evasion_percent=0,
        magic_defense=6,
        magic_def_multiplier=1,
        magic_resistance=0,
        shield_count=0,
    )
    base = BaseCharacter(
        level=10,
        total_exp=0,
        job_level=1,
        job_skill_point=0,
        max_hp=180,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=12,
        mind=12,
    )
    member = PartyMemberRuntime(
        name="Arc",
        level=10,
        job=Job(
            name="Evoker", slug="evoker", earned="start", stats_by_level={}, raw={}
        ),
        base=base,
        stats=stats,
        state=BattleActorState(
            hp=180,
            max_hp=180,
            mp_pool={1: 1, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0},
            max_mp_pool={1: 1, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0},
        ),
    )
    enemy = EnemyRuntime(
        name="Ouroboros",
        stats=FinalEnemyStats(
            name="Ouroboros",
            hp=120,
            level=5,
            job_level=1,
            attack_power=20,
            attack_multiplier=1,
            accuracy_percent=80,
            defense=4,
            defense_multiplier=1,
            evasion_percent=0,
            magic_defense=2,
            magic_def_multiplier=1,
            magic_resistance_percent=0,
            agility=5,
        ),
        state=BattleActorState(hp=120, max_hp=120),
        json={
            "Level": 5,
            "SpecialAttackRate": 0,
            "MagicDefense": 2,
            "MagicResistance": {},
            "StatusAilmentVulnerability": {},
        },
    )

    logs, side_result, _events = simulate_one_round_multi_party(
        party_members=[member],
        enemies=[enemy],
        planned_actions=[
            PlannedAction(
                kind="magic",
                command="Magic",
                spell_name="Shiva",
                target_side="enemy",
                target_index=0,
            )
        ],
        state=RuntimeState(
            monsters={},
            weapons={},
            armors={},
            spells=expanded,
            items_by_name={},
            jobs_by_name={},
            save={"party": [{"name": "Arc"}]},
            base_dir=Path("."),
        ),
        rng=Random(0),
        spells_by_name=expanded,
    )

    assert side_result.end_reason == "continue"
    assert "▶ Arc の行動（Magic）" in logs
    assert not any(
        line.startswith("▶ Arc の行動（Magic:")
        for line in logs
    )
    assert any(
        line.startswith("Arcは召喚魔法《Shiva:")
        for line in logs
    )
