"""The workflow: runs the steps in order, keeps a report, and raises an alert when something is wrong."""
from __future__ import annotations

import time
import uuid
from typing import Callable, Optional, Sequence
from urllib.parse import urlsplit

from .alerts import Alerter, NullAlerter
from .extract import ExtractionError, Extractor
from .logs import log_event
from .models import FieldSpec, RunReport
from .retry import with_retries
from .sink import Sink
from .sources import PageSource
from .store import RunStore
from .validate import validate_record


class Workflow:
    """One scrape-and-land job. Build it once, call `run(url)` as often as you like."""

    def __init__(
        self,
        *,
        source: PageSource,
        extractor: Extractor,
        fields: Sequence[FieldSpec],
        sink: Sink,
        store: RunStore,
        alerter: Optional[Alerter] = None,
        name: str = "workflow",
        attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._source = source
        self._extractor = extractor
        self._fields = list(fields)
        self._sink = sink
        self._store = store
        self._alerter = alerter or NullAlerter()
        self._name = name
        self._attempts = attempts
        self._sleep = sleep

    def run(self, url: str) -> RunReport:
        """Run every step once. Never raises: any failure is written into the returned report."""
        report = RunReport(run_id=str(uuid.uuid4()), url=_without_query(url))
        self._store.save(report)
        log_event("run_started", run_id=report.run_id, workflow=self._name)

        try:
            self._run_steps(url, report)
        except Exception as error:  # a run must always end with a saved report and an alert
            report.status = "failed"
            report.error = type(error).__name__
            log_event("run_crashed", run_id=report.run_id, error_type=report.error)

        self._finish(report)
        return report

    def _run_steps(self, url: str, report: RunReport) -> None:
        # Reading steps are safe to retry. The write step below is not retried.
        page = with_retries(
            lambda: self._source.fetch(url),
            name="fetch",
            attempts=self._attempts,
            sleep=self._sleep,
        )
        records = with_retries(
            lambda: self._extractor.extract(page.text, self._fields),
            name="extract",
            attempts=self._attempts,
            retry_on=(ExtractionError,),
            sleep=self._sleep,
        )
        report.extracted = len(records)

        if not records:
            # An empty page usually means the site changed, not that there is nothing to do.
            report.status = "failed"
            report.problems.append("no records were found on the page")
            return

        for index, record in enumerate(records, start=1):
            cleaned, problems = validate_record(record, self._fields, page.text)
            if problems:
                report.rejected += 1
                report.problems.extend(f"record {index}: {problem}" for problem in problems)
                continue
            try:
                self._sink.land(cleaned)
                report.landed += 1
            except Exception as error:
                report.failed += 1
                report.problems.append(f"record {index}: could not be written ({type(error).__name__})")

        report.status = "succeeded" if report.landed == report.extracted else "partial"
        if report.landed == 0:
            report.status = "failed"

    def _finish(self, report: RunReport) -> None:
        report.problems = report.problems[:50]  # keep reports small
        self._store.save(report)
        log_event(
            "run_finished",
            run_id=report.run_id,
            status=report.status,
            extracted=report.extracted,
            landed=report.landed,
            rejected=report.rejected,
            failed=report.failed,
        )
        if report.status != "succeeded":
            self._alerter.send(
                f"{self._name}: run {report.run_id} ended '{report.status}' "
                f"({report.landed}/{report.extracted} landed, {report.rejected} rejected, {report.failed} failed)"
            )


def _without_query(url: str) -> str:
    """Drop the query string and fragment before the address is saved: they can hold secrets."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"
