"""Reading and writing records of one collection."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import quote

from .filters import Filter, and_
from .http import HttpClient

Record = Dict[str, Any]


def _enc(value: Any) -> str:
    return quote(str(value), safe="")


@dataclass(frozen=True)
class ListResult:
    data: List[Record]
    #: Pass to ``after()`` to get the next page. None on the last page.
    next_cursor: Optional[str]
    limit: int
    #: Notes from the server, for example "sorting needs an index".
    notes: List[str] = field(default_factory=list)


class Collection:
    """One collection of one connection. Create it with ``client.collection(connection_id, name)``."""

    def __init__(self, http: HttpClient, connection_id: str, name: str) -> None:
        self._http = http
        self._base = f"/v1/connections/{_enc(connection_id)}/collections/{_enc(name)}/records"

    def query(self) -> "QueryBuilder":
        return QueryBuilder(self)

    def where(self, filter: Filter) -> "QueryBuilder":
        return self.query().where(filter)

    def get(self, id: Any) -> Record:
        return self._http.request("GET", f"{self._base}/{_enc(id)}")["data"]

    def create(self, values: Record, *, idempotency_key: Optional[str] = None) -> Record:
        """Create a record. A random idempotency key is added so a retried write cannot happen twice."""
        return self._http.request("POST", self._base, body=values, idempotency_key=idempotency_key or _new_key())["data"]

    def update(self, id: Any, values: Record, *, idempotency_key: Optional[str] = None) -> Record:
        return self._http.request("PATCH", f"{self._base}/{_enc(id)}", body=values, idempotency_key=idempotency_key or _new_key())["data"]

    def delete(self, id: Any, *, idempotency_key: Optional[str] = None) -> None:
        self._http.request("DELETE", f"{self._base}/{_enc(id)}", idempotency_key=idempotency_key or _new_key())

    def _run_list(self, state: "_QueryState") -> ListResult:
        filters = state.filters
        response = self._http.request("GET", self._base, query={
            "filter": None if not filters else json.dumps(filters[0] if len(filters) == 1 else and_(*filters), separators=(",", ":")),
            "sort": None if not state.sorts else ",".join(f"-{f}" if d == "desc" else f for f, d in state.sorts),
            "fields": None if not state.fields else ",".join(state.fields),
            "limit": None if state.limit is None else str(state.limit),
            "cursor": state.cursor,
        })
        page = response.get("page", {})
        return ListResult(
            data=response["data"],
            next_cursor=page.get("nextCursor"),
            limit=page.get("limit", 0),
            notes=(response.get("meta") or {}).get("capabilityNotes") or [],
        )


@dataclass(frozen=True)
class _QueryState:
    filters: tuple = ()
    sorts: tuple = ()
    fields: tuple = ()
    limit: Optional[int] = None
    cursor: Optional[str] = None


class QueryBuilder:
    """A query under construction. Every method returns a new builder, so builders can be reused safely."""

    def __init__(self, collection: Collection, state: Optional[_QueryState] = None) -> None:
        self._collection = collection
        self._state = state or _QueryState()

    def _with(self, **change: Any) -> "QueryBuilder":
        values = {**self._state.__dict__, **change}
        return QueryBuilder(self._collection, _QueryState(**values))

    def where(self, filter: Filter) -> "QueryBuilder":
        """Add a filter. Calling this more than once means "all of these must match"."""
        return self._with(filters=self._state.filters + (filter,))

    def order_by(self, field: str, direction: str = "asc") -> "QueryBuilder":
        if direction not in ("asc", "desc"):
            raise ValueError("direction must be 'asc' or 'desc'")
        return self._with(sorts=self._state.sorts + ((field, direction),))

    def select(self, *fields: str) -> "QueryBuilder":
        """Return only these fields."""
        return self._with(fields=self._state.fields + tuple(fields))

    def limit(self, count: int) -> "QueryBuilder":
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError("limit must be a whole number of at least 1")
        return self._with(limit=count)

    def after(self, cursor: Optional[str]) -> "QueryBuilder":
        """Continue after a previous page."""
        return self._with(cursor=cursor)

    def list(self) -> ListResult:
        """Fetch one page."""
        return self._collection._run_list(self._state)

    def first(self) -> Optional[Record]:
        """The first matching record, or None."""
        data = self.limit(1).list().data
        return data[0] if data else None

    def iterate(self, *, max_pages: int = 10_000) -> Iterator[Record]:
        """Walk every matching record, page after page::

            for order in orders.where(eq("status", "paid")).iterate():
                ...
        """
        builder: QueryBuilder = self
        for _ in range(max_pages):
            result = builder.list()
            yield from result.data
            if not result.next_cursor:
                return
            builder = builder.after(result.next_cursor)
        raise RuntimeError(f"Stopped after {max_pages} pages. Raise max_pages if this is expected.")


def _new_key() -> str:
    return str(uuid.uuid4())
