from __future__ import annotations

import pytest

pytest.importorskip("flask")

from adapters.flask_app import _item_allowed_for_member as flask_item_allowed
from adapters.flask_app import create_app
from combat.runtime_state import init_runtime_state
from combat.usecases import build_battle_session


def _build_session_with_equipped_member():
    state = init_runtime_state()
    state.save = {
        **state.save,
        "CP": 999,
        "inventory": {"Weapon": {}, "Armor": {}},
    }
    session = build_battle_session(
        state=state,
        enemy_names=sorted(state.monsters.keys())[:3],
    )
    member = session.party_members[0]

    weapon_name = next(
        name
        for name, raw in state.weapons.items()
        if isinstance(name, str)
        and isinstance(raw, dict)
        and flask_item_allowed(member, raw)
    )
    head_name = next(
        name
        for name, raw in state.armors.items()
        if isinstance(name, str)
        and isinstance(raw, dict)
        and raw.get("ArmorType") == "Helm"
        and flask_item_allowed(member, raw)
    )
    state.save["party"][0]["equipment"] = {
        "main_hand": weapon_name,
        "off_hand": None,
        "head": head_name,
        "body": None,
        "arms": None,
    }

    return (
        build_battle_session(
            state=state,
            enemy_names=sorted(state.monsters.keys())[:3],
        ),
        weapon_name,
        head_name,
    )


def test_menu_change_job_unequips_all_and_returns_items_to_inventory():
    session, weapon_name, head_name = _build_session_with_equipped_member()
    current_job = session.party_members[0].job.name
    next_job = next(
        name for name in sorted(session.state.jobs_by_name.keys()) if name != current_job
    )
    app = create_app(session=session)
    client = app.test_client()

    response = client.post(
        "/menu/change-job",
        json={"member_index": 0, "job_name": next_job},
    )

    assert response.status_code == 200
    payload = response.get_json()
    member_row = payload["menu_state"]["party"][0]

    assert payload["ok"] is True
    assert member_row["job"] == next_job
    assert member_row["equipment"] == {
        "main_hand": None,
        "off_hand": None,
        "head": None,
        "body": None,
        "arms": None,
    }
    assert session.state.save["party"][0]["equipment"] == member_row["equipment"]
    assert session.state.save["inventory"]["Weapon"][weapon_name] == 1
    assert session.state.save["inventory"]["Armor"][head_name] == 1
