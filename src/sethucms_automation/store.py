"""Where run reports are kept, so you can see what happened yesterday without reading logs."""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Dict, List, Optional, Protocol

from .models import RunReport


class RunStore(Protocol):
    def save(self, report: RunReport) -> None: ...

    def get(self, run_id: str) -> Optional[RunReport]: ...

    def recent(self, limit: int = 20) -> List[RunReport]: ...


class MemoryRunStore:
    """Keeps reports in memory. For tests and for trying things out locally."""

    def __init__(self) -> None:
        self._reports: Dict[str, RunReport] = {}

    def save(self, report: RunReport) -> None:
        self._reports[report.run_id] = RunReport(**asdict(report))

    def get(self, run_id: str) -> Optional[RunReport]:
        found = self._reports.get(run_id)
        return RunReport(**asdict(found)) if found else None

    def recent(self, limit: int = 20) -> List[RunReport]:
        return list(self._reports.values())[-limit:][::-1]


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS automation_runs (
    run_id     text PRIMARY KEY,
    url        text NOT NULL,
    status     text NOT NULL,
    extracted  integer NOT NULL DEFAULT 0,
    landed     integer NOT NULL DEFAULT 0,
    rejected   integer NOT NULL DEFAULT 0,
    failed     integer NOT NULL DEFAULT 0,
    problems   jsonb NOT NULL DEFAULT '[]'::jsonb,
    error      text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)
"""

# Every value goes in as a parameter (%s). No SQL is built from text.
_UPSERT = """
INSERT INTO automation_runs (run_id, url, status, extracted, landed, rejected, failed, problems, error)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
ON CONFLICT (run_id) DO UPDATE SET
    status = EXCLUDED.status,
    extracted = EXCLUDED.extracted,
    landed = EXCLUDED.landed,
    rejected = EXCLUDED.rejected,
    failed = EXCLUDED.failed,
    problems = EXCLUDED.problems,
    error = EXCLUDED.error,
    updated_at = now()
"""

_COLUMNS = "run_id, url, status, extracted, landed, rejected, failed, problems, error"


class PostgresRunStore:
    """Keeps reports in a PostgreSQL table called automation_runs.

    Install first:  pip install "psycopg[binary]"
    Pass a connection string such as the DATABASE_URL your host gives you.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._ensure_table()

    def _connect(self):
        # Imported here so the package works without psycopg when you use the memory store.
        import psycopg

        return psycopg.connect(self._dsn)

    def _ensure_table(self) -> None:
        with self._connect() as connection:
            connection.execute(_CREATE_TABLE)

    def save(self, report: RunReport) -> None:
        with self._connect() as connection:
            connection.execute(
                _UPSERT,
                (
                    report.run_id,
                    report.url,
                    report.status,
                    report.extracted,
                    report.landed,
                    report.rejected,
                    report.failed,
                    json.dumps(report.problems),
                    report.error,
                ),
            )

    def get(self, run_id: str) -> Optional[RunReport]:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM automation_runs WHERE run_id = %s", (run_id,)
            ).fetchone()
        return _row_to_report(row) if row else None

    def recent(self, limit: int = 20) -> List[RunReport]:
        limit = max(1, min(int(limit), 200))
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {_COLUMNS} FROM automation_runs ORDER BY created_at DESC LIMIT %s", (limit,)
            ).fetchall()
        return [_row_to_report(row) for row in rows]


def _row_to_report(row) -> RunReport:
    problems = row[7]
    if isinstance(problems, str):
        problems = json.loads(problems)
    return RunReport(
        run_id=row[0],
        url=row[1],
        status=row[2],
        extracted=row[3],
        landed=row[4],
        rejected=row[5],
        failed=row[6],
        problems=list(problems or []),
        error=row[8],
    )
