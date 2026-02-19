# adapters/flask_app.py
# create_app() でエラーハンドラ登録、JSON受信、DTO変換、
# execute_round_dto 呼び出し、JSONレスポンス返却までを接続
from __future__ import annotations

import os
from pathlib import Path
from random import Random
from typing import Any, Sequence

from flask import Flask, jsonify, render_template, request, send_from_directory

from adapters.flask_error_handlers import register_flask_error_handlers
from assets.data.data_loader import load_explicit_groups
from combat.dto import (
    ExecuteRoundInputDTO,
    parse_execute_round_input_dict,
    to_json_ready_dict,
)
from combat.enemy_selection import build_groups, build_location_index, pick_enemy_names
from combat.errors import InputValidationError
from combat.input_ui import normalize_battle_command
from combat.magic_menu import build_party_magic_info, build_party_magic_lists
from combat.runtime_state import init_runtime_state
from combat.char_build import (
    build_party_members_from_save,
    compute_character_final_stats,
)
from combat.usecases import BattleSession, build_battle_session, execute_round_dto
from combat.models import EquipmentSet
from assets.data.data_loader import save_savedata
from ui_pygame.field_effects import sync_equipment_to_save
from adapters.flask_menu_actions import make_cast_field_magic_fn, make_use_field_item_fn


def _build_default_session(
    *, enemy_names: Sequence[str] | None = None
) -> BattleSession:
    state = init_runtime_state()
    selected_enemy_names = (
        list(enemy_names) if enemy_names else sorted(state.monsters.keys())[:3]
    )
    return build_battle_session(state=state, enemy_names=selected_enemy_names)


def _normalize_planned_actions_length(
    request_dto: ExecuteRoundInputDTO, *, expected_count: int
) -> ExecuteRoundInputDTO:
    actual_count = len(request_dto.planned_actions)
    if actual_count > expected_count:
        raise InputValidationError(
            "planned_actions has too many entries",
            details={"expected_max": expected_count, "actual": actual_count},
        )
    if actual_count == expected_count:
        return request_dto

    padded = list(request_dto.planned_actions) + [None] * (
        expected_count - actual_count
    )
    return ExecuteRoundInputDTO(
        planned_actions=padded,
        lifecycle_state=request_dto.lifecycle_state,
    )


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_party_status_snapshot(session: BattleSession) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for idx, member in enumerate(session.party_members):
        state = getattr(member, "state", None)
        hp = _safe_int(getattr(state, "hp", 0), 0)
        max_hp_raw = getattr(state, "max_hp", None)
        max_hp = _safe_int(max_hp_raw, hp) if max_hp_raw is not None else hp
        snapshots.append(
            {
                "index": idx,
                "name": str(getattr(member, "name", f"Ally {idx + 1}")),
                "hp": hp,
                "max_hp": max_hp,
            }
        )
    return snapshots


def _build_enemy_status_snapshot(session: BattleSession) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for idx, enemy in enumerate(session.enemies):
        state = getattr(enemy, "state", None)
        hp = _safe_int(getattr(state, "hp", 0), 0)
        max_hp_raw = getattr(state, "max_hp", None)
        max_hp = _safe_int(max_hp_raw, hp) if max_hp_raw is not None else hp
        snapshots.append(
            {
                "index": idx,
                "name": str(getattr(enemy, "name", f"Enemy {idx + 1}")),
                "sprite_id": getattr(enemy, "sprite_id", None),
                "hp": hp,
                "max_hp": max_hp,
            }
        )
    return snapshots


def _build_session_status_snapshot(session: BattleSession) -> dict[str, Any]:
    return {
        "party": _build_party_status_snapshot(session),
        "enemies": _build_enemy_status_snapshot(session),
    }


def _build_party_menu_snapshot(session: BattleSession) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, member in enumerate(session.party_members):
        eq = getattr(member, "equipment", None)
        state = getattr(member, "state", None)
        stats = getattr(member, "stats", None)
        hp = _safe_int(getattr(state, "hp", 0), 0)
        max_hp_raw = getattr(state, "max_hp", None)
        max_hp = _safe_int(max_hp_raw, hp) if max_hp_raw is not None else hp
        rows.append(
            {
                "index": idx,
                "name": str(getattr(member, "name", f"Ally {idx + 1}")),
                "job": str(getattr(getattr(member, "job", None), "name", "Unknown")),
                "hp": hp,
                "max_hp": max_hp,
                "row": str(getattr(stats, "row", "front")),
                "equipment": {
                    "main_hand": getattr(eq, "main_hand", None),
                    "off_hand": getattr(eq, "off_hand", None),
                    "head": getattr(eq, "head", None),
                    "body": getattr(eq, "body", None),
                    "arms": getattr(eq, "arms", None),
                },
            }
        )
    return rows


