# tests/test_summon_magic_slots.py
from pathlib import Path
from random import Random
from types import SimpleNamespace
from typing import cast

from assets.data.data_loader import load_jobs, load_spells
from combat.battle_sim import _build_character_action_inputs
from combat.magic_menu import (
    build_party_magic_lists_from_party,
    expand_spells_for_summons,
)
from combat.models import PlannedAction, PartyMemberRuntime
from combat.constants import JOB_CAST_CODE


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
