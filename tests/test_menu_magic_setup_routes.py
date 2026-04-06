# tests/test_menu_magic_setup_routes.py
from __future__ import annotations

import pytest

pytest.importorskip("flask")

from adapters.flask_app import create_app
from combat.runtime_state import init_runtime_state
from combat.usecases import build_battle_session


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


def test_menu_magic_uses_save_backed_inventory_and_equips():
    state = init_runtime_state()
    state.save["inventory"]["Magic"] = {
        "LV1": {"Fire": 2, "Cure": 1},
        "LV2": {"Thunder": 1},
    }
    state.save["party"][0]["Magic"] = {
        "LV1": ["Fire", None, None],
        "LV2": [None, "Thunder", None],
    }
    session = build_battle_session(
        state=state,
        enemy_names=sorted(state.monsters.keys())[:3],
    )
    app = create_app(session=session)
    client = app.test_client()

    menu_state = client.get("/menu/state").get_json()
    magic_setup = menu_state["magic_setup"]
    assert magic_setup["equipped_by_member"][0]["1"] == ["Fire", None, None]
    assert magic_setup["equipped_by_member"][0]["2"] == [None, "Thunder", None]
    assert magic_setup["stock_by_level"]["1"] == ["Fire", "Cure"]
    assert magic_setup["stock_by_level"]["2"] == []

    member_candidates = menu_state["magic_candidates_by_member"][0]
    assert [cand["name"] for cand in member_candidates] == ["Fire", "Thunder"]

    learn_resp = client.post(
        "/menu/magic/learn",
        json={
            "member_index": 0,
            "level": 1,
            "slot_index": 1,
            "spell_name": "Cure",
        },
    )
    assert learn_resp.status_code == 200
    learned_state = learn_resp.get_json()["menu_state"]["magic_setup"]
    assert learned_state["equipped_by_member"][0]["1"] == ["Fire", "Cure", None]
    assert learned_state["stock_by_level"]["1"] == ["Fire"]
    assert state.save["party"][0]["Magic"]["LV1"] == ["Fire", "Cure", None]


def test_flask_menu_magic_candidates_respect_mystic_knight_spell_restrictions():
    state = init_runtime_state()
    state.save["party"][0]["job"] = "Mystic Knight"
    state.save["party"][0]["current_job"] = "Mystic Knight"
    state.save["party"][0]["job_levels"]["Mystic Knight"] = {
        "level": state.save["party"][0].get("job_level", {}).get("level", 1),
        "skill_point": state.save["party"][0].get("job_level", {}).get("skill_point", 0),
    }
    state.save["party"][0]["Magic"] = {
        "LV1": ["Cure", None, None],
        "LV2": ["Shiva", None, None],
        "LV3": ["Cura", None, None],
        "LV4": [None, None, None],
        "LV5": [None, None, None],
        "LV6": [None, None, None],
        "LV7": [None, None, None],
        "LV8": ["Bahamut", None, None],
    }
    session = build_battle_session(
        state=state,
        enemy_names=sorted(state.monsters.keys())[:3],
    )
    app = create_app(session=session)
    client = app.test_client()

    menu_state = client.get("/menu/state").get_json()
    member_candidates = menu_state["magic_candidates_by_member"][0]

    assert [cand["name"] for cand in member_candidates] == ["Cure", "Cura"]
