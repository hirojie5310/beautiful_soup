# adapters/flask_app.py
# create_app() でエラーハンドラ登録、JSON受信、DTO変換、
# execute_round_dto 呼び出し、JSONレスポンス返却までを接続
from __future__ import annotations

import os
from pathlib import Path
from random import Random
from typing import Any, Sequence

from flask import Flask, jsonify, render_template, request

from adapters.flask_error_handlers import register_flask_error_handlers
from assets.data.data_loader import load_explicit_groups
from combat.dto import ExecuteRoundInputDTO, parse_execute_round_input_dict, to_json_ready_dict
from combat.enemy_selection import build_groups, build_location_index, pick_enemy_names
from combat.errors import InputValidationError
from combat.runtime_state import init_runtime_state
from combat.usecases import BattleSession, build_battle_session, execute_round_dto


def _build_default_session(*, enemy_names: Sequence[str] | None = None) -> BattleSession:
    state = init_runtime_state()
    selected_enemy_names = list(enemy_names) if enemy_names else sorted(state.monsters.keys())[:3]
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

    padded = list(request_dto.planned_actions) + [None] * (expected_count - actual_count)
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
        location_groups = build_groups(location_entries, explicit_groups=explicit_groups)

        groups_payload: list[dict[str, Any]] = []
        location_to_entry: dict[str, Any] = {}
        for group in location_groups:
            locations = []
            for child in group.children:
                locations.append(child.location)
                location_to_entry[child.location] = child
            groups_payload.append({"group_name": group.group_name, "locations": locations})

        initial_group = groups_payload[0]["group_name"] if groups_payload else ""
        initial_location = groups_payload[0]["locations"][0] if groups_payload and groups_payload[0]["locations"] else ""
        initial_entry = location_to_entry.get(initial_location)
        selected_enemy_names = (
            pick_enemy_names(initial_entry, state.monsters, k_min=2, k_max=6) if initial_entry else sorted(state.monsters.keys())[:3]
        )
        battle_session = build_battle_session(state=state, enemy_names=selected_enemy_names)

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
            selected_group = request.args.get("location_group", selection_context["selected_group"])
            selected_location = request.args.get("location", selection_context["selected_location"])

            groups = selection_context["groups"]
            valid_group_names = {g["group_name"] for g in groups}
            if selected_group not in valid_group_names and groups:
                selected_group = groups[0]["group_name"]

            group_row = next((g for g in groups if g["group_name"] == selected_group), None)
            valid_locations = set(group_row["locations"]) if group_row else set()
            if selected_location not in valid_locations and group_row and group_row["locations"]:
                selected_location = group_row["locations"][0]

            location_entry = selection_context["location_to_entry"].get(selected_location)
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
        response_payload["session_status"] = _build_session_status_snapshot(battle_session)
        response_payload["selected_location_group"] = selection_context.get("selected_group", "")
        response_payload["selected_location"] = selection_context.get("selected_location", "")
        return jsonify(response_payload), 200

    return app


app = create_app()


def run_dev_server() -> None:
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_dev_server()
