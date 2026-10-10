"""Building filters.

Each helper returns plain data (dicts) that the API understands, so filters can also be
stored or sent as JSON.
"""
from __future__ import annotations

from typing import Any, Dict, List

Filter = Dict[str, Any]


def _cmp(field: str, op: str, value: Any) -> Filter:
    return {"field": field, "op": op, "value": value}


def eq(field: str, value: Any) -> Filter: return _cmp(field, "eq", value)
def ne(field: str, value: Any) -> Filter: return _cmp(field, "ne", value)
def lt(field: str, value: Any) -> Filter: return _cmp(field, "lt", value)
def lte(field: str, value: Any) -> Filter: return _cmp(field, "lte", value)
def gt(field: str, value: Any) -> Filter: return _cmp(field, "gt", value)
def gte(field: str, value: Any) -> Filter: return _cmp(field, "gte", value)
def is_in(field: str, values: List[Any]) -> Filter: return _cmp(field, "in", list(values))
def not_in(field: str, values: List[Any]) -> Filter: return _cmp(field, "nin", list(values))
def contains(field: str, value: Any) -> Filter: return _cmp(field, "contains", value)
def starts_with(field: str, value: str) -> Filter: return _cmp(field, "startsWith", value)
def exists(field: str, present: bool = True) -> Filter: return _cmp(field, "exists", present)


def and_(*filters: Filter) -> Filter: return {"and": list(filters)}
def or_(*filters: Filter) -> Filter: return {"or": list(filters)}
def not_(filter: Filter) -> Filter: return {"not": filter}
