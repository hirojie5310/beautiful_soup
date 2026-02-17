# adapters/flask_error_handlers.py
# Flask 向けの雛形
# map_domain_error_to_http
# map_unexpected_error_to_http
# register_flask_error_handlers
# ドメインエラーはそのままHTTP化、想定外例外はマスクして 500 応答する設計
from __future__ import annotations

from typing import Any

from combat.errors import DomainError, InternalDomainError


def map_domain_error_to_http(error: DomainError) -> tuple[dict[str, Any], int]:
    """Map domain errors to a JSON payload and HTTP status."""
    return error.to_payload(), error.http_status


def map_unexpected_error_to_http(error: Exception) -> tuple[dict[str, Any], int]:
    """Fallback mapping for non-domain exceptions."""
    # Keep original message out of API response to avoid accidental leaks.
    del error
    internal = InternalDomainError()
    return internal.to_payload(), internal.http_status


def register_flask_error_handlers(app: Any) -> None:
    """Register Flask error handlers.

    Template usage:

        from flask import Flask
        from adapters.flask_error_handlers import register_flask_error_handlers

        app = Flask(__name__)
        register_flask_error_handlers(app)
    """

    from flask import jsonify
    from werkzeug.exceptions import HTTPException

    @app.errorhandler(DomainError)
    def handle_domain_error(error: DomainError):
        payload, status = map_domain_error_to_http(error)
        return jsonify(payload), status

    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException):
        # Preserve Flask/Werkzeug HTTP semantics (404/405/etc.)
        payload = {
            "error": {
                "code": "http_error",
                "message": error.description,
                "details": {"name": error.name},
            }
        }
        return jsonify(payload), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        payload, status = map_unexpected_error_to_http(error)
        return jsonify(payload), status
