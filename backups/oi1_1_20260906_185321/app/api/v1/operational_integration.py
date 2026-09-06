from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ...core.responses import success_response, error_response
from ...core.security import require_api_key
from ...schemas.activity_farmer_entry import FarmerActivityEntry
from ...schemas.operational_integration import OperationalActivityCompleteRequest
from ...services.operational_integration import (
    operational_health,
    capabilities,
    operational_stock,
    build_operational_context,
    preview_operational_activity,
    complete_operational_activity,
)
from ...services.activity_register import (
    ActivityRegisterNotFound,
    ActivityRegisterConflict,
    ActivityRegisterValidation,
)

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
            error_response(code="FARMAI_OPERATIONAL_INTEGRATION", message=str(exc))
        ),
    )


@router.get("/health", operation_id="getOperationalHealth")
def health():
    return success_response(operational_health())


@router.get("/capabilities", operation_id="getOperationalCapabilities")
def get_capabilities():
    return success_response(capabilities())


@router.get("/stock", operation_id="getOperationalStock")
def stock():
    return success_response(operational_stock())


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
    except (ActivityRegisterNotFound, ActivityRegisterConflict, ActivityRegisterValidation) as exc:
        return _err(exc)


@router.post("/activity/preview", operation_id="previewOperationalActivity")
def preview_activity(req: FarmerActivityEntry):
    try:
        return success_response(preview_operational_activity(req))
    except (ActivityRegisterNotFound, ActivityRegisterConflict, ActivityRegisterValidation) as exc:
        return _err(exc)


@router.post("/activity/complete", operation_id="completeOperationalActivity")
def complete_activity(req: OperationalActivityCompleteRequest):
    try:
        return success_response(complete_operational_activity(req))
    except (ActivityRegisterNotFound, ActivityRegisterConflict, ActivityRegisterValidation) as exc:
        return _err(exc)
