"""Validation: only records that pass every check are allowed to reach SethuCMS."""
from __future__ import annotations

import re
from typing import Any, List, Sequence, Tuple

from .models import FieldSpec, Record

_KINDS = {"string", "number", "integer", "boolean"}


def validate_record(record: Record, fields: Sequence[FieldSpec], page_text: str) -> Tuple[Record, List[str]]:
    """Check one record. Returns the cleaned record (only known fields) and a list of problems.

    An empty problem list means the record is safe to write. Problem messages name the
    field and the rule, but never include the value, so they are safe to log.
    """
    problems: List[str] = []
    cleaned: Record = {}
    known = {spec.name for spec in fields}

    for extra in sorted(set(record) - known):
        problems.append(f"{extra}: not a requested field")

    for spec in fields:
        value = record.get(spec.name)
        if value is None or value == "":
            if spec.required:
                problems.append(f"{spec.name}: required but missing")
            continue
        problem = _check_value(spec, value, page_text)
        if problem:
            problems.append(f"{spec.name}: {problem}")
        else:
            cleaned[spec.name] = value
    return cleaned, problems


def _check_value(spec: FieldSpec, value: Any, page_text: str) -> str:
    """Return a short problem description, or an empty string when the value is fine."""
    if spec.kind not in _KINDS:
        return f"unknown kind '{spec.kind}'"

    if spec.kind == "boolean":
        return "" if isinstance(value, bool) else "must be true or false"

    if spec.kind in ("number", "integer"):
        # bool is a subclass of int in Python, so exclude it explicitly.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return "must be a number"
        if spec.kind == "integer" and int(value) != value:
            return "must be a whole number"
        if spec.minimum is not None and value < spec.minimum:
            return "is below the minimum"
        if spec.maximum is not None and value > spec.maximum:
            return "is above the maximum"
        return ""

    if not isinstance(value, str):
        return "must be text"
    if spec.pattern and not re.fullmatch(spec.pattern, value):
        return "does not match the expected pattern"
    if spec.must_appear_in_source and _squash(value) not in _squash(page_text):
        return "was not found on the page"
    return ""


def _squash(text: str) -> str:
    """Lowercase and collapse spaces, so a harmless layout difference does not fail the check."""
    return " ".join(text.lower().split())
