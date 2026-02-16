# combat/errors.py
# このリポジトリ向けの DomainError 階層
# （InputValidationError / InvalidLifecycleError / StateNotInitializedError / InternalDomainError）
# code・http_status・details を持つ API 向けエラー表現を定義
# to_payload() で Flask 返却に直接使える形
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(eq=False)
class DomainError(Exception):
    """Domain/Application boundary error base class.

    Flask adapter should map this family to API error responses.
    """

    message: str
    code: str = "domain_error"
    http_status: int = 400
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class InputValidationError(DomainError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="input_validation_error",
            http_status=422,
            details=details or {},
        )


class InvalidLifecycleError(DomainError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="invalid_lifecycle",
            http_status=409,
            details=details or {},
        )


class StateNotInitializedError(DomainError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            code="state_not_initialized",
            http_status=500,
            details=details or {},
        )


class InternalDomainError(DomainError):
    def __init__(self, message: str = "Internal domain error") -> None:
        super().__init__(
            message=message,
            code="internal_domain_error",
            http_status=500,
            details={},
        )
