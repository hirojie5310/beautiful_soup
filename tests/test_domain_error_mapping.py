# teststest_domain_error_mapping.py
from combat.dto import DTOValidationError
from combat.errors import InputValidationError, InvalidLifecycleError
from adapters.flask_error_handlers import (
    map_domain_error_to_http,
    map_unexpected_error_to_http,
)


def test_dto_validation_error_is_input_validation_error() -> None:
    error = DTOValidationError("invalid payload")
    assert isinstance(error, InputValidationError)


def test_invalid_lifecycle_error_payload_and_status() -> None:
    error = InvalidLifecycleError("bad transition", details={"before": "ready"})
    payload, status = map_domain_error_to_http(error)

    assert status == 409
    assert payload["error"]["code"] == "invalid_lifecycle"
    assert payload["error"]["details"]["before"] == "ready"


def test_unexpected_error_mapping_masks_internal_message() -> None:
    payload, status = map_unexpected_error_to_http(RuntimeError("secret detail"))

    assert status == 500
    assert payload["error"]["code"] == "internal_domain_error"
