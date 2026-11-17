"""The last step: write validated records into a SethuCMS collection through the SDK."""
from __future__ import annotations

import hashlib
import json
from typing import Protocol

from sethucms import SethuClient

from .models import Record


class Sink(Protocol):
    def land(self, record: Record) -> str: ...


class SethuSink:
    """Creates records in one SethuCMS collection.

    The idempotency key is made from the record itself, so running the same workflow twice on
    the same page cannot create the same record twice. The gateway answers a repeated key with
    the first result instead of writing again.
    """

    def __init__(self, client: SethuClient, connection_id: str, collection_name: str) -> None:
        self._collection = client.collection(connection_id, collection_name)
        self._scope = f"{connection_id}/{collection_name}"

    def land(self, record: Record) -> str:
        key = idempotency_key_for(self._scope, record)
        created = self._collection.create(record, idempotency_key=key)
        return str(created.get("id", ""))


def idempotency_key_for(scope: str, record: Record) -> str:
    """A stable key: the same scope and the same record always give the same key."""
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(f"{scope}\n{canonical}".encode("utf-8")).hexdigest()
    return f"auto-{digest[:48]}"