def _build_inventory_snapshot(session: BattleSession) -> list[dict[str, Any]]:
    state = getattr(session, "state", None)
    save = getattr(state, "save", {})
    inventory = save.get("inventory", {}) if isinstance(save, dict) else {}
    rows: list[dict[str, Any]] = []
    for item_type in ("Anywhere", "Field"):
        bucket = inventory.get(item_type, {})
        if not isinstance(bucket, dict):
            continue
        for name, count in sorted(bucket.items()):
            qty = _safe_int(count, 0)
            if qty <= 0:
                continue
            rows.append({"item_type": item_type, "name": name, "count": qty})
    return rows


def _build_menu_state_payload(session: BattleSession) -> dict[str, Any]:
    state = getattr(session, "state", None)
    jobs = getattr(state, "jobs_by_name", {})
    job_names = sorted(jobs.keys()) if isinstance(jobs, dict) else []
    return {
        "party": _build_party_menu_snapshot(session),
        "inventory": _build_inventory_snapshot(session),
        "jobs": job_names,
    }


def _refresh_session_party(session: BattleSession) -> None:
    hp_by_name = {m.name: int(m.state.hp) for m in session.party_members}
    session.party_members = build_party_members_from_save(
        save=session.state.save,
        jobs_by_name=session.state.jobs_by_name,
        weapons=session.state.weapons,
        armors=session.state.armors,
        level_table=session.level_table,
    )
    for member in session.party_members:
        hp = hp_by_name.get(member.name)
        if hp is not None:
            member.state.hp = max(0, min(hp, int(member.state.max_hp or hp)))

    session.party_magic_info = build_party_magic_info(session.state)
    session.party_magic_lists = build_party_magic_lists(session.state)


def _require_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise InputValidationError(f"{key} must be int")
    return value


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise InputValidationError(f"{key} must be non-empty string")
    return value


def _build_magic_command_candidates_by_member(
    session: BattleSession,
) -> list[list[str]]:
    candidates: list[list[str]] = []
    for row in session.party_magic_lists:
        names: list[str] = []
        for cand in row or []:
            if not isinstance(cand, (list, tuple)) or not cand:
                continue
            name = cand[0]
            if isinstance(name, str) and name:
                names.append(name)
        candidates.append(names)
    return candidates


def _build_special_command_candidates(session: BattleSession) -> list[str]:
    candidates: list[str] = []
    for member in session.party_members:
        job_raw = getattr(getattr(member, "job", None), "raw", {})
        if not isinstance(job_raw, dict):
            continue
        for i in range(1, 11):
            command_row = job_raw.get(f"BattleCommand{i}")
            if not isinstance(command_row, dict):
                continue
            command = command_row.get("Command")
            if not isinstance(command, str) or not command:
                continue
            if normalize_battle_command(command) != "special":
                continue
            if command not in candidates:
                candidates.append(command)
    return candidates


