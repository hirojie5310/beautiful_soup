# tests/test_battle_lifecycle_dto.py
# 契約テストの足場として、
# DTO ライフサイクル関連の関数・データ構造が期待どおり動くかを確認する ユニットテスト
# DTO/ライフサイクル周辺の「契約」をピンポイントで守るためのテスト
from combat.dto import (
    ExecuteRoundInputDTO,
    derive_round_lifecycle,
    to_json_ready_dict,
)


def test_derive_round_lifecycle_continue_to_next_round() -> None:
    lifecycle = derive_round_lifecycle(
        current_state="ready_for_actions",
        end_reason="continue",
    )

    assert lifecycle.before == "resolving_round"
    assert lifecycle.after == "ready_for_next_round"
    assert lifecycle.battle_finished is False


def test_derive_round_lifecycle_terminal_to_finished() -> None:
    lifecycle = derive_round_lifecycle(
        current_state="ready_for_actions",
        end_reason="enemy_defeated",
    )

    assert lifecycle.before == "resolving_round"
    assert lifecycle.after == "battle_finished"
    assert lifecycle.battle_finished is True


def test_derive_round_lifecycle_rejects_invalid_start_state() -> None:
    try:
        derive_round_lifecycle(
            current_state="ready_for_next_round",
            end_reason="continue",
        )
    except ValueError as exc:
        assert "ready_for_actions" in str(exc)
    else:
        raise AssertionError("ValueError expected")


def test_execute_round_input_default_lifecycle_state() -> None:
    request = ExecuteRoundInputDTO(planned_actions=[])
    assert request.lifecycle_state == "ready_for_actions"


def test_to_json_ready_dict_includes_lifecycle() -> None:
    from combat.dto import BattleLifecycleDTO, ExecuteRoundOutputDTO

    dto = ExecuteRoundOutputDTO(
        logs=[],
        end_reason="continue",
        escaped=False,
        enemy_was_physically_hit=False,
        events=[],
        lifecycle=BattleLifecycleDTO(
            before="resolving_round",
            after="ready_for_next_round",
            battle_finished=False,
        ),
    )

    payload = to_json_ready_dict(dto)
    assert payload["lifecycle"]["before"] == "resolving_round"
    assert payload["lifecycle"]["after"] == "ready_for_next_round"
    assert payload["lifecycle"]["battle_finished"] is False
