# tests/test_wasm_api.py
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

from combat.battle_save_patch import build_battle_save_patch
from combat.enums import Status
from combat.runtime_state import init_runtime_state
from combat.wasm_api import (
    WasmBattleEngine,
    _build_magic_spell_meta,
    build_location_selection_context,
    build_session_status_snapshot,
    pick_enemy_names_for_location,
)


def test_create_from_state_reflects_updated_party_magic_slots() -> None:
    state = init_runtime_state()
    save_copy = json.loads(json.dumps(state.save))
    save_copy["party"][0]["Magic"]["LV7"] = ["Drain", "Esuna", "Curaja"]
    state.save = save_copy

    engine = WasmBattleEngine.create_from_state(
        state=state,
        enemy_names=["Goblin", "Goblin", "Goblin"],
        seed=5,
        selected_location_group="Mythril Mines",
        selected_location="Mythril Mines B1",
    )

    assert engine.session.state.save["party"][0]["Magic"]["LV7"][1] == "Esuna"
    assert engine.session.party_members[0].magic_slots[7][1] == "Esuna"


def test_create_from_state_preserves_current_hp_and_mp_at_battle_start() -> None:
    state = init_runtime_state()
    save_copy = json.loads(json.dumps(state.save))
    save_copy["party"][0]["hp"] = 123
    save_copy["party"][0]["mp"] = {f"L{level}MP": 0 for level in range(1, 9)}
    save_copy["party"][0]["mp"]["L1MP"] = 1
    state.save = save_copy

    engine = WasmBattleEngine.create_from_state(
        state=state,
        enemy_names=["Goblin"],
        seed=5,
        selected_location_group="Mythril Mines",
        selected_location="Mythril Mines B1",
    )
    payload = engine.build_initial_payload()
    first_member = payload["session_status"]["party"][0]

    assert first_member["hp"] == 123
    assert first_member["hp"] < first_member["max_hp"]
    assert first_member["mp_levels"]["1"]["current"] == 1
    assert (
        first_member["mp_levels"]["1"]["current"]
        < first_member["mp_levels"]["1"]["max"]
    )
    assert first_member["mp_levels"]["2"]["current"] == 0


def test_wasm_engine_round_json_returns_browser_ready_payload(monkeypatch) -> None:
    engine = WasmBattleEngine.create_default(seed=7)

    def _fake_execute_round_dto(*, session, request, rng):
        assert len(request.planned_actions) == len(session.party_members)
        first_enemy = session.enemies[0]
        first_enemy.state.hp = 0
        return type(
            "Output",
            (),
            {
                "logs": ["Refia attacks!", "Goblin took 10 damage."],
                "end_reason": "continue",
                "escaped": False,
                "enemy_was_physically_hit": True,
                "events": [
                    {
                        "type": "damage",
                        "target_side": "enemy",
                        "target_index": 0,
                        "value": 10,
                    }
                ],
                "lifecycle": type(
                    "Lifecycle",
                    (),
                    {
                        "before": "resolving_round",
                        "after": "ready_for_next_round",
                        "battle_finished": False,
                    },
                )(),
            },
        )()

    monkeypatch.setattr("combat.wasm_api.execute_round_dto", _fake_execute_round_dto)

    payload = json.loads(
        engine.execute_round_json(
            json.dumps(
                {"planned_actions": [], "lifecycle_state": "ready_for_actions"},
                ensure_ascii=False,
            )
        )
    )

    assert payload["logs"] == ["Refia attacks!", "Goblin took 10 damage."]
    assert payload["lifecycle"]["after"] == "ready_for_next_round"
    assert payload["session_status"]["enemies"][0]["hp"] == 0
    assert payload["selected_location_group"] != ""
    assert payload["selected_location"] != ""


