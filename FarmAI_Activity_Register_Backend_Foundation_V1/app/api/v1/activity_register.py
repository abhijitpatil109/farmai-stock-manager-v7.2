"""
FarmAI Activity Register V1 - Domain Foundation API.

Phase 1 scope:
- Reference catalog
- Farm (शेत)
- Plot (प्लॉट)
- Crop Cycle (पीक चक्र)

Activity recording endpoints are intentionally deferred to the next phase.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ...core.responses import error_response, success_response
from ...core.security import require_api_key
from ...schemas.activity_register import CropCycleCreate, FarmCreate, PlotCreate
from ...services.activity_register import (
    ActivityRegisterConflict,
    ActivityRegisterNotFound,
    ActivityRegisterValidation,
    create_crop_cycle,
    create_farm,
    create_plot,
    get_crop_cycle,
    get_reference_data,
    list_crop_cycles,
    list_farms,
    list_plots,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["Activity Register"],
    dependencies=[Depends(require_api_key)],
)


def _error(status_code: int, code: str, message: str):
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(error_response(code=code, message=message)),
    )


def _handle_domain_error(exc: Exception):
    if isinstance(exc, ActivityRegisterNotFound):
        return _error(404, "ACTIVITY_REGISTER_NOT_FOUND", str(exc))
    if isinstance(exc, ActivityRegisterConflict):
        return _error(409, "ACTIVITY_REGISTER_CONFLICT", str(exc))
    if isinstance(exc, ActivityRegisterValidation):
        return _error(422, "ACTIVITY_REGISTER_VALIDATION", str(exc))
    raise exc


@router.get(
    "/activity-register/reference-data",
    operation_id="getActivityRegisterReferenceData",
    summary="Get Activity Register reference data (अॅक्टिव्हिटी रजिस्टर संदर्भ डेटा)",
)
def reference_data():
    return success_response(get_reference_data())


@router.post(
    "/farms",
    operation_id="createFarm",
    summary="Create Farm (शेत तयार करा)",
)
def post_farm(req: FarmCreate):
    try:
        return success_response(create_farm(req))
    except (ActivityRegisterNotFound, ActivityRegisterConflict, ActivityRegisterValidation) as exc:
        return _handle_domain_error(exc)


@router.get(
    "/farms",
    operation_id="listFarms",
    summary="List Farms (शेतांची यादी)",
)
def get_farms(
    active_only: bool = Query(default=True),
):
    return success_response(list_farms(active_only=active_only))


@router.post(
    "/plots",
    operation_id="createPlot",
    summary="Create Plot (प्लॉट तयार करा)",
)
def post_plot(req: PlotCreate):
    try:
        return success_response(create_plot(req))
    except (ActivityRegisterNotFound, ActivityRegisterConflict, ActivityRegisterValidation) as exc:
        return _handle_domain_error(exc)


@router.get(
    "/plots",
    operation_id="listPlots",
    summary="List Plots (प्लॉटची यादी)",
)
def get_plots(
    farm_id: UUID = Query(...),
    active_only: bool = Query(default=True),
):
    return success_response(list_plots(farm_id=farm_id, active_only=active_only))


@router.post(
    "/crop-cycles",
    operation_id="createCropCycle",
    summary="Create Crop Cycle (पीक चक्र तयार करा)",
)
def post_crop_cycle(req: CropCycleCreate):
    try:
        return success_response(create_crop_cycle(req))
    except (ActivityRegisterNotFound, ActivityRegisterConflict, ActivityRegisterValidation) as exc:
        return _handle_domain_error(exc)


@router.get(
    "/crop-cycles",
    operation_id="listCropCycles",
    summary="List Crop Cycles (पीक चक्रांची यादी)",
)
def get_crop_cycles(
    farm_id: UUID | None = Query(default=None),
    plot_id: UUID | None = Query(default=None),
    status: Literal["PLANNED", "ACTIVE", "HARVESTED", "CANCELLED", "ARCHIVED"] | None = Query(default=None),
):
    return success_response(
        list_crop_cycles(farm_id=farm_id, plot_id=plot_id, status=status)
    )


@router.get(
    "/crop-cycles/{crop_cycle_id}",
    operation_id="getCropCycle",
    summary="Get Crop Cycle (पीक चक्र पहा)",
)
def get_crop_cycle_by_id(crop_cycle_id: UUID):
    try:
        return success_response(get_crop_cycle(crop_cycle_id))
    except (ActivityRegisterNotFound, ActivityRegisterConflict, ActivityRegisterValidation) as exc:
        return _handle_domain_error(exc)
