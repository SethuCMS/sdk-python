"""The request pipeline: authentication, timeouts, retries and error handling."""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Union
from urllib.parse import urlencode, urlsplit

from .errors import SethuApiError, error_from_response

TokenSource = Union[str, Callable[[], str]]

#: A transport sends one request and returns (status, headers, body bytes).
#: It raises TimeoutError on timeout and OSError for any other network failure.
#: Tests (and special environments) can pass their own.
Transport = Callable[[str, str, Dict[str, str], Optional[bytes], float], Tuple[int, Mapping[str, str], bytes]]

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_RETRYABLE_STATUS = {429, 502, 503, 504}


def normalize_base_url(raw: str, allow_insecure_http: bool = False) -> str:
    try:
        parts = urlsplit(raw)
        hostname = parts.hostname
    except ValueError:
        raise ValueError("base_url must be a valid URL") from None
    if parts.scheme not in ("https", "http") or not hostname:
        raise ValueError("base_url must use https")
    if parts.scheme == "http" and hostname not in _LOCAL_HOSTS and not allow_insecure_http:
        raise ValueError("base_url must use https. Plain http is only allowed for localhost.")
    if parts.username or parts.password:
        raise ValueError("base_url must not contain credentials. Pass a token instead.")
    return raw.rstrip("/")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects: the Authorization header must not travel to another address."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
        return None


def urllib_transport(method: str, url: str, headers: Dict[str, str], body: Optional[bytes], timeout: float):
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as error:  # a real answer with a failure status
        try:
            return error.code, dict(error.headers.items()), error.read()
        finally:
            error.close()
    except TimeoutError:
        raise
    except urllib.error.URLError as error:
        if isinstance(error.reason, TimeoutError):
            raise TimeoutError() from None
        raise OSError(str(error.reason)) from None


class HttpClient:
    def __init__(
        self,
        base_url: str,
        *,
        token: Optional[TokenSource] = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        allow_insecure_http: bool = False,
        transport: Optional[Transport] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = normalize_base_url(base_url, allow_insecure_http)
        self._token = token
        self._timeout = timeout
        self._max_retries = max_retries
        self._transport = transport or urllib_transport
        self._sleep = sleep

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Mapping[str, Optional[str]]] = None,
        body: Any = None,
        idempotency_key: Optional[str] = None,
    ) -> Any:
        # Only reads are retried. A retried write could happen twice.
        attempts = self._max_retries + 1 if method == "GET" else 1
        attempt = 0
        while True:
            attempt += 1
            try:
                return self._send(method, path, query, body, idempotency_key)
            except SethuApiError as error:
                if attempt >= attempts or not _is_retryable(error):
                    raise
                self._sleep(_backoff_seconds(attempt, error))

    def _send(self, method, path, query, body, idempotency_key) -> Any:
        url = self.base_url + path
        pairs = {k: v for k, v in (query or {}).items() if v is not None}
        if pairs:
            url += "?" + urlencode(pairs)

        headers = {"Accept": "application/json"}
        token = self._token() if callable(self._token) else self._token
        if token:
            headers["Authorization"] = f"Bearer {token}"  # a header, never the URL
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        try:
            status, response_headers, raw = self._transport(method, url, headers, data, self._timeout)
        except TimeoutError as error:
            raise SethuApiError("TIMEOUT", "The request took too long", status=0) from error
        except OSError as error:
            raise SethuApiError("CONNECTION_FAILED", "Could not reach the server", status=0) from error

        parsed = _parse_json(raw) if status != 204 else None
        if 200 <= status < 300:
            return parsed
        error = error_from_response(status, parsed)
        retry_after = _header(response_headers, "Retry-After")
        try:
            seconds = float(retry_after) if retry_after is not None else 0.0
        except ValueError:
            seconds = 0.0
        if seconds > 0:
            error.retry_after_seconds = seconds
        raise error


def _header(headers: Mapping[str, str], name: str) -> Optional[str]:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def _parse_json(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None  # not JSON (for example an HTML error page); callers handle the missing body


def _is_retryable(error: SethuApiError) -> bool:
    if error.status == 0:
        return error.code == "CONNECTION_FAILED"
    return error.status in _RETRYABLE_STATUS


def _backoff_seconds(attempt: int, error: SethuApiError) -> float:
    if error.retry_after_seconds is not None:
        return min(error.retry_after_seconds, 10.0)
    return min(0.2 * 2 ** (attempt - 1), 5.0) * (0.5 + random.random() / 2)
