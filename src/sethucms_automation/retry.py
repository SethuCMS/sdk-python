"""Retry a step that can fail for reasons that go away, such as a slow page or a network blip."""
from __future__ import annotations

import random
import time
from typing import Callable, Tuple, Type, TypeVar

from .logs import log_event

T = TypeVar("T")


def with_retries(
    step: Callable[[], T],
    *,
    name: str,
    attempts: int = 3,
    base_delay: float = 1.0,
    retry_on: Tuple[Type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run `step`. If it raises one of `retry_on`, wait and try again, up to `attempts` times.

    The wait doubles each time and has some random spread so many workflows
    do not all retry at the same moment. The last error is raised unchanged.
    Only use this for steps that are safe to run twice (reading, not writing).
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    attempt = 0
    while True:
        attempt += 1
        try:
            return step()
        except retry_on as error:
            if attempt >= attempts:
                log_event("step_gave_up", step=name, attempts=attempt, error_type=type(error).__name__)
                raise
            delay = min(base_delay * 2 ** (attempt - 1), 30.0) * (0.5 + random.random() / 2)
            log_event("step_retry", step=name, attempt=attempt, wait_seconds=round(delay, 2))
            sleep(delay)
