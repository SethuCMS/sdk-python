# sethucms (Python SDK)

Python client for the SethuCMS API. Python 3.9+, no dependencies (standard library only).

```python
from sethucms import SethuClient, SethuApiError, eq, gt

cms = SethuClient("https://cms.example.com", token=lambda: get_access_token())
orders = cms.collection("conn_123", "orders")

# One page
page = (orders.where(eq("status", "paid")).where(gt("total", 100))
        .order_by("created_at", "desc").limit(20).list())
print(page.data, page.next_cursor)

# Every matching record, page after page
for order in orders.where(eq("status", "paid")).iterate():
    print(order)

# Writes (a random idempotency key is added, so a retried write cannot happen twice)
created = orders.create({"status": "new"})
orders.update(created["id"], {"status": "paid"})
orders.delete(created["id"])
```

## Errors

Every failure raises `SethuApiError` with a stable `code`:

```python
try:
    orders.create({"status": "new"})
except SethuApiError as error:
    if error.code == "READ_ONLY":
        ...  # this connection does not allow writes
    print(error.request_id)  # quote this when asking for support
```

Codes: `CONNECTION_FAILED`, `AUTH_FAILED`, `FORBIDDEN`, `READ_ONLY`, `NOT_FOUND`, `CONFLICT`,
`VALIDATION_FAILED`, `CAPABILITY_UNSUPPORTED`, `RATE_LIMITED`, `TIMEOUT`, `INTERNAL`.

## Safety defaults

- `https` only (plain `http` only for localhost). A URL with a password in it is refused.
- The token travels in a header, never in the URL.
- Redirects are never followed, so the token cannot be sent to another address.
- Reads are retried (rate limits, 502/503/504, network errors) and honour `Retry-After`; writes are never retried.
- Error messages never repeat the server's raw response or the network library's message.
- The default timeout is 30 seconds.

## Filters

`eq, ne, lt, lte, gt, gte, is_in, not_in, contains, starts_with, exists` and the combinators
`and_, or_, not_`. They return plain dicts, so a filter can be stored as JSON.

## Develop

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
```
