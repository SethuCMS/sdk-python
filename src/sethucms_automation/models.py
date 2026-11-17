"""Plain data objects shared by every step of the pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

Record = Dict[str, Any]


@dataclass(frozen=True)
class FieldSpec:
    """Describes one field the workflow must produce, and how it is checked."""

    name: str
    #: One of "string", "number", "integer", "boolean".
    kind: str = "string"
    required: bool = True
    #: For numbers: the smallest and largest allowed value.
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    #: For strings: a regular expression the whole value must match.
    pattern: Optional[str] = None
    #: For strings: when True the value must appear in the page text.
    #: This catches an AI step that invents a value that is not on the page.
    must_appear_in_source: bool = True


@dataclass(frozen=True)
class FetchedPage:
    """What a page source returns: the address it ended on, the HTML, and the readable text."""

    url: str
    html: str
    text: str


@dataclass
class RecordOutcome:
    """The result for one extracted record."""

    #: "landed", "rejected" or "failed"
    status: str
    problems: List[str] = field(default_factory=list)
    #: The id SethuCMS gave the new record. Only set when the record landed.
    record_id: Optional[str] = None


@dataclass
class RunReport:
    """A summary of one run. It holds counts and problem messages, never record values."""

    run_id: str
    url: str
    #: "running", "succeeded", "partial" or "failed"
    status: str = "running"
    extracted: int = 0
    landed: int = 0
    rejected: int = 0
    failed: int = 0
    problems: List[str] = field(default_factory=list)
    error: Optional[str] = None
