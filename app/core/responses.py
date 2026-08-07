"""
FarmAI Core API response utilities.

Provides a single, stable response envelope for all /api/v1 endpoints.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

API_VERSION = "v1"


def _timestamp() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _request_id(request_id: str | None = None) -> str:
    """Return supplied request ID or generate a new one."""
    return request_id or str(uuid4())


def build_meta(
    request_id: str | None = None,
    *,
    api_version: str = API_VERSION,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the standard FarmAI response metadata block."""
    meta: dict[str, Any] = {
        "api_version": api_version,
        "request_id": _request_id(request_id),
        "timestamp": _timestamp(),
    }

    if extra:
        meta.update(extra)

    return meta


def success_response(
    data: Any = None,
    *,
    request_id: str | None = None,
    api_version: str = API_VERSION,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the standard FarmAI success envelope."""
    return {
        "ok": True,
        "data": data,
        "meta": build_meta(
            request_id=request_id,
            api_version=api_version,
            extra=meta,
        ),
    }


def error_response(
    code: str,
    message: str,
    *,
    request_id: str | None = None,
    api_version: str = API_VERSION,
    details: Any | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the standard FarmAI error envelope."""
    error: dict[str, Any] = {
        "code": code,
        "message": message,
    }

    if details is not None:
        error["details"] = details

    return {
        "ok": False,
        "error": error,
        "meta": build_meta(
            request_id=request_id,
            api_version=api_version,
            extra=meta,
        ),
    }
