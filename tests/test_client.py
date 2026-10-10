import json
from urllib.parse import parse_qs, urlsplit

import pytest

from sethucms import SethuApiError, SethuClient, and_, eq, gt
from sethucms.http import normalize_base_url


class Script:
    """A scripted transport: records requests and answers from a queue."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.seen = []

    def __call__(self, method, url, headers, body, timeout):
        parts = urlsplit(url)
        self.seen.append({
            "method": method, "path": parts.path, "query": {k: v[0] for k, v in parse_qs(parts.query).items()},
            "headers": headers, "body": json.loads(body) if body else None, "url": url,
        })
        if not self.answers:
            raise AssertionError("no scripted answer left")
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


def ok(body, status=200, headers=None):
    return status, headers or {}, json.dumps(body).encode()


def page(data, cursor=None, limit=50, notes=None):
    body = {"data": data, "page": {"nextCursor": cursor, "limit": limit}}
    if notes:
        body["meta"] = {"capabilityNotes": notes}
    return ok(body)


def client(script, **options):
    sleeps = []
    c = SethuClient("https://cms.example.com", token="tok_123", transport=script, **options)
    c._http._sleep = sleeps.append
    return c, sleeps


def test_list_builds_the_request_and_reads_the_page():
    script = Script(page([{"id": 1}], "abc", 20, ["note"]))
    c, _ = client(script)
    result = (c.collection("c 1", "orders").where(eq("status", "paid")).where(gt("total", 5))
              .order_by("created_at", "desc").order_by("id").select("id", "status").limit(20).list())
    request = script.seen[0]
    assert request["path"] == "/v1/connections/c%201/collections/orders/records"
    assert request["query"]["sort"] == "-created_at,id"
    assert request["query"]["fields"] == "id,status"
    assert request["query"]["limit"] == "20"
    assert json.loads(request["query"]["filter"]) == and_(eq("status", "paid"), gt("total", 5))
    assert (result.data, result.next_cursor, result.limit, result.notes) == ([{"id": 1}], "abc", 20, ["note"])


def test_single_filter_is_sent_as_is_and_no_filter_sends_none():
    script = Script(page([]), page([]))
    c, _ = client(script)
    col = c.collection("c", "x")
    col.where(eq("a", 1)).list()
    col.query().list()
    assert json.loads(script.seen[0]["query"]["filter"]) == eq("a", 1)
    assert "filter" not in script.seen[1]["query"]


def test_token_is_in_a_header_never_the_url_and_a_function_is_called_each_time():
    script = Script(page([]), page([]))
    calls = []
    c = SethuClient("https://cms.example.com", token=lambda: calls.append(1) or f"t{len(calls)}", transport=script)
    c.collection("c", "x").query().list()
    c.collection("c", "x").query().list()
    assert script.seen[0]["headers"]["Authorization"] == "Bearer t1"
    assert script.seen[1]["headers"]["Authorization"] == "Bearer t2"
    assert "t1" not in script.seen[0]["url"]


def test_writes_use_the_right_verbs_bodies_and_an_idempotency_key():
    script = Script(ok({"data": {"id": 1}}, 201), ok({"data": {"id": 1}}), (204, {}, b""))
    c, _ = client(script)
    col = c.collection("c", "x")
    col.create({"a": 1})
    col.update(1, {"a": 2}, idempotency_key="mine")
    col.delete(1)
    assert [s["method"] for s in script.seen] == ["POST", "PATCH", "DELETE"]
    assert script.seen[0]["body"] == {"a": 1}
    assert script.seen[0]["headers"]["Idempotency-Key"]
    assert script.seen[1]["headers"]["Idempotency-Key"] == "mine"
    assert script.seen[2]["headers"]["Idempotency-Key"]


def test_record_ids_are_encoded_so_they_cannot_change_the_path():
    script = Script(ok({"data": {}}))
    c, _ = client(script)
    c.collection("c", "x").get("../admin?x=1")
    assert script.seen[0]["path"] == "/v1/connections/c/collections/x/records/..%2Fadmin%3Fx%3D1"


def test_api_errors_become_typed_errors_with_the_request_id():
    script = Script(ok({"error": {"code": "READ_ONLY", "message": "no writes", "requestId": "r1"}}, 403))
    c, _ = client(script)
    with pytest.raises(SethuApiError) as caught:
        c.collection("c", "x").create({})
    assert (caught.value.code, caught.value.status, caught.value.request_id) == ("READ_ONLY", 403, "r1")


def test_non_json_failures_use_the_status_and_never_repeat_the_body():
    script = Script((500, {}, b"<html>secret stack trace</html>"))
    c, _ = client(script)
    with pytest.raises(SethuApiError) as caught:
        c.collection("c", "x").get(1)
    assert caught.value.code == "INTERNAL"
    assert "secret" not in str(caught.value)


def test_reads_are_retried_on_temporary_failures_honouring_retry_after():
    script = Script(ok({}, 503, {"retry-after": "2"}), ok({}, 429), page([{"id": 1}]))
    c, sleeps = client(script)
    assert c.collection("c", "x").query().list().data == [{"id": 1}]
    assert len(script.seen) == 3
    assert sleeps[0] == 2.0 and sleeps[1] > 0


def test_reads_give_up_after_max_retries_and_writes_are_never_retried():
    script = Script(ok({}, 503), ok({}, 503), ok({}, 503))
    c, _ = client(script)
    with pytest.raises(SethuApiError):
        c.collection("c", "x").get(1)
    assert len(script.seen) == 3

    script = Script(ok({}, 503))
    c, _ = client(script)
    with pytest.raises(SethuApiError):
        c.collection("c", "x").create({})
    assert len(script.seen) == 1


def test_client_errors_are_not_retried():
    script = Script(ok({"error": {"code": "NOT_FOUND", "message": "x"}}, 404))
    c, _ = client(script)
    with pytest.raises(SethuApiError) as caught:
        c.collection("c", "x").get(1)
    assert caught.value.code == "NOT_FOUND" and len(script.seen) == 1


def test_iterate_follows_cursors_until_the_last_page():
    script = Script(page([{"id": 1}, {"id": 2}], "p2"), page([{"id": 3}]))
    c, _ = client(script)
    ids = [r["id"] for r in c.collection("c", "x").query().iterate()]
    assert ids == [1, 2, 3]
    assert script.seen[1]["query"]["cursor"] == "p2"


def test_iterate_stops_with_an_error_instead_of_looping_forever():
    script = Script(*[page([{"id": 1}], "again") for _ in range(5)])
    c, _ = client(script)
    with pytest.raises(RuntimeError):
        list(c.collection("c", "x").query().iterate(max_pages=3))


def test_first_returns_one_record_or_none():
    script = Script(page([{"id": 9}]), page([]))
    c, _ = client(script)
    q = c.collection("c", "x").query()
    assert q.first() == {"id": 9}
    assert script.seen[0]["query"]["limit"] == "1"
    assert q.first() is None


def test_builders_are_immutable_so_a_base_query_can_be_reused():
    script = Script(page([]), page([]))
    c, _ = client(script)
    base = c.collection("c", "x").where(eq("a", 1))
    base.limit(5).list()
    base.list()
    assert script.seen[0]["query"]["limit"] == "5"
    assert "limit" not in script.seen[1]["query"]


def test_limit_must_be_a_positive_whole_number():
    q = SethuClient("https://cms.example.com", transport=Script()).collection("c", "x").query()
    for bad in (0, -1, 1.5, True):
        with pytest.raises(ValueError):
            q.limit(bad)


def test_base_url_safety():
    assert normalize_base_url("https://cms.example.com/") == "https://cms.example.com"
    assert normalize_base_url("http://localhost:8080") == "http://localhost:8080"
    for bad in ("http://cms.example.com", "ftp://x.com", "not a url", "https://user:pw@cms.example.com", ""):
        with pytest.raises(ValueError):
            normalize_base_url(bad)
    assert normalize_base_url("http://cms.internal", allow_insecure_http=True)


def test_network_failure_and_timeout_become_typed_errors():
    c, _ = client(Script(TimeoutError()), max_retries=0)
    with pytest.raises(SethuApiError) as caught:
        c.collection("c", "x").get(1)
    assert caught.value.code == "TIMEOUT" and caught.value.status == 0

    c, _ = client(Script(OSError("boom")), max_retries=0)
    with pytest.raises(SethuApiError) as caught:
        c.collection("c", "x").get(1)
    assert caught.value.code == "CONNECTION_FAILED"
    assert "boom" not in str(caught.value)


def test_network_failures_on_reads_are_retried_but_timeouts_are_not():
    script = Script(OSError("x"), page([]))
    c, _ = client(script)
    c.collection("c", "x").query().list()
    assert len(script.seen) == 2

    script = Script(TimeoutError(), page([]))
    c, _ = client(script)
    with pytest.raises(SethuApiError):
        c.collection("c", "x").query().list()
    assert len(script.seen) == 1


def test_health_check_never_raises():
    c, _ = client(Script(OSError("x"), OSError("x"), OSError("x")))
    assert c.is_healthy() is False
    c, _ = client(Script(ok({"status": "ok"})))
    assert c.is_healthy() is True
