from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from combat.models import BattleActorState
from combat.enums import Status
from combat.battle_save_patch import BattleSavePatch
from combat.battle_save_patch import BattleSavePatchValidationError
from combat.battle_save_patch import build_battle_save_patch
from combat.battle_save_patch import build_party_battle_state_patch
from combat.progression import build_victory_reward_save_patch
from combat.runtime_state import RuntimeState
from combat.wasm_api import WasmBattleEngine


def test_build_battle_save_patch_reports_resource_party_and_inventory_diffs() -> None:
    before = {
        "gil": 100,
        "CP": 2,
        "inventory": {"Anywhere": {"Potion": 1}},
        "item_stock": {"Potion": 1},
        "party": [
            {
                "name": "Refia",
                "level": 1,
                "exp": 0,
                "hp": 8,
                "max_hp": 10,
                "job_level": {"level": 1, "skill_point": 0},
                "mp_levels": {"1": {"current": 1, "max": 2}},
            }
        ],
    }
    after = {
        "gil": 125,
        "CP": 3,
        "inventory": {"Anywhere": {"Potion": 2}},
        "item_stock": {},
        "party": [
            {
                "name": "Refia",
                "level": 2,
                "exp": 40,
                "hp": 6,
                "max_hp": 12,
                "job_level": {"level": 1, "skill_point": 5},
                "mp_levels": {"1": {"current": 0, "max": 3}},
            }
        ],
    }

    patch = build_battle_save_patch(
        before,
        after,
        rewards={"gained_gil": 25, "gained_cp": 1},
    ).to_dict()

    assert patch["resource_changes"]["gil"] == {
        "before": 100,
        "after": 125,
        "delta": 25,
    }
    assert patch["resource_changes"]["cp"]["delta"] == 1
    assert patch["party_changes"] == [
        {
            "name": "Refia",
            "hp": {"before": 8, "after": 6, "delta": -2},
            "max_hp": {"before": 10, "after": 12, "delta": 2},
            "level": {"before": 1, "after": 2, "delta": 1},
            "exp": {"before": 0, "after": 40, "delta": 40},
            "job_level": {
                "skill_point": {"before": 0, "after": 5, "delta": 5},
            },
            "mp_levels": {
                "1": {
                    "current_before": 1,
                    "current_after": 0,
                    "current_delta": -1,
                    "max_before": 2,
                    "max_after": 3,
                    "max_delta": 1,
                }
            },
        }
    ]
    assert patch["inventory_changes"] == [
        {"path": ["Anywhere", "Potion"], "before": 1, "after": 2, "delta": 1}
    ]
    assert patch["item_stock_changes"] == [
        {"path": ["Potion"], "before": 1, "after": 0, "delta": -1}
    ]
    assert patch["rewards"]["gained_gil"] == 25


def test_runtime_state_apply_battle_save_patch_updates_save_contract() -> None:
    state = RuntimeState(
        monsters={},
        weapons={},
        armors={},
        spells={},
        items_by_name={},
        jobs_by_name={},
        base_dir=Path("."),
        save={
            "schema_version": 1,
            "gil": 100,
            "CP": 2,
            "inventory": {"Anywhere": {"Potion": 1}},
            "party": [
                {
                    "name": "Refia",
                    "level": 1,
                    "exp": 0,
                    "job": "Onion Knight",
                    "job_level": {"level": 1, "skill_point": 0},
                    "hp": 8,
                    "max_hp": 10,
                    "mp_levels": {"1": {"current": 1, "max": 2}},
                    "row": "front",
                }
            ],
        },
    )
    patch = build_battle_save_patch(
        state.save,
        {
            **state.save,
            "gil": 125,
            "party": [
                {
                    **state.save["party"][0],
                    "hp": 6,
                    "max_hp": 12,
                    "mp_levels": {"1": {"current": 0, "max": 3}},
                }
            ],
        },
    )

    state.apply(patch)

    assert state.save["gil"] == 125
    assert state.save["party"][0]["hp"] == 6
    assert state.save["party"][0]["max_hp"] == 12
    assert state.save["party"][0]["mp"]["L1MP"] == 0
    assert state.save["party"][0]["mp_levels"]["1"] == {"current": 0, "max": 3}


