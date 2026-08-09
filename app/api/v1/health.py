"""
FarmAI Core API - Health Endpoints

Purpose:
    • API health
    • Database connectivity
    • Version information

This module contains only health-related endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...db import connection
from ...core.responses import success_response
from ...core.security import require_api_key

router = APIRouter(
    prefix="/api/v1",
    tags=["System"],
    dependencies=[Depends(require_api_key)],
)


@router.get(
    "/health",
    operation_id="healthCheck",
    summary="Health Check",
    description="Checks API and PostgreSQL connectivity.",
)
def health_check():
    """
    Verify API and PostgreSQL connectivity.
    """

    database_status = "ok"

    try:
        with connection() as conn:
            conn.execute("SELECT 1")
    except Exception:
        database_status = "failed"

    status = "ok" if database_status == "ok" else "degraded"

    return success_response(
        {
            "service": "FarmAI Stock Manager",
            "application_version": "7.2.2",
            "api_version": "v1",
            "status": status,
            "database": database_status,
        }
    )