from __future__ import annotations

from web_wasm.bootstrap_runtime import _align_party_to_base, _repair_party_entry_job


def test_repair_party_entry_job_reverts_unsynced_job_change() -> None:
    entry = {
        "job": "Onion Knight",
        "current_job": "Onion Knight",
        "job_levels": {
            "Dragoon": {"level": 99, "skill_point": 99},
        },
    }

    repaired = _repair_party_entry_job(entry, {"job": "Dragoon"})

    assert repaired["job"] == "Dragoon"
    assert repaired["current_job"] == "Dragoon"


def test_repair_party_entry_job_keeps_job_when_job_levels_are_synced() -> None:
    entry = {
        "job": "Onion Knight",
        "current_job": "Onion Knight",
        "job_level": {"level": 1, "skill_point": 0},
        "job_levels": {
            "Dragoon": {"level": 99, "skill_point": 99},
            "Onion Knight": {"level": 1, "skill_point": 0},
        },
    }

    repaired = _repair_party_entry_job(entry, {"job": "Dragoon"})

    assert repaired["job"] == "Onion Knight"
    assert repaired["current_job"] == "Onion Knight"


def test_align_party_to_base_keeps_synced_changed_job() -> None:
    base_party = [
        {
            "name": "Refia",
            "job": "Dragoon",
            "job_levels": {
                "Dragoon": {"level": 99, "skill_point": 99},
            },
            "portrait_key": "refia",
        }
    ]
    overlay_party = [
        {
            "name": "Refia",
            "job": "Onion Knight",
            "current_job": "Onion Knight",
            "job_level": {"level": 1, "skill_point": 0},
            "job_levels": {
                "Dragoon": {"level": 99, "skill_point": 99},
                "Onion Knight": {"level": 1, "skill_point": 0},
            },
            "portrait_key": "refia",
        }
    ]

    aligned = _align_party_to_base(base_party, overlay_party)

    assert aligned[0]["job"] == "Onion Knight"
    assert aligned[0]["current_job"] == "Onion Knight"
