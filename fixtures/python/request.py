"""Request type and helpers for decoding bodies, validation, and pagination."""

import dataclasses
import json
from dataclasses import dataclass, field

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


@dataclass
class Request:
    method: str
    path: str
    query: dict = field(default_factory=dict)
    body: str = ""
    path_params: dict = field(default_factory=dict)


class ValidationError(Exception):
    """Raised by request validate() methods. Handlers turn it into a 422 with
    code validation_failed and message "field: reason"."""

    def __init__(self, field, reason):
        super().__init__(f"{field}: {reason}")
        self.field = field
        self.reason = reason


class BadJSON(Exception):
    """Raised by decode_body. Handlers turn it into a 400 with code bad_json."""


class BadQuery(Exception):
    """Raised by parse_page. Handlers turn it into a 400 with code bad_query."""


def decode_body(req, cls):
    """Decodes a JSON object body into the dataclass cls, rejecting unknown
    fields and missing required fields."""
    try:
        raw = json.loads(req.body)
    except json.JSONDecodeError as e:
        raise BadJSON(str(e)) from None
    if not isinstance(raw, dict):
        raise BadJSON("body must be a JSON object")
    known = {f.name for f in dataclasses.fields(cls)}
    unknown = set(raw) - known
    if unknown:
        raise BadJSON(f"unknown fields: {sorted(unknown)}")
    try:
        return cls(**raw)
    except TypeError as e:
        raise BadJSON(str(e)) from None


@dataclass
class PageParams:
    limit: int = DEFAULT_LIMIT
    offset: int = 0


@dataclass
class PageInfo:
    limit: int
    offset: int
    total: int


def _int_param(query, name):
    value = query.get(name, "")
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return False


def parse_page(req):
    """Reads ?limit= and ?offset=. Raises BadQuery for invalid values."""
    p = PageParams()
    limit = _int_param(req.query, "limit")
    if limit is not None:
        if limit is False or not 1 <= limit <= MAX_LIMIT:
            raise BadQuery(f"limit must be an integer from 1 to {MAX_LIMIT}")
        p.limit = limit
    offset = _int_param(req.query, "offset")
    if offset is not None:
        if offset is False or offset < 0:
            raise BadQuery("offset must be a non-negative integer")
        p.offset = offset
    return p


def paginate(items, p):
    """Slices items according to p and returns (page_items, PageInfo)."""
    return items[p.offset:p.offset + p.limit], PageInfo(p.limit, p.offset, len(items))