def test_wasm_engine_persists_save_when_battle_finishes(monkeypatch) -> None:
    engine = WasmBattleEngine.create_default(seed=19)
    saved_calls: list[tuple[str | os.PathLike[str], dict[str, object]]] = []

    def _fake_execute_round_dto(*, session, request, rng):
        return type(
            "Output",
            (),
            {
                "logs": ["Battle ended."],
                "end_reason": "char_defeated",
                "escaped": False,
                "enemy_was_physically_hit": False,
                "events": [],
                "lifecycle": type(
                    "Lifecycle",
                    (),
                    {
                        "before": "resolving_round",
                        "after": "battle_finished",
                        "battle_finished": True,
                    },
                )(),
            },
        )()

    def _fake_save_savedata(path: str | os.PathLike[str], save: dict[str, object]):
        saved_calls.append((path, save))

    monkeypatch.setattr("combat.wasm_api.execute_round_dto", _fake_execute_round_dto)
    monkeypatch.setattr("combat.wasm_api.save_savedata", _fake_save_savedata)

    engine.execute_round_json(
        json.dumps(
            {"planned_actions": [], "lifecycle_state": "ready_for_actions"},
            ensure_ascii=False,
        )
    )

    assert len(saved_calls) == 1
    assert (
        Path(saved_calls[0][0]).as_posix().endswith("assets/data/ffiii_savedata.json")
    )
    assert saved_calls[0][1] is engine.session.state.save


def test_wasm_engine_persists_runtime_hp_and_mp_when_battle_finishes(
    monkeypatch,
) -> None:
    engine = WasmBattleEngine.create_default(seed=23)
    first_member = engine.session.party_members[0]
    first_member.state.max_hp = 200
    first_member.state.hp = 200
    first_member.state.max_mp_pool[1] = 3
    first_member.state.mp_pool[1] = 3
    saved_calls: list[tuple[str | os.PathLike[str], dict[str, object]]] = []

    def _fake_execute_round_dto(*, session, request, rng):
        member = session.party_members[0]
        member.state.hp = 111
        member.state.mp_pool[1] = 1
        return type(
            "Output",
            (),
            {
                "logs": ["Battle ended."],
                "end_reason": "char_defeated",
                "escaped": False,
                "enemy_was_physically_hit": False,
                "events": [],
                "lifecycle": type(
                    "Lifecycle",
                    (),
                    {
                        "before": "resolving_round",
                        "after": "battle_finished",
                        "battle_finished": True,
                    },
                )(),
            },
        )()

    def _fake_save_savedata(path: str | os.PathLike[str], save: dict[str, object]):
        saved_calls.append((path, save))

    monkeypatch.setattr("combat.wasm_api.execute_round_dto", _fake_execute_round_dto)
    monkeypatch.setattr("combat.wasm_api.save_savedata", _fake_save_savedata)

    engine.execute_round_json(
        json.dumps(
            {"planned_actions": [], "lifecycle_state": "ready_for_actions"},
            ensure_ascii=False,
        )
    )

    saved_member = cast(dict[str, Any], saved_calls[0][1]["party"][0])
    assert saved_member["hp"] == 111
    assert saved_member["max_hp"] == 200
    assert saved_member["mp"]["L1MP"] == 1
    assert saved_member["mp_levels"]["1"] == {"current": 1, "max": 3}


