from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from .config import settings


api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="FarmAIApiKey",
    description="FarmAI Stock Manager API key",
    auto_error=False,
)


def _configured_api_key() -> str:
    value = getattr(settings, "api_key", None)

    if value is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "API_KEY_NOT_CONFIGURED",
                "message": "FarmAI API authentication is not configured.",
            },
        )

    value = str(value).strip()

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
    if supplied_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Invalid or missing API key.",
            },
        )

    expected_api_key = _configured_api_key()
    supplied_api_key = supplied_api_key.strip()

    if not supplied_api_key or not hmac.compare_digest(
        supplied_api_key,
        expected_api_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Invalid or missing API key.",
            },
        )

    return supplied_api_key