def test_runtime_state_apply_rejects_patch_with_unknown_party_member() -> None:
    state = RuntimeState(
        monsters={},
        weapons={},
        armors={},
        spells={},
        items_by_name={},
        jobs_by_name={},
        base_dir=Path("."),
        save={
            "schema_version": 1,
            "gil": 100,
            "CP": 2,
            "inventory": {},
            "party": [
                {
                    "name": "Refia",
                    "level": 1,
                    "exp": 0,
                    "job": "Onion Knight",
                    "job_level": {"level": 1, "skill_point": 0},
                    "hp": 8,
                    "max_hp": 10,
                    "mp_levels": {"1": {"current": 1, "max": 2}},
                    "row": "front",
                }
            ],
        },
    )
    before_save = deepcopy(state.save)
    patch = BattleSavePatch(
        party_changes=[
            {
                "name": "Arc",
                "hp": {"before": 8, "after": 6, "delta": -2},
            }
        ]
    )

    with pytest.raises(
        BattleSavePatchValidationError, match="does not exist in current save.party"
    ):
        state.apply(patch)

    assert state.save == before_save


def test_runtime_state_apply_rejects_reapplying_same_patch() -> None:
    state = RuntimeState(
        monsters={},
        weapons={},
        armors={},
        spells={},
        items_by_name={},
        jobs_by_name={},
        base_dir=Path("."),
        save={
            "schema_version": 1,
            "gil": 100,
            "CP": 2,
            "inventory": {"Anywhere": {"Potion": 1}},
            "party": [
                {
                    "name": "Refia",
                    "level": 1,
                    "exp": 0,
                    "job": "Onion Knight",
                    "job_level": {"level": 1, "skill_point": 0},
                    "hp": 8,
                    "max_hp": 10,
                    "mp_levels": {"1": {"current": 1, "max": 2}},
                    "row": "front",
                }
            ],
        },
    )
    patch = build_battle_save_patch(
        state.save,
        {
            **state.save,
            "gil": 125,
            "party": [
                {
                    **state.save["party"][0],
                    "hp": 6,
                }
            ],
        },
    )

    state.apply(patch)

    with pytest.raises(
        BattleSavePatchValidationError, match="before does not match current save"
    ):
        state.apply(patch)


def test_runtime_state_apply_rejects_patch_with_malformed_inventory_path() -> None:
    state = RuntimeState(
        monsters={},
        weapons={},
        armors={},
        spells={},
        items_by_name={},
        jobs_by_name={},
        base_dir=Path("."),
        save={
            "schema_version": 1,
            "gil": 0,
            "CP": 0,
            "inventory": {"Anywhere": {"Potion": 1}},
            "party": [
                {
                    "name": "Refia",
                    "level": 1,
                    "exp": 0,
                    "job": "Onion Knight",
                    "job_level": {"level": 1, "skill_point": 0},
                    "hp": 10,
                    "max_hp": 10,
                    "mp_levels": {"1": {"current": 1, "max": 2}},
                    "row": "front",
                }
            ],
        },
    )
    before_save = deepcopy(state.save)
    patch = BattleSavePatch(
        inventory_changes=[
            {"path": [], "before": 1, "after": 0, "delta": -1},
        ]
    )

    with pytest.raises(
        BattleSavePatchValidationError, match="path must be a non-empty list"
    ):
        state.apply(patch)

    assert state.save == before_save


