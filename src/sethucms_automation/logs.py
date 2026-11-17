"""Logging that is safe to leave on in production.

Rule from the SethuCMS gateway: never log record values, tokens or query strings.
`log_event` only accepts short keys and simple numbers or words, and refuses long text.
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

_LOGGER_NAME = "sethucms_automation"
_MAX_VALUE_LENGTH = 80


def get_logger() -> logging.Logger:
    """Return the package logger. It writes to stderr, one JSON object per line."""
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_event(event: str, level: int = logging.INFO, **details: Any) -> None:
    """Write one log line such as {"event": "page_fetched", "run_id": "..."}."""
    safe = {"event": event}
    for key, value in details.items():
        safe[key] = _make_safe(value)
    get_logger().log(level, json.dumps(safe, sort_keys=True))


def _make_safe(value: Any) -> Any:
    """Keep numbers, booleans and short words. Anything longer is replaced by its length."""
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    text = str(value)
    if len(text) <= _MAX_VALUE_LENGTH:
        return text
    return f"<{len(text)} characters hidden>"
