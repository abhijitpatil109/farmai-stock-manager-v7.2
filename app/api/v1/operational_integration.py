from __future__ import annotations

import logging
import traceback
from datetime import date
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ...core.responses import success_response, error_response
from ...core.security import require_api_key
from ...schemas.activity_farmer_entry import FarmerActivityEntry
from ...schemas.operational_integration import OperationalActivityCompleteRequest
from ...schemas.weather_intelligence import SprayWindowConsultRequest
from ...services.operational_integration import (
    CONTRACT_VERSION,
    operational_health,
    capabilities,
    operational_stock,
    operational_activity_history,
    build_operational_context,
    preview_operational_activity,
    complete_operational_activity,
)
from ...services.operational_decision_context import build_crop_decision_context
from ...services.external_weather import spray_window_consultation
from ...services.activity_register import (
    ActivityRegisterNotFound,
    ActivityRegisterConflict,
    ActivityRegisterValidation,
)

logger = logging.getLogger("farmai.operational")

router = APIRouter(
    prefix="/api/v1/operations",
    tags=["FarmAI ChatGPT Operational Integration"],
    dependencies=[Depends(require_api_key)],
)


def _err(exc):
    status = (
        404 if isinstance(exc, ActivityRegisterNotFound)
        else 409 if isinstance(exc, ActivityRegisterConflict)
        else 422
    )
    return JSONResponse(
        status_code=status,
        content=jsonable_encoder(
            error_response(
                code="FARMAI_OPERATIONAL_INTEGRATION",
                message=str(exc),
            )
        ),
    )


def _unexpected_error(exc: Exception, *, operation: str):
    incident_id = f"OI-{uuid4().hex[:12].upper()}"
    stage = getattr(exc, "stage", None)
    original = getattr(exc, "original_exception", None)

    logger.error(
        "FarmAI unexpected operational failure "
        "incident_id=%s operation=%s stage=%s exception_type=%s "
        "original_exception_type=%s exception=%s\n%s",
        incident_id,
        operation,
        stage or "unknown",
        type(exc).__name__,
        type(original).__name__ if original is not None else None,
        str(exc),
        traceback.format_exc(),
    )

    message = (
        "Unexpected FarmAI operational failure. "
        f"Incident ID: {incident_id}. "
        "Check Vercel Function logs for the matching incident ID."
    )
    if stage:
        message += f" Failure stage: {stage}."

    return JSONResponse(
        status_code=500,
        content=jsonable_encoder(
            error_response(
                code="FARMAI_OPERATIONAL_UNEXPECTED",
                message=message,
            )
        ),
    )


@router.get("/health", operation_id="getOperationalHealth")
def health():
    return success_response(operational_health())


@router.get("/capabilities", operation_id="getOperationalCapabilities")
def get_capabilities():
    return success_response(capabilities())


@router.get(
    "/stock",
    operation_id="getOperationalStock",
    summary="Get complete authoritative FarmAI stock",
    description=(
        "Authoritative GPT-facing stock read. Returns EVERY active FarmAI product, "
        "including zero-stock products and products with no stock transaction yet. "
        "For complete/current stock questions use this operation, not getCurrentInventory."
    ),
)
def stock():
    try:
        return success_response(operational_stock())
    except (
        ActivityRegisterNotFound,
        ActivityRegisterConflict,
        ActivityRegisterValidation,
    ) as exc:
        return _err(exc)
    except Exception as exc:
        return _unexpected_error(exc, operation="getOperationalStock")


@router.get(
    "/activity-history",
    operation_id="getOperationalActivityHistory",
    summary="Get authoritative FarmAI activity history",
    description=(
        "Authoritative GPT-facing Activity History. Reads Activity + Execution + "
        "purpose + products + linked Stock transactions. Use this for latest/history "
        "questions after crop-use stock deductions."
    ),
)
def activity_history(
    crop_cycle_id: UUID | None = None,
    crop_name: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    execution_status: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
):
    try:
        return success_response(
            operational_activity_history(
                crop_cycle_id=crop_cycle_id,
                crop_name=crop_name,
                date_from=date_from,
                date_to=date_to,
                execution_status=execution_status,
                limit=limit,
            )
        )
    except (
        ActivityRegisterNotFound,
        ActivityRegisterConflict,
        ActivityRegisterValidation,
    ) as exc:
        return _err(exc)
    except Exception as exc:
        return _unexpected_error(exc, operation="getOperationalActivityHistory")