def create_app(
    *,
    session: BattleSession | None = None,
    rng: Random | None = None,
    enemy_names: Sequence[str] | None = None,
) -> Flask:
    template_dir = Path(__file__).resolve().parents[1] / "templates"
    app = Flask(__name__, template_folder=str(template_dir))
    register_flask_error_handlers(app)

    if session is not None:
        battle_session = session
        selection_context = {
            "groups": [],
            "selected_group": "",
            "selected_location": "",
            "selected_enemy_names": [e.get("name", "") for e in []],
            "enabled": False,
        }
    else:
        state = init_runtime_state()
        explicit_groups = load_explicit_groups("assets/data/explicit_groups.json")
        location_entries = build_location_index(state.monsters)
        location_groups = build_groups(
            location_entries, explicit_groups=explicit_groups
        )

        groups_payload: list[dict[str, Any]] = []
        location_to_entry: dict[str, Any] = {}
        for group in location_groups:
            locations = []
            for child in group.children:
                locations.append(child.location)
                location_to_entry[child.location] = child
            groups_payload.append(
                {"group_name": group.group_name, "locations": locations}
            )

        initial_group = groups_payload[0]["group_name"] if groups_payload else ""
        initial_location = (
            groups_payload[0]["locations"][0]
            if groups_payload and groups_payload[0]["locations"]
            else ""
        )
        initial_entry = location_to_entry.get(initial_location)
        selected_enemy_names = (
            pick_enemy_names(initial_entry, state.monsters, k_min=2, k_max=6)
            if initial_entry
            else sorted(state.monsters.keys())[:3]
        )
        battle_session = build_battle_session(
            state=state, enemy_names=selected_enemy_names
        )

        selection_context = {
            "groups": groups_payload,
            "selected_group": initial_group,
            "selected_location": initial_location,
            "selected_enemy_names": selected_enemy_names,
            "enabled": True,
            "state": state,
            "location_to_entry": location_to_entry,
        }

    round_rng = rng or Random()

    @app.get("/")
    def index():
        nonlocal battle_session
        if selection_context.get("enabled"):
            selected_group = request.args.get(
                "location_group", selection_context["selected_group"]
            )
            selected_location = request.args.get(
                "location", selection_context["selected_location"]
            )

            groups = selection_context["groups"]
            valid_group_names = {g["group_name"] for g in groups}
            if selected_group not in valid_group_names and groups:
                selected_group = groups[0]["group_name"]

            group_row = next(
                (g for g in groups if g["group_name"] == selected_group), None
            )
            valid_locations = set(group_row["locations"]) if group_row else set()
            if (
                selected_location not in valid_locations
                and group_row
                and group_row["locations"]
            ):
                selected_location = group_row["locations"][0]

            location_entry = selection_context["location_to_entry"].get(
                selected_location
            )
            if location_entry is not None:
                enemy_names_for_location = pick_enemy_names(
                    location_entry,
                    selection_context["state"].monsters,
                    k_min=2,
                    k_max=6,
                )
                if (
                    selected_group != selection_context["selected_group"]
                    or selected_location != selection_context["selected_location"]
                ):
                    battle_session = build_battle_session(
                        state=selection_context["state"],
                        enemy_names=enemy_names_for_location,
                    )
                    selection_context["selected_enemy_names"] = enemy_names_for_location

            selection_context["selected_group"] = selected_group
            selection_context["selected_location"] = selected_location

        return render_template(
            "top.html",
            expected_action_count=len(battle_session.party_members),
            default_lifecycle="ready_for_actions",
            initial_session_status=_build_session_status_snapshot(battle_session),
            location_groups=selection_context["groups"],
            selected_location_group=selection_context["selected_group"],
            selected_location=selection_context["selected_location"],
            selected_enemy_names=selection_context.get("selected_enemy_names", []),
            magic_command_candidates_by_member=_build_magic_command_candidates_by_member(
                battle_session
            ),
            item_command_candidates=sorted(battle_session.state.items_by_name.keys()),
            special_command_candidates=_build_special_command_candidates(
                battle_session
            ),
        )

    @app.post("/battle/round")
    def post_battle_round():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError(
                "request body must be JSON object",
                details={"actual": type(payload).__name__},
            )

        request_dto = parse_execute_round_input_dict(payload)
        request_dto = _normalize_planned_actions_length(
            request_dto,
            expected_count=len(battle_session.party_members),
        )
        output_dto = execute_round_dto(
            session=battle_session,
            request=request_dto,
            rng=round_rng,
        )
        response_payload = to_json_ready_dict(output_dto)
        response_payload["session_status"] = _build_session_status_snapshot(
            battle_session
        )
        response_payload["selected_location_group"] = selection_context.get(
            "selected_group", ""
        )
        response_payload["selected_location"] = selection_context.get(
            "selected_location", ""
        )
        return jsonify(response_payload), 200

    @app.get("/assets/enemy-sprites/<path:filename>")
    def get_enemy_sprite(filename: str):
        safe_name = Path(filename).name
        if not safe_name.lower().endswith(".png"):
            return jsonify({"error": "png only"}), 400
        sprite_dir = Path(__file__).resolve().parents[1] / "assets/images/enemy_sprites"
        return send_from_directory(str(sprite_dir), safe_name)

    @app.get("/menu")
    def menu_page():
        return render_template(
            "menu.html",
            initial_menu_state=_build_menu_state_payload(battle_session),
        )

    @app.get("/menu/state")
    def get_menu_state():
        return jsonify(_build_menu_state_payload(battle_session)), 200

    @app.post("/menu/use-item")
    def post_menu_use_item():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError("request body must be JSON object")

        user_index = _require_int(payload, "user_index")
        item_name = _require_str(payload, "item_name")
        target_index_raw = payload.get("target_index")
        target_index = target_index_raw if isinstance(target_index_raw, int) else None
        item_type = (
            payload.get("item_type")
            if isinstance(payload.get("item_type"), str)
            else None
        )

        use_item = make_use_field_item_fn(
            party=battle_session.party_members,
            items_by_name=battle_session.state.items_by_name,
            save_dict=battle_session.state.save,
        )
        ok = use_item(user_index, item_name, target_index, item_type)
        return (
            jsonify(
                {"ok": ok, "menu_state": _build_menu_state_payload(battle_session)}
            ),
            200,
        )

    @app.post("/menu/cast-magic")
    def post_menu_cast_magic():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError("request body must be JSON object")

        caster_index = _require_int(payload, "caster_index")
        spell_name = _require_str(payload, "spell_name")
        target_index_raw = payload.get("target_index")
        target_index = target_index_raw if isinstance(target_index_raw, int) else None

        def _build_magic_fn(member_index: int) -> list[tuple[str, int, int]]:
            rows = battle_session.party_magic_lists[member_index] or []
            return [(str(name), int(level), 1) for (name, _magic_type, level) in rows]

        cast_magic = make_cast_field_magic_fn(
            party=battle_session.party_members,
            spells_by_name=battle_session.spells_expanded,
            build_magic_fn=_build_magic_fn,
            save_dict=battle_session.state.save,
        )
        ok = cast_magic(caster_index, spell_name, target_index)
        return (
            jsonify(
                {"ok": ok, "menu_state": _build_menu_state_payload(battle_session)}
            ),
            200,
        )

    @app.post("/menu/change-equipment")
    def post_menu_change_equipment():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError("request body must be JSON object")

        member_index = _require_int(payload, "member_index")
        slot = _require_str(payload, "slot")
        item_name_raw = payload.get("item_name")
        item_name = (
            item_name_raw if isinstance(item_name_raw, str) and item_name_raw else None
        )

        if member_index < 0 or member_index >= len(battle_session.party_members):
            raise InputValidationError("member_index out of range")
        if slot not in {"main_hand", "off_hand", "head", "body", "arms"}:
            raise InputValidationError("slot is invalid")

        member = battle_session.party_members[member_index]
        equipment = member.equipment if member.equipment is not None else EquipmentSet()
        member.equipment = equipment
        setattr(equipment, slot, item_name)
        member.stats = compute_character_final_stats(
            member.base,
            equipment,
            battle_session.state.weapons,
            battle_session.state.armors,
            job_name=member.job.name,
        )
        sync_equipment_to_save(member, battle_session.state.save)
        return (
            jsonify(
                {"ok": True, "menu_state": _build_menu_state_payload(battle_session)}
            ),
            200,
        )

    @app.post("/menu/change-job")
    def post_menu_change_job():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError("request body must be JSON object")

        member_index = _require_int(payload, "member_index")
        job_name = _require_str(payload, "job_name")
        if member_index < 0 or member_index >= len(battle_session.party_members):
            raise InputValidationError("member_index out of range")
        if job_name not in battle_session.state.jobs_by_name:
            raise InputValidationError("job_name is invalid")

        party_entry = battle_session.state.save["party"][member_index]
        party_entry["job"] = job_name
        _refresh_session_party(battle_session)
        return (
            jsonify(
                {"ok": True, "menu_state": _build_menu_state_payload(battle_session)}
            ),
            200,
        )

    @app.post("/menu/reorder")
    def post_menu_reorder():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InputValidationError("request body must be JSON object")
        order = payload.get("order")
        if not isinstance(order, list) or not all(isinstance(i, int) for i in order):
            raise InputValidationError("order must be list[int]")
        expected = list(range(len(battle_session.party_members)))
        if sorted(order) != expected:
            raise InputValidationError("order must be permutation of current indices")

        battle_session.party_members = [battle_session.party_members[i] for i in order]
        battle_session.state.save["party"] = [
            battle_session.state.save["party"][i] for i in order
        ]
        battle_session.party_magic_lists = [
            battle_session.party_magic_lists[i] for i in order
        ]
        battle_session.party_magic_info = [
            battle_session.party_magic_info[i] for i in order
        ]
        return (
            jsonify(
                {"ok": True, "menu_state": _build_menu_state_payload(battle_session)}
            ),
            200,
        )

    @app.post("/menu/save")
    def post_menu_save():
        save_savedata(
            Path("assets/data/ffiii_savedata.json"), battle_session.state.save
        )
        return jsonify({"ok": True}), 200

    return app


app = create_app()


def run_dev_server() -> None:
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_dev_server()
