# sethucms_automation

Workflows that pull data from websites, check it, and land it in SethuCMS.

```
fetch page  ->  AI extracts fields  ->  validate  ->  write to SethuCMS
(Playwright)    (Claude or any LLM)      (rules)      (sethucms SDK)
                                           |
                        rejected records are reported, never written
```

## Why it is safe to leave running

- **Only validated records reach the CMS.** Each value is checked for type, range and pattern. Text values must also appear on the page, so a value the AI invented is rejected.
- **Re-running cannot duplicate records.** The write uses an idempotency key made from the record itself.
- **Reads retry, writes do not.** Fetching and extracting retry with backoff. The write step never retries.
- **An empty page is a failure, not a success.** It usually means the site changed, and it raises an alert.
- **Logs and reports hold no record values.** Problems name the field and the rule only. Web addresses are saved without their query string.
- **The AI step cannot take orders from the page.** The page is sent as data and the prompt says to ignore instructions inside it. The validation step is the real protection.
- **The API checks who is calling and where.** Bearer token compared in constant time, `https` only, and only hosts on `allowed_hosts` (so the service cannot be pointed at internal addresses).

## Use it

```python
from sethucms import SethuClient
from sethucms_automation import FieldSpec, Workflow
from sethucms_automation.extract import LlmExtractor, anthropic_completer
from sethucms_automation.sink import SethuSink
from sethucms_automation.sources import PlaywrightSource
from sethucms_automation.store import PostgresRunStore
from sethucms_automation.alerts import WebhookAlerter

cms = SethuClient("https://cms.example.com", token="...")
workflow = Workflow(
    source=PlaywrightSource(),
    extractor=LlmExtractor(anthropic_completer()),
    fields=[FieldSpec("code", pattern=r"T-\d+"), FieldSpec("value", kind="integer", minimum=1)],
    sink=SethuSink(cms, "conn_123", "tenders"),
    store=PostgresRunStore("postgresql://user:password@host/db"),
    alerter=WebhookAlerter("https://hooks.example.com/..."),
)
report = workflow.run("https://portal.example.com/tenders")
print(report.status, report.landed, report.rejected)
```

Serve it with FastAPI: `create_app(workflow, store, api_token=..., allowed_hosts=["portal.example.com"])`, then `uvicorn`.

## Install

```bash
pip install -e ".[automation,dev]"
playwright install chromium     # only for PlaywrightSource
pytest
```

## What has and has not been tested

Tested (the tests in `tests/test_automation.py`): validation, extraction parsing, retries, the workflow including rejected, failed and empty runs, the SDK write with its idempotency key, and the FastAPI routes. Browser, AI model, network and database are **faked** in those tests.

Not tested: a real Playwright run against a real site, a real model call, a real PostgreSQL database (`PostgresRunStore`), a real SethuCMS gateway, and the webhook alert. Run each once against the real thing before relying on it.
