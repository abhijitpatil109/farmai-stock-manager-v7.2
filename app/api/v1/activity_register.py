"""
FarmAI Activity Register - Phase 2A API router.

Stock Manager remains untouched. No endpoint in this file deducts inventory.
"""

from __future__ import annotations

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ...core.responses import error_response, success_response
from ...core.security import require_api_key
from ...schemas.activity_register import (
    ActivityCreate, ActivityStatusCommand, CropCycleCreate, ExecutionCreate,
    FarmCreate, ObservationCreate, PlotCreate,
)
from ...services.activity_history import activity_history_detail, crop_history
from ...services.activity_register import (
    ActivityRegisterConflict, ActivityRegisterNotFound, ActivityRegisterValidation,
    add_execution, change_activity_status, create_activity, create_crop_cycle,
    create_farm, create_observation, create_plot, crop_timeline, get_activity,
    get_crop_cycle, get_reference_data, list_activities, list_crop_cycles,
    list_farms, list_plots,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["Activity Register"],
    dependencies=[Depends(require_api_key)],
)


def _error(status_code, code, message):
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(error_response(code=code,message=message)),
    )


def _domain_error(exc):
    if isinstance(exc, ActivityRegisterNotFound):
        return _error(404,"ACTIVITY_REGISTER_NOT_FOUND",str(exc))
    if isinstance(exc, ActivityRegisterConflict):
        return _error(409,"ACTIVITY_REGISTER_CONFLICT",str(exc))
    if isinstance(exc, ActivityRegisterValidation):
        return _error(422,"ACTIVITY_REGISTER_VALIDATION",str(exc))
    raise exc


from ...schemas.activity_stock_integration import StockReserveRequest, StockReleaseRequest, StockSyncRequest, StockReverseRequest
from ...services.activity_stock_integration import stock_preview, reserve_activity, release_activity, sync_execution, reverse_execution_stock

@router.get("/activity-register/reference-data", operation_id="getActivityRegisterReferenceData")
def reference_data():
    return success_response(get_reference_data())


