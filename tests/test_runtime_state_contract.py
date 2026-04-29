from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from combat.runtime_state import (
    RuntimeState,
    RuntimeStateInvariantError,
    init_runtime_state,
    validate_runtime_state,
)


def _minimal_save() -> dict:
    return {
        "schema_version": 1,
        "gil": 0,
        "CP": 0,
        "inventory": {
            "Anywhere": {"Potion": 1},
            "Magic": {"LV1": {"Cure": 1}},
        },
        "party": [
            {
                "name": "Refia",
                "level": 1,
                "exp": 0,
                "job": "Onion Knight",
                "job_level": {"level": 1, "skill_point": 0},
                "job_levels": {
                    "Onion Knight": {"level": 1, "skill_point": 0},
                },
                "hp": 10,
                "max_hp": 10,
                "mp": {"L1MP": 0},
                "mp_levels": {"1": {"current": 0, "max": 0}},
                "row": "front",
            },
        ],
    }


def _minimal_state(save: dict | None = None) -> RuntimeState:
    return RuntimeState(
        monsters={},
        weapons={},
        armors={},
        spells={},
        items_by_name={},
        jobs_by_name={},
        save=save or _minimal_save(),
        base_dir=Path("."),
    )


def test_validate_runtime_state_accepts_minimal_contract() -> None:
    validate_runtime_state(_minimal_state())


def test_init_runtime_state_satisfies_runtime_contract() -> None:
    state = init_runtime_state()
    validate_runtime_state(state)


def test_runtime_state_update_save_reverts_on_invalid_mutation() -> None:
    state = _minimal_state()
    original_save = deepcopy(state.save)

    with pytest.raises(RuntimeStateInvariantError, match="save.gil"):
        state.update_save(lambda save: save.update({"gil": -1}))

    assert state.save == original_save


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        (lambda save: save.update({"gil": -1}), "save.gil"),
        (lambda save: save["party"][0].update({"hp": 11}), "hp must be <= max_hp"),
        (lambda save: save["party"][0].update({"row": "middle"}), "row"),
        (
            lambda save: save["party"][0]["job_level"].update({"level": 0}),
            "job_level.level",
        ),
        (
            lambda save: save["inventory"]["Anywhere"].update({"Potion": -1}),
            "save.inventory",
        ),
        (
            lambda save: save["party"][0]["mp_levels"]["1"].update({"current": 2}),
            "current must be <= max",
        ),
    ],
)
def test_validate_runtime_state_rejects_invariant_violations(patch, message: str) -> None:
    save = deepcopy(_minimal_save())
    patch(save)

    with pytest.raises(RuntimeStateInvariantError, match=message):
        validate_runtime_state(_minimal_state(save))
