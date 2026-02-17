# adapters/flask_app.py
# create_app() でエラーハンドラ登録、JSON受信、DTO変換、
# execute_round_dto 呼び出し、JSONレスポンス返却までを接続
from __future__ import annotations

import os
from pathlib import Path
from random import Random
from typing import Sequence

from flask import Flask, jsonify, render_template, request

from adapters.flask_error_handlers import register_flask_error_handlers
from combat.dto import ExecuteRoundInputDTO, parse_execute_round_input_dict, to_json_ready_dict
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


def create_app(
    *,
    session: BattleSession | None = None,
    rng: Random | None = None,
    enemy_names: Sequence[str] | None = None,
) -> Flask:
    template_dir = Path(__file__).resolve().parents[1] / "templates"
    app = Flask(__name__, template_folder=str(template_dir))
    register_flask_error_handlers(app)

    battle_session = session or _build_default_session(enemy_names=enemy_names)
    round_rng = rng or Random()

    @app.get("/")
    def index():
        return render_template(
            "top.html",
            expected_action_count=len(battle_session.party_members),
            default_lifecycle="ready_for_actions",
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
        return jsonify(to_json_ready_dict(output_dto)), 200

    return app


app = create_app()


def run_dev_server() -> None:
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_dev_server()