# Existing agricultural-context endpoints
@router.post("/farms", operation_id="createFarm")
def post_farm(req: FarmCreate):
    try: return success_response(create_farm(req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)

@router.get("/farms", operation_id="listFarms")
def get_farms(active_only: bool=True):
    return success_response(list_farms(active_only))

@router.post("/plots", operation_id="createPlot")
def post_plot(req: PlotCreate):
    try: return success_response(create_plot(req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)

@router.get("/plots", operation_id="listPlots")
def get_plots(farm_id: UUID, active_only: bool=True):
    return success_response(list_plots(farm_id,active_only))

@router.post("/crop-cycles", operation_id="createCropCycle")
def post_cycle(req: CropCycleCreate):
    try: return success_response(create_crop_cycle(req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)

@router.get("/crop-cycles", operation_id="listCropCycles")
def get_cycles(
    farm_id: UUID|None=None, plot_id: UUID|None=None,
    status: Literal["PLANNED","ACTIVE","HARVESTED","CANCELLED","ARCHIVED"]|None=None
):
    return success_response(list_crop_cycles(farm_id,plot_id,status))

@router.get("/crop-cycles/{crop_cycle_id}", operation_id="getCropCycle")
def get_cycle(crop_cycle_id: UUID):
    try: return success_response(get_crop_cycle(crop_cycle_id))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)


# Core Activity Recording
@router.post(
    "/activities",
    operation_id="createActivity",
    summary="Create Activity (क्रियाकलाप तयार करा)",
)
def post_activity(req: ActivityCreate):
    try: return success_response(create_activity(req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)


@router.get(
    "/activities",
    operation_id="listActivities",
    summary="List Activities (क्रियाकलापांची यादी)",
)
def get_activities(
    crop_cycle_id: UUID|None=None,
    status: str|None=None,
    activity_type_code: str|None=None,
    date_from: date|None=None,
    date_to: date|None=None,
):
    return success_response(
        list_activities(crop_cycle_id,status,activity_type_code,date_from,date_to)
    )


@router.get(
    "/activities/{activity_id}",
    operation_id="getActivity",
    summary="Get Activity (क्रियाकलाप पहा)",
)
def get_activity_api(activity_id: UUID):
    try: return success_response(get_activity(activity_id))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)


@router.post(
    "/activities/{activity_id}/executions",
    operation_id="recordActivityExecution",
    summary="Record Activity Execution (क्रियाकलाप अंमलबजावणी नोंदवा)",
)
def post_execution(activity_id: UUID, req: ExecutionCreate):
    try: return success_response(add_execution(activity_id,req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)


@router.post(
    "/activities/{activity_id}/skip",
    operation_id="skipActivity",
    summary="Skip Activity (क्रियाकलाप वगळा)",
)
def skip_activity(activity_id: UUID, req: ActivityStatusCommand):
    try: return success_response(change_activity_status(activity_id,"SKIPPED",req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)


@router.post(
    "/activities/{activity_id}/cancel",
    operation_id="cancelActivity",
    summary="Cancel Activity (क्रियाकलाप रद्द करा)",
)
def cancel_activity(activity_id: UUID, req: ActivityStatusCommand):
    try: return success_response(change_activity_status(activity_id,"CANCELLED",req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)


@router.post(
    "/crop-cycles/{crop_cycle_id}/observations",
    operation_id="recordCropObservation",
    summary="Record Crop Observation (पीक निरीक्षण नोंदवा)",
)
def post_observation(crop_cycle_id: UUID, req: ObservationCreate):
    try: return success_response(create_observation(crop_cycle_id,req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)


@router.get(
    "/crop-cycles/{crop_cycle_id}/timeline",
    operation_id="getCropCycleTimeline",
    summary="View Crop Timeline (पीक कालरेषा पहा)",
)
def timeline(crop_cycle_id: UUID, date_from: date|None=None, date_to: date|None=None):
    try: return success_response(crop_timeline(crop_cycle_id,date_from,date_to))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)


@router.get(
    "/crop-cycles/{crop_cycle_id}/history",
    operation_id="getCropCycleAuthoritativeHistory",
    summary="View Authoritative Crop History (अधिकृत पीक इतिहास पहा)",
)
def authoritative_crop_history(crop_cycle_id: UUID):
    try: return success_response(crop_history(crop_cycle_id))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)


@router.get(
    "/activities/{activity_id}/history",
    operation_id="getActivityAuthoritativeHistory",
    summary="View Authoritative Activity History (अधिकृत क्रियाकलाप इतिहास पहा)",
)
def authoritative_activity_history(activity_id: UUID):
    try: return success_response(activity_history_detail(activity_id))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)

# ---------------------------------------------------------------------------
# Phase 3 Activity Planner Operational MVP
# ---------------------------------------------------------------------------
from ...schemas.activity_planner import ActivityPlanUpdate, ScheduleCommand, StartCommand
from ...services.activity_planner import planner_board, update_plan, schedule_activity, start_activity, plan_vs_actual

@router.get("/activity-planner/board", operation_id="getActivityPlannerBoard",
            summary="Activity Planner Board (क्रियाकलाप नियोजक)")
def activity_planner_board(farm_id: UUID|None=None, crop_cycle_id: UUID|None=None,
                           date_from: date|None=None, date_to: date|None=None):
    return success_response(planner_board(farm_id,crop_cycle_id,date_from,date_to))

@router.put("/activities/{activity_id}/plan", operation_id="updateActivityPlan",
            summary="Update Activity Plan (क्रियाकलाप योजना बदला)")
def update_activity_plan_api(activity_id: UUID, req: ActivityPlanUpdate):
    try: return success_response(update_plan(activity_id,req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)

@router.post("/activities/{activity_id}/schedule", operation_id="scheduleActivity",
             summary="Schedule / Reschedule Activity (क्रियाकलाप वेळापत्रक)")
def schedule_activity_api(activity_id: UUID, req: ScheduleCommand):
    try: return success_response(schedule_activity(activity_id,req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)

@router.post("/activities/{activity_id}/start", operation_id="startActivity",
             summary="Start Activity (क्रियाकलाप सुरू करा)")
def start_activity_api(activity_id: UUID, req: StartCommand):
    try: return success_response(start_activity(activity_id,req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)

@router.get("/activities/{activity_id}/plan-vs-actual", operation_id="getActivityPlanVsActual",
            summary="Plan vs Actual (नियोजित विरुद्ध प्रत्यक्ष)")
def plan_vs_actual_api(activity_id: UUID):
    try: return success_response(plan_vs_actual(activity_id))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)


@router.get("/activities/{activity_id}/stock-preview", operation_id="previewActivityStock")
def phase4_stock_preview(activity_id, location_code: str = "MAIN"):
    return success_response(stock_preview(activity_id, location_code), meta={"source":"activity-register+stock-manager"})
@router.post("/activities/{activity_id}/stock-reservations", operation_id="reserveActivityStock")
def phase4_reserve(activity_id, req: StockReserveRequest):
    return success_response(reserve_activity(activity_id, req), meta={"source":"activity-register+stock-manager"})
@router.post("/activities/{activity_id}/stock-reservations/release", operation_id="releaseActivityStock")
def phase4_release(activity_id, req: StockReleaseRequest):
    return success_response(release_activity(activity_id, req), meta={"source":"activity-register+stock-manager"})
@router.post("/activity-executions/{execution_id}/stock-sync", operation_id="syncExecutionStock")
def phase4_sync(execution_id, req: StockSyncRequest):
    return success_response(sync_execution(execution_id, req), meta={"source":"activity-register+stock-manager"})
@router.post("/activity-executions/{execution_id}/stock-reversal", operation_id="reverseExecutionStock")
def phase4_reverse(execution_id, req: StockReverseRequest):
    return success_response(reverse_execution_stock(execution_id, req), meta={"source":"activity-register+stock-manager"})

# ---------------------------------------------------------------------------
# Phase 5 Farmer Experience
# ---------------------------------------------------------------------------
from ...services.activity_farmer_experience import farmer_dashboard, crop_activity_timeline

@router.get("/activity-register/dashboard", operation_id="getActivityRegisterFarmerDashboard", summary="Farm Activity Dashboard (शेत क्रियाकलाप डॅशबोर्ड)")
def phase5_farmer_dashboard(farm_id: UUID|None=None, crop_cycle_id: UUID|None=None, date_from: date|None=None, date_to: date|None=None):
    try: return success_response(farmer_dashboard(farm_id,crop_cycle_id,date_from,date_to))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)

@router.get("/crop-cycles/{crop_cycle_id}/activity-timeline", operation_id="getFarmerCropActivityTimeline", summary="Crop Activity Timeline (पीक क्रियाकलाप कालरेषा)")
def phase5_crop_timeline(crop_cycle_id: UUID, limit: int=Query(default=200,ge=1,le=500)):
    try: return success_response(crop_activity_timeline(crop_cycle_id,limit))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e: return _domain_error(e)

# ---------------------------------------------------------------------------
# Phase 5.1 Farmer Operational Entry + Quantity Resolution
# ---------------------------------------------------------------------------
from ...schemas.activity_farmer_entry import FarmerActivityEntry
from ...services.activity_farmer_entry import preview_farmer_activity, complete_farmer_activity

@router.post("/activity-register/farmer-entry/preview",operation_id="previewFarmerActivity",
             summary="Preview Farmer Activity (शेतकरी क्रियाकलाप पूर्वावलोकन)")
def phase51_preview(req: FarmerActivityEntry):
    try:return success_response(preview_farmer_activity(req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _domain_error(e)

@router.post("/activity-register/farmer-entry/complete",operation_id="completeFarmerActivity",
             summary="Complete Farmer Activity (शेतकरी क्रियाकलाप पूर्ण नोंद)")
def phase51_complete(req: FarmerActivityEntry):
    try:return success_response(complete_farmer_activity(req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _domain_error(e)