def test_build_victory_reward_save_patch_does_not_mutate_save_before_apply(
    monkeypatch,
) -> None:
    engine = WasmBattleEngine.create_default(seed=47)
    state = engine.session.state
    state.save["CP"] = 0
    state.save["item_stock"] = {}
    before_save = deepcopy(state.save)
    first_enemy = engine.session.enemies[0]
    first_enemy.json["Experience"] = 12
    first_enemy.json["Gil"] = 34
    first_enemy.json["CP"] = 5

    monkeypatch.setattr("combat.progression.roll_drops", lambda enemy: ["Potion"])

    rewards, patch = build_victory_reward_save_patch(
        party_members=engine.session.party_members,
        enemies=[first_enemy],
        state=state,
        level_table=engine.session.level_table,
    )

    assert state.save == before_save
    assert rewards["gained_exp"] == 12
    assert rewards["gained_gil"] == 34
    assert rewards["gained_cp"] == 5
    assert rewards["dropped_item"] == ["Potion"]
    assert patch.resource_changes["gil"]["delta"] == 34

    state.apply(patch)

    assert state.save["gil"] == before_save["gil"] + 34
    assert state.save["CP"] == min(255, before_save["CP"] + 5)
    assert (
        state.save["inventory"]["Anywhere"]["Potion"]
        == before_save["inventory"]["Anywhere"]["Potion"] + 1
    )


def test_build_party_battle_state_patch_can_drive_state_apply() -> None:
    state = RuntimeState(
        monsters={},
        weapons={},
        armors={},
        spells={},
        items_by_name={},
        jobs_by_name={},
        base_dir=Path("."),
        save={
            "schema_version": 1,
            "gil": 0,
            "CP": 0,
            "inventory": {},
            "party": [
                {
                    "name": "Refia",
                    "level": 1,
                    "exp": 0,
                    "job": "Onion Knight",
                    "job_level": {"level": 1, "skill_point": 0},
                    "hp": 10,
                    "max_hp": 10,
                    "mp_levels": {"1": {"current": 1, "max": 2}},
                    "row": "front",
                }
            ],
        },
    )
    runtime_member = SimpleNamespace(
        name="Refia",
        state=BattleActorState(hp=4, max_hp=12),
    )
    runtime_member.state.mp_pool[1] = 0
    runtime_member.state.max_mp_pool[1] = 3

    patch = build_party_battle_state_patch(state.save, [runtime_member])
    state.apply(patch)

    assert state.save["party"][0]["hp"] == 4
    assert state.save["party"][0]["max_hp"] == 12
    assert state.save["party"][0]["mp"]["L1MP"] == 0
    assert state.save["party"][0]["mp_levels"]["1"] == {"current": 0, "max": 3}


def test_build_party_battle_state_patch_preserves_persistent_statuses_only() -> None:
    state = RuntimeState(
        monsters={},
        weapons={},
        armors={},
        spells={},
        items_by_name={},
        jobs_by_name={},
        base_dir=Path("."),
        save={
            "schema_version": 1,
            "gil": 0,
            "CP": 0,
            "inventory": {},
            "party": [
                {
                    "name": "Refia",
                    "level": 1,
                    "exp": 0,
                    "job": "Onion Knight",
                    "job_level": {"level": 1, "skill_point": 0},
                    "hp": 10,
                    "max_hp": 10,
                    "mp_levels": {"1": {"current": 1, "max": 2}},
                    "status_effects": {
                        "Blind": False,
                        "Poison": False,
                        "Sleep": True,
                        "Confusion": True,
                        "Partial Petrification (1/3)": True,
                    },
                    "status_icons": ["sleep", "confusion", "petrify"],
                    "row": "front",
                }
            ],
        },
    )
    runtime_member = SimpleNamespace(
        name="Refia",
        state=BattleActorState(hp=4, max_hp=12),
    )
    runtime_member.state.statuses = {
        Status.BLIND,
        Status.POISON,
        Status.SLEEP,
        Status.CONFUSION,
        Status.PARTIAL_PETRIFY,
    }

    patch = build_party_battle_state_patch(state.save, [runtime_member])
    state.apply(patch)

    entry = state.save["party"][0]
    assert entry["status_effects"]["Blind"] is True
    assert entry["status_effects"]["Poison"] is True
    assert entry["status_effects"]["Sleep"] is False
    assert entry["status_effects"]["Confusion"] is False
    assert entry["status_effects"]["Partial Petrification (1/3)"] is False
    assert entry["status_icons"] == ["blind", "poison"]
