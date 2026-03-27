# tests/test_execute_round_end_reason_guard.py
from random import Random
from types import SimpleNamespace
from typing import cast

from combat.dto import ExecuteRoundInputDTO
from combat.models import BattleActorState, SideTurnResult
from combat.usecases import BattleSession, execute_round_dto


def test_execute_round_dto_downgrades_false_enemy_defeated_when_enemy_alive(
    monkeypatch,
):
    session = cast(
        BattleSession,
        SimpleNamespace(
            enemies=[SimpleNamespace(state=BattleActorState(hp=10, max_hp=10))]
        ),
    )

    def _fake_execute_round(*, session, planned_actions, rng):
        del session, planned_actions, rng
        return SimpleNamespace(
            logs=["dummy"],
            round_result=SideTurnResult(end_reason="enemy_defeated"),
            event=[],
        )

    monkeypatch.setattr("combat.usecases.execute_round", _fake_execute_round)

    out = execute_round_dto(
        session=session,
        request=ExecuteRoundInputDTO(planned_actions=[]),
        rng=Random(0),
    )

    assert out.end_reason == "continue"
    assert out.lifecycle.after == "ready_for_next_round"
