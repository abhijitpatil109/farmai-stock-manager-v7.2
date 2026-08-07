"""
FarmAI Core API security utilities.

This module provides the shared authentication dependency for all /api/v1
Stock Agent endpoints.

Authentication model (V1):
    Header: X-API-Key
    Secret source: FARMAI_API_KEY environment variable

The database and API remain the source of truth. No credential value is ever
hard-coded in application code.
"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Header, HTTPException, status

from ..config import settings


API_KEY_HEADER = "X-API-Key"


def _is_valid_api_key(candidate: str | None) -> bool:
    """
    Compare the supplied API key with the configured FarmAI secret.

    hmac.compare_digest is used to avoid ordinary string-comparison timing
    differences.
    """
    if not candidate:
        return False

    configured_key = settings().farmai_api_key

    if not configured_key:
        return False

    return hmac.compare_digest(candidate, configured_key)


def require_api_key(
    x_api_key: Annotated[str | None, Header(alias=API_KEY_HEADER)] = None,
) -> str:
    """
    FastAPI dependency that protects FarmAI Core API V1 routes.

    Returns the authenticated API key value so the dependency can later be
    extended with caller identity, roles, permissions, or audit metadata
    without changing route signatures.

    Raises:
        HTTPException(401): when the key is missing or invalid.
    """
    if not _is_valid_api_key(x_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Invalid or missing API key.",
            },
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return x_api_key