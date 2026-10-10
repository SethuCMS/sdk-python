"""Errors raised by the SDK.

Every failed API call raises ``SethuApiError``. Check ``error.code`` to decide what to do.
"""
from __future__ import annotations

from typing import Any, Optional

KNOWN_CODES = frozenset({
    "CONNECTION_FAILED", "AUTH_FAILED", "FORBIDDEN", "READ_ONLY", "NOT_FOUND", "CONFLICT",
    "VALIDATION_FAILED", "CAPABILITY_UNSUPPORTED", "RATE_LIMITED", "TIMEOUT", "INTERNAL",
})


class SethuApiError(Exception):
    """A failed API call."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int,
        details: Any = None,
        request_id: Optional[str] = None,
        retry_after_seconds: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        #: HTTP status, or 0 when the request never reached the server.
        self.status = status
        self.details = details
        #: Quote this when asking for support.
        self.request_id = request_id
        self.retry_after_seconds = retry_after_seconds

    def __repr__(self) -> str:
        return f"SethuApiError(code={self.code!r}, status={self.status}, message={self.message!r})"


def code_from_status(status: int) -> str:
    if status in (400, 422):
        return "VALIDATION_FAILED"
    return {
        401: "AUTH_FAILED", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "CONFLICT",
        429: "RATE_LIMITED", 502: "CONNECTION_FAILED", 504: "TIMEOUT",
    }.get(status, "INTERNAL")


def error_from_response(status: int, body: Any) -> SethuApiError:
    """Build an error from a failed response body.

    Never repeats the raw body, which could be an HTML error page.
    """
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message")
        request_id = error.get("requestId")
        return SethuApiError(
            code if isinstance(code, str) and code in KNOWN_CODES else code_from_status(status),
            message if isinstance(message, str) else "Request failed",
            status=status,
            details=error.get("details"),
            request_id=request_id if isinstance(request_id, str) else None,
        )
    return SethuApiError(code_from_status(status), f"The server answered with status {status}", status=status)