def test_wasm_engine_applies_drop_item_stock_to_inventory_on_victory(
    monkeypatch,
) -> None:
    engine = WasmBattleEngine.create_default(seed=29)

    def _fake_execute_round_dto(*, session, request, rng):
        return type(
            "Output",
            (),
            {
                "logs": ["Victory!"],
                "end_reason": "enemy_defeated",
                "escaped": False,
                "enemy_was_physically_hit": True,
                "events": [],
                "lifecycle": type(
                    "Lifecycle",
                    (),
                    {
                        "before": "resolving_round",
                        "after": "battle_finished",
                        "battle_finished": True,
                    },
                )(),
            },
        )()

    def _fake_build_victory_reward_save_patch(*, party_members, enemies, state, level_table):
        del party_members, enemies, level_table
        after_save = json.loads(json.dumps(state.save))
        after_save.setdefault("inventory", {}).setdefault("Anywhere", {})["Potion"] = (
            int(
                after_save.setdefault("inventory", {})
                .setdefault("Anywhere", {})
                .get("Potion", 0)
            )
            + 1
        )
        rewards = {
            "gained_exp": 10,
            "gained_gil": 10,
            "gained_cp": 1,
            "dropped_item": ["Potion"],
            "levelups": [],
        }
        return rewards, build_battle_save_patch(state.save, after_save, rewards=rewards)

    monkeypatch.setattr("combat.wasm_api.execute_round_dto", _fake_execute_round_dto)
    monkeypatch.setattr(
        "combat.wasm_api.build_victory_reward_save_patch",
        _fake_build_victory_reward_save_patch,
    )
    monkeypatch.setattr(
        "combat.wasm_api.save_savedata",
        lambda path, save: None,
    )

    payload = json.loads(
        engine.execute_round_json(
            json.dumps(
                {"planned_actions": [], "lifecycle_state": "ready_for_actions"},
                ensure_ascii=False,
            )
        )
    )

    assert payload["victory_rewards"]["dropped_item"] == ["Potion"]
    assert payload["victory_rewards"]["gil_before"] >= 0
    assert (
        payload["victory_rewards"]["gil_after"]
        >= payload["victory_rewards"]["gil_before"]
    )
    assert payload["victory_rewards"]["cp_before"] >= 0
    assert (
        payload["victory_rewards"]["cp_after"]
        >= payload["victory_rewards"]["cp_before"]
    )
    assert any("Gil +10 (" in row for row in payload["logs"])
    assert any("CP +1 (" in row for row in payload["logs"])
    assert payload["battle_save_patch"]["rewards"]["dropped_item"] == ["Potion"]
    assert any(
        row["path"] == ["Anywhere", "Potion"] and row["delta"] == 1
        for row in payload["battle_save_patch"]["inventory_changes"]
    )


def test_wasm_engine_battle_end_save_includes_progress_fields_after_victory(
    monkeypatch,
) -> None:
    engine = WasmBattleEngine.create_default(seed=41)
    saved_calls: list[dict[str, Any]] = []

    def _fake_execute_round_dto(*, session, request, rng):
        return type(
            "Output",
            (),
            {
                "logs": ["Victory!"],
                "end_reason": "enemy_defeated",
                "escaped": False,
                "enemy_was_physically_hit": True,
                "events": [],
                "lifecycle": type(
                    "Lifecycle",
                    (),
                    {
                        "before": "resolving_round",
                        "after": "battle_finished",
                        "battle_finished": True,
                    },
                )(),
            },
        )()

    def _fake_build_victory_reward_save_patch(*, party_members, enemies, state, level_table):
        del party_members, enemies, level_table
        after_save = json.loads(json.dumps(state.save))
        after_save["party"][0]["exp"] = 43210
        after_save["party"][0]["job_level"] = {"level": 12, "skill_point": 34}
        after_save["gil"] = 9876
        after_save["CP"] = 654
        after_save["inventory"] = {"Anywhere": {"Potion": 7}}
        rewards = {
            "gained_exp": 999,
            "gained_gil": 10,
            "gained_cp": 1,
            "dropped_item": [],
            "levelups": [],
        }
        return rewards, build_battle_save_patch(state.save, after_save, rewards=rewards)

    def _fake_save_savedata(path: str | os.PathLike[str], save: dict[str, object]):
        del path
        saved_calls.append(json.loads(json.dumps(save)))

    monkeypatch.setattr("combat.wasm_api.execute_round_dto", _fake_execute_round_dto)
    monkeypatch.setattr(
        "combat.wasm_api.build_victory_reward_save_patch",
        _fake_build_victory_reward_save_patch,
    )
    monkeypatch.setattr("combat.wasm_api.save_savedata", _fake_save_savedata)

    payload = json.loads(
        engine.execute_round_json(
            json.dumps(
                {"planned_actions": [], "lifecycle_state": "ready_for_actions"},
                ensure_ascii=False,
            )
        )
    )

    assert saved_calls
    assert payload["battle_save_patch"]["resource_changes"]["gil"]["after"] == 9876
    assert payload["battle_save_patch"]["resource_changes"]["cp"]["after"] == 654
    first_member_patch = next(
        row
        for row in payload["battle_save_patch"]["party_changes"]
        if row["name"] == engine.session.party_members[0].name
    )
    assert first_member_patch["exp"]["after"] == 43210
    assert first_member_patch["job_level"]["level"]["after"] == 12
    assert payload["battle_save_patch"]["inventory_changes"]

    assert saved_calls[0]["party"][0]["exp"] == 43210
    assert saved_calls[0]["party"][0]["job_level"]["level"] == 12
    assert saved_calls[0]["party"][0]["job_level"]["skill_point"] == 34
    assert saved_calls[0]["gil"] == 9876
    assert saved_calls[0]["CP"] == 654
    assert saved_calls[0]["inventory"]["Anywhere"]["Potion"] >= 7


