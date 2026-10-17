"""Shared validation helpers and clock."""
import re
from datetime import datetime, timezone

from .errors import validation_error

ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_id(value) -> bool:
    return isinstance(value, str) and bool(ID_RE.match(value))


def is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def require_object(body, field="body") -> dict:
    if not isinstance(body, dict):
        raise validation_error([field])
    return body


def check_ids(body: dict, *fields: str, optional: tuple = ()) -> None:
    bad = [f for f in fields if not is_id(body.get(f))]
    bad += [f for f in optional if body.get(f) is not None and not is_id(body.get(f))]
    if bad:
        raise validation_error(bad)
