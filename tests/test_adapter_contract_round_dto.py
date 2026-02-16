# tests/test_adapter_contract_round_dto.py
# アダプタ契約テストとして、
# 正常系（最小 payload / nullable action）と
# 異常系（planned_actions 非 list、target_side 不正値、lifecycle_state 非文字列）をカバー
from combat.dto import DTOValidationError, parse_execute_round_input_dict


def test_parse_execute_round_input_dict_accepts_minimal_payload() -> None:
    dto = parse_execute_round_input_dict({"planned_actions": []})
    assert dto.lifecycle_state == "ready_for_actions"
    assert dto.planned_actions == []


def test_parse_execute_round_input_dict_accepts_nullable_actions() -> None:
    dto = parse_execute_round_input_dict(
        {
            "planned_actions": [
                None,
                {
                    "kind": "physical",
                    "target_side": "enemy",
                    "target_index": 0,
                    "target_all": False,
                },
            ],
            "lifecycle_state": "ready_for_actions",
        }
    )

    assert dto.planned_actions[0] is None
    assert dto.planned_actions[1] is not None
    assert dto.planned_actions[1].kind == "physical"


def test_parse_execute_round_input_dict_rejects_non_list_planned_actions() -> None:
    try:
        parse_execute_round_input_dict({"planned_actions": {}})
    except DTOValidationError as exc:
        assert "planned_actions" in str(exc)
    else:
        raise AssertionError("DTOValidationError expected")


def test_parse_execute_round_input_dict_rejects_invalid_target_side() -> None:
    try:
        parse_execute_round_input_dict(
            {
                "planned_actions": [
                    {
                        "kind": "physical",
                        "target_side": "invalid",
                    }
                ]
            }
        )
    except DTOValidationError as exc:
        assert "target_side" in str(exc)
    else:
        raise AssertionError("DTOValidationError expected")


def test_parse_execute_round_input_dict_rejects_non_string_lifecycle() -> None:
    try:
        parse_execute_round_input_dict(
            {
                "planned_actions": [],
                "lifecycle_state": 100,
            }
        )
    except DTOValidationError as exc:
        assert "lifecycle_state" in str(exc)
    else:
        raise AssertionError("DTOValidationError expected")
