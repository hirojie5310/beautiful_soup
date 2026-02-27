# tests/test_menu_magic_setup_routes.py
from __future__ import annotations

import pytest

pytest.importorskip("flask")

from adapters.flask_app import create_app


def _pick_level_with_stock(stock_by_level: dict[str, list[str]]) -> tuple[int, str]:
    for lv in range(1, 9):
        row = stock_by_level.get(str(lv), [])
        if row:
            return lv, row[0]
    raise AssertionError("no spell stock found in any level")


def test_menu_magic_learn_swap_remove_flow():
    app = create_app()
    client = app.test_client()

    state_resp = client.get("/menu/state")
    assert state_resp.status_code == 200
    state = state_resp.get_json()

    magic_setup = state["magic_setup"]
    lv, spell_name = _pick_level_with_stock(magic_setup["stock_by_level"])

    learn_resp = client.post(
        "/menu/magic/learn",
        json={
            "member_index": 0,
            "level": lv,
            "slot_index": 0,
            "spell_name": spell_name,
        },
    )
    assert learn_resp.status_code == 200
    learned_state = learn_resp.get_json()["menu_state"]["magic_setup"]
    assert learned_state["equipped_by_member"][0][str(lv)][0] == spell_name
    assert spell_name not in learned_state["stock_by_level"][str(lv)]

    swap_resp = client.post(
        "/menu/magic/swap",
        json={
            "from_member_index": 0,
            "to_member_index": 1,
            "level": lv,
            "slot_index": 0,
        },
    )
    assert swap_resp.status_code == 200
    swapped_state = swap_resp.get_json()["menu_state"]["magic_setup"]
    assert swapped_state["equipped_by_member"][0][str(lv)][0] is None
    assert swapped_state["equipped_by_member"][1][str(lv)][0] == spell_name

    remove_resp = client.post(
        "/menu/magic/remove",
        json={
            "member_index": 1,
            "level": lv,
            "slot_index": 0,
        },
    )
    assert remove_resp.status_code == 200
    removed_state = remove_resp.get_json()["menu_state"]["magic_setup"]
    assert removed_state["equipped_by_member"][1][str(lv)][0] is None
    assert spell_name in removed_state["stock_by_level"][str(lv)]
