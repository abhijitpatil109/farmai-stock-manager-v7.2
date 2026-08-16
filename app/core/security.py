from __future__ import annotations

import hmac
import os

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader


api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="FarmAIApiKey",
    description="FarmAI Stock Manager API key",
    auto_error=False,
)


def _configured_api_key() -> str:
    """
    Read the server-side API key directly from environment variables.

    Supports both names so this remains compatible with existing deployments:
    - FARMAI_API_KEY
    - API_KEY
    """
    value = (
        os.getenv("FARMAI_API_KEY")
        or os.getenv("API_KEY")
        or ""
    ).strip()

    if not value:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "API_KEY_NOT_CONFIGURED",
                "message": "FarmAI API authentication is not configured.",
            },
        )

    return value


def require_api_key(
    supplied_api_key: str | None = Depends(api_key_header),
) -> str:
    """
    Validate the X-API-Key header and expose a proper OpenAPI apiKey scheme.
    """
    if supplied_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Invalid or missing API key.",
            },
        )

    supplied = supplied_api_key.strip()
    expected = _configured_api_key()

    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Invalid or missing API key.",
            },
        )

    return supplied
import logging

logger = logging.getLogger("farmai.security")

def require_api_key(
    supplied_api_key: str | None = Depends(api_key_header),
) -> str:

    logger.info(
        "FarmAI auth debug: header_present=%s header_length=%s",
        supplied_api_key is not None,
        len(supplied_api_key) if supplied_api_key else 0,
    )

    if supplied_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Invalid or missing API key.",
            },
        )

    supplied = supplied_api_key.strip()
    expected = _configured_api_key()

    logger.info(
        "FarmAI auth debug: supplied_length=%s expected_length=%s",
        len(supplied),
        len(expected),
    )

    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Invalid or missing API key.",
            },
        )

    return supplied