"""Response helpers. Every handler returns a Response built by one of these."""

import dataclasses
import json
from dataclasses import dataclass

# Error codes used in the "code" field of every error response.
CODE_BAD_JSON = "bad_json"
CODE_BAD_QUERY = "bad_query"
CODE_VALIDATION_FAILED = "validation_failed"
CODE_NOT_FOUND = "not_found"
CODE_CONFLICT = "conflict"


@dataclass
class Response:
    status: int
    body: str


def _encode(value):
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    raise TypeError(f"cannot encode {type(value).__name__}")


def write_raw(status, payload):
    return Response(status, json.dumps(payload, default=_encode))


def write_json(status, data):
    """All success responses wrap their payload in {"data": ...}."""
    return write_raw(status, {"data": data})


def write_list(data, page):
    """List responses add a "page" object next to "data"."""
    return write_raw(200, {"data": data, "page": page})


def write_error(status, code, message):
    """All error responses look like {"error": {"code": ..., "message": ...}}."""
    return write_raw(status, {"error": {"code": code, "message": message}})


def write_not_found(kind, id):
    """Writes a 404 such as "user usr_000009 not found"."""
    return write_error(404, CODE_NOT_FOUND, f"{kind} {id} not found")