@router.get("/context", operation_id="getOperationalContext")
def context(
    farm_id: UUID | None = None,
    crop_cycle_id: UUID | None = None,
    horizon_days: int = Query(default=7, ge=1, le=30),
    history_days: int = Query(default=30, ge=1, le=180),
    include_intelligence: bool = True,
):
    try:
        return success_response(
            build_operational_context(
                farm_id=farm_id,
                crop_cycle_id=crop_cycle_id,
                horizon_days=horizon_days,
                history_days=history_days,
                include_intelligence=include_intelligence,
            )
        )
    except (
        ActivityRegisterNotFound,
        ActivityRegisterConflict,
        ActivityRegisterValidation,
    ) as exc:
        return _err(exc)
    except Exception as exc:
        return _unexpected_error(exc, operation="getOperationalContext")


@router.get(
    "/crop-decision-context/{crop_cycle_id}",
    operation_id="getOperationalCropDecisionContext",
    summary="Decision-grade crop context for FarmAI GPT",
)
def crop_decision_context(
    crop_cycle_id: UUID,
    horizon_days: int = Query(default=7, ge=1, le=14),
    history_days: int = Query(default=60, ge=14, le=180),
):
    try:
        return success_response(
            build_crop_decision_context(
                crop_cycle_id=crop_cycle_id,
                horizon_days=horizon_days,
                history_days=history_days,
            )
        )
    except (
        ActivityRegisterNotFound,
        ActivityRegisterConflict,
        ActivityRegisterValidation,
    ) as exc:
        return _err(exc)
    except Exception as exc:
        return _unexpected_error(
            exc, operation="getOperationalCropDecisionContext"
        )


@router.post(
    "/spray-window",
    operation_id="getBestOperationalSprayWindow",
    summary="Resolve stored farm geotag and find the best spray window",
    description=(
        "MANDATORY for today/tomorrow spray-window or 'can we spray?' requests. "
        "Resolves stored farm/crop/plot geotag, refreshes forecasts, and ranks "
        "windows. Do not ask for coordinates first; ask only if the response "
        "reports missing or ambiguous stored location. Label limits override defaults."
    ),
)
def spray_window(req: SprayWindowConsultRequest):
    try:
        return success_response(spray_window_consultation(req))
    except (
        ActivityRegisterNotFound,
        ActivityRegisterConflict,
        ActivityRegisterValidation,
    ) as exc:
        return _err(exc)
    except Exception as exc:
        return _unexpected_error(exc, operation="getBestOperationalSprayWindow")


@router.post(
    "/activity/preview",
    operation_id="previewOperationalActivity",
    summary="Preview crop Activity + Stock impact",
)
def preview_activity(req: FarmerActivityEntry):
    try:
        return success_response(preview_operational_activity(req))
    except (
        ActivityRegisterNotFound,
        ActivityRegisterConflict,
        ActivityRegisterValidation,
    ) as exc:
        return _err(exc)
    except Exception as exc:
        return _unexpected_error(exc, operation="previewOperationalActivity")


@router.post(
    "/activity/complete",
    operation_id="completeOperationalActivity",
    summary="Record completed crop Activity and synchronize Stock",
    description=(
        "Use for completed crop applications with stock use. Records Activity, "
        "Execution, purposes and actual quantities, then synchronizes Stock "
        "idempotently. Report success only when write_confirmation verifies "
        "history and stock linkage. Never use generic stock usage for crop work."
    ),
)
def complete_activity(req: OperationalActivityCompleteRequest):
    try:
        return success_response(complete_operational_activity(req))
    except (
        ActivityRegisterNotFound,
        ActivityRegisterConflict,
        ActivityRegisterValidation,
    ) as exc:
        return _err(exc)
    except Exception as exc:
        return _unexpected_error(exc, operation="completeOperationalActivity")
