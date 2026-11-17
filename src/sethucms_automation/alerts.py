"""Alerts: tell a human when a run needs attention. An alert must never break a run."""
from __future__ import annotations

import json
import urllib.request
from typing import Protocol

from .logs import log_event


class Alerter(Protocol):
    def send(self, message: str) -> None: ...


class NullAlerter:
    """Does nothing. The default when no webhook is set."""

    def send(self, message: str) -> None:
        return None


class WebhookAlerter:
    """Posts {"text": message} to a webhook. Slack and Discord-compatible hooks accept this shape."""

    def __init__(self, webhook_url: str, timeout: float = 10.0) -> None:
        if not webhook_url.startswith("https://"):
            raise ValueError("The alert webhook must use https.")
        self._url = webhook_url
        self._timeout = timeout

    def send(self, message: str) -> None:
        body = json.dumps({"text": message}).encode("utf-8")
        request = urllib.request.Request(
            self._url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout):
                pass
        except Exception as error:  # an alert failing must not fail the workflow
            log_event("alert_failed", error_type=type(error).__name__)
