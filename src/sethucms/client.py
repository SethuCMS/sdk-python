"""The entry point of the SDK."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote

from .collection import Collection
from .errors import SethuApiError
from .http import HttpClient, TokenSource, Transport


class SethuClient:
    """::

        cms = SethuClient("https://cms.example.com", token=lambda: get_access_token())
        orders = cms.collection("conn_123", "orders")
        page = orders.where(eq("status", "paid")).order_by("created_at", "desc").limit(20).list()
    """

    def __init__(
        self,
        base_url: str,
        *,
        token: Optional[TokenSource] = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        allow_insecure_http: bool = False,
        transport: Optional[Transport] = None,
    ) -> None:
        self._http = HttpClient(
            base_url, token=token, timeout=timeout, max_retries=max_retries,
            allow_insecure_http=allow_insecure_http, transport=transport,
        )

    def collection(self, connection_id: str, name: str) -> Collection:
        return Collection(self._http, connection_id, name)

    def connections(self) -> List[Dict[str, Any]]:
        return self._http.request("GET", "/v1/connections")["data"]

    def collections(self, connection_id: str) -> List[Dict[str, Any]]:
        return self._http.request("GET", f"/v1/connections/{quote(connection_id, safe='')}/collections")["data"]

    def is_healthy(self) -> bool:
        """True when the gateway reports that it is ready. Never raises."""
        try:
            self._http.request("GET", "/v1/health")
            return True
        except SethuApiError:
            return False