def test_wasm_engine_battle_end_save_patch_reports_non_victory_state_sync(
    monkeypatch,
) -> None:
    engine = WasmBattleEngine.create_default(seed=43)
    before_hp = int(engine.session.state.save["party"][0]["hp"])
    engine.session.party_members[0].state.hp = max(0, before_hp - 5)

    def _fake_execute_round_dto(*, session, request, rng):
        del session, request, rng
        return type(
            "Output",
            (),
            {
                "logs": ["Escaped!"],
                "end_reason": "escaped",
                "escaped": True,
                "enemy_was_physically_hit": False,
                "events": [],
                "lifecycle": type(
                    "Lifecycle",
                    (),
                    {
                        "before": "resolving_round",
                        "after": "battle_finished",
                        "battle_finished": True,
                    },
                )(),
            },
        )()

    monkeypatch.setattr("combat.wasm_api.execute_round_dto", _fake_execute_round_dto)
    monkeypatch.setattr("combat.wasm_api.save_savedata", lambda path, save: None)

    payload = json.loads(
        engine.execute_round_json(
            json.dumps(
                {"planned_actions": [], "lifecycle_state": "ready_for_actions"},
                ensure_ascii=False,
            )
        )
    )

    assert payload["battle_save_patch"]["rewards"] == {}
    first_member_patch = next(
        row
        for row in payload["battle_save_patch"]["party_changes"]
        if row["name"] == engine.session.party_members[0].name
    )
    assert first_member_patch["hp"]["before"] == before_hp
    assert first_member_patch["hp"]["after"] == max(0, before_hp - 5)


def test_build_session_status_snapshot_serializes_status_icons() -> None:
    engine = WasmBattleEngine.create_default(seed=1)
    engine.session.party_members[0].state.statuses = {Status.BLIND}

    snapshot = build_session_status_snapshot(engine.session)

    assert snapshot["party"][0]["status_icons"] == ["blind"]
    assert snapshot["enemies"]
    assert "magic_command_candidates_by_member" in snapshot
    assert "item_command_candidates" in snapshot
    assert "magic_spell_meta" in snapshot
    assert "item_meta" in snapshot


def test_build_session_status_snapshot_serializes_enemy_status_icons_from_string() -> (
    None
):
    engine = WasmBattleEngine.create_default(seed=13)
    enemy_state = cast(Any, engine.session.enemies[0].state)
    setattr(enemy_state, "statuses", {"Status.SLEEP"})

    snapshot = build_session_status_snapshot(engine.session)

    assert snapshot["enemies"][0]["status_icons"] == ["sleep"]


