"""Consistent JSON error responses for the public API."""

from __future__ import annotations

from flask import jsonify


def error_response(code: str, message: str, status: int):
    return (
        jsonify(
            {
                "ok": False,
                "error": {
                    "code": code,
                    "message": message,
                },
            }
        ),
        status,
    )
