"""A small FastAPI service to start runs and read their reports.

Run it with:  uvicorn "your_module:app"  where app = create_app(...)
"""
from __future__ import annotations

import hmac
from dataclasses import asdict
from typing import Collection, List, Optional
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from .store import RunStore
from .workflow import Workflow


class RunRequest(BaseModel):
    url: str


def create_app(
    workflow: Workflow,
    store: RunStore,
    *,
    api_token: str,
    allowed_hosts: Collection[str],
) -> FastAPI:
    """Build the app.

    `allowed_hosts` is the list of websites a caller may ask us to scrape. Without it, anyone with
    the token could make the server open any address, including internal ones.
    """
    if len(api_token) < 16:
        raise ValueError("api_token must be at least 16 characters.")
    if not allowed_hosts:
        raise ValueError("allowed_hosts must name at least one website.")
    allowed = {host.lower() for host in allowed_hosts}
    app = FastAPI(title="SethuCMS automation", docs_url=None, redoc_url=None)

    def require_token(authorization: Optional[str] = Header(default=None)) -> None:
        """Check the Bearer token in constant time, so timing cannot reveal it."""
        expected = f"Bearer {api_token}"
        if authorization is None or not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="A valid token is required.")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/runs", dependencies=[Depends(require_token)])
    def start_run(request: RunRequest) -> dict:
        _check_url(request.url, allowed)
        # The run is done when this returns. Put a job queue in front for long pages.
        return asdict(workflow.run(request.url))

    @app.get("/runs", dependencies=[Depends(require_token)])
    def list_runs(limit: int = 20) -> List[dict]:
        return [asdict(report) for report in store.recent(limit)]

    @app.get("/runs/{run_id}", dependencies=[Depends(require_token)])
    def get_run(run_id: str) -> dict:
        report = store.get(run_id)
        if report is None:
            raise HTTPException(status_code=404, detail="No run with that id.")
        return asdict(report)

    return app


def _check_url(url: str, allowed: set) -> None:
    """Only https addresses on the allow-list are accepted."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise HTTPException(status_code=400, detail="The address must start with https://")
    if parts.username or parts.password:
        raise HTTPException(status_code=400, detail="The address must not contain a password.")
    if parts.hostname.lower() not in allowed:
        raise HTTPException(status_code=403, detail="That website is not on the allow-list.")