def test_build_session_status_snapshot_marks_out_of_battle_members() -> None:
    engine = WasmBattleEngine.create_default(seed=11)
    engine.session.party_members[0].state.hp = 0
    engine.session.party_members[0].state.statuses = {Status.KO}

    snapshot = build_session_status_snapshot(engine.session)

    assert snapshot["party"][0]["out_of_battle"] is True
    if len(snapshot["party"]) > 1:
        assert snapshot["party"][1]["out_of_battle"] is False


def test_build_session_status_snapshot_includes_menu_fields() -> None:
    engine = WasmBattleEngine.create_default(seed=17)

    snapshot = build_session_status_snapshot(engine.session)

    first = snapshot["party"][0]
    assert first["job"] != ""
    assert first["row"] in {"front", "back"}
    assert isinstance(first["mp_levels"], dict)
    assert first["mp_levels"]["1"]["current"] >= 0
    assert first["mp_levels"]["8"]["max"] >= 0
    assert snapshot["resources"]["cp_max"] == 255
    assert snapshot["resources"]["gil"] >= 0


def test_build_session_status_snapshot_prefers_runtime_member_identity() -> None:
    engine = WasmBattleEngine.create_default(seed=23)
    runtime_name = engine.session.party_members[0].name
    runtime_job = str(getattr(engine.session.party_members[0].job, "name", ""))
    engine.session.state.save["party"][0]["name"] = "Refia"
    engine.session.state.save["party"][0]["job"] = "Dragoon"
    engine.session.state.save["party"][0]["portrait_key"] = "refia"

    snapshot = build_session_status_snapshot(engine.session)

    assert snapshot["party"][0]["name"] == runtime_name
    assert snapshot["party"][0]["job"] == runtime_job


def test_wasm_engine_initial_payload_exposes_flat_party_members() -> None:
    engine = WasmBattleEngine.create_default(seed=3)

    payload = engine.build_initial_payload()

    assert payload["session_status"]["party"]
    assert payload["session_status"]["command_candidates_by_member"]
    assert payload["session_status"]["command_candidates_by_member"][0]
    assert isinstance(payload["session_status"]["item_command_candidates"], list)
    assert isinstance(payload["session_status"]["magic_spell_meta"], dict)
    assert payload["party_members"][0]["equipment"]["main_hand"] is not None
    assert "strength" in payload["party_members"][0]


def test_location_selection_context_includes_groups_and_locations() -> None:
    state = init_runtime_state()

    context = build_location_selection_context(state)

    assert context["groups"]
    assert context["selected_group"] != ""
    assert context["selected_location"] != ""


def test_pick_enemy_names_for_location_returns_combatants() -> None:
    state = init_runtime_state()
    context = build_location_selection_context(state)

    names = pick_enemy_names_for_location(state, context["selected_location"])

    assert names
    assert all(isinstance(name, str) and name for name in names)


def test_wasm_magic_meta_includes_parent_summon_with_uniform_child_target() -> None:
    dummy_session = cast(
        Any,
        type(
            "Session",
            (),
            {
                "spells_expanded": {
                    "Leviathan: Demon Eye": {
                        "Name": "Leviathan: Demon Eye",
                        "Type": "Summon",
                        "Target": "All Enemies",
                        "Level": 7,
                    }
                },
                "state": type(
                    "State",
                    (),
                    {
                        "spells": {
                            "Leviathan": {
                                "Name": "Leviathan",
                                "Type": "Summon Magic",
                                "Target": "One Enemy",
                                "Level": 7,
                                "Spells": [
                                    {
                                        "Name": "Leviathan: Demon Eye",
                                        "Target": "All Enemies",
                                    },
                                    {
                                        "Name": "Leviathan: Cyclone",
                                        "Target": "All Enemies",
                                    },
                                ],
                            }
                        }
                    },
                )(),
            },
        )(),
    )

    meta = _build_magic_spell_meta(dummy_session)

    assert meta["Leviathan"]["target_norm"] == "all enemies"
    assert meta["Leviathan"]["can_select_all"] is False
