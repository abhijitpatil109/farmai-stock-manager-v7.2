
from datetime import date
from uuid import UUID

from fastapi import APIRouter,Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ...core.responses import error_response,success_response
from ...core.security import require_api_key
from ...schemas.activity_proactive_planner import (
    RecommendationToActivityRequest,PriorityRequest,HoldRequest,
    ReleaseHoldRequest,PlannerRescheduleRequest,DismissRequest,
)
from ...services.activity_proactive_planner import (
    recommendation_to_activity,set_priority,hold_activity,release_hold,
    reschedule,dismiss,proactive_board,
)
from ...services.activity_register import (
    ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation,
)

router=APIRouter(
    prefix="/api/v1",
    tags=["Proactive Farm Planner"],
    dependencies=[Depends(require_api_key)],
)


def _err(e):
    status=(
      404 if isinstance(e,ActivityRegisterNotFound)
      else 409 if isinstance(e,ActivityRegisterConflict)
      else 422
    )
    return JSONResponse(
      status_code=status,
      content=jsonable_encoder(
        error_response(code="PROACTIVE_PLANNER",message=str(e))
      )
    )


@router.post(
  "/proactive-planner/recommendations/{recommendation_id}/propose-activity",
  operation_id="proposeActivityFromRecommendation",
  summary="Recommendation → Proposed Activity (शिफारस → प्रस्तावित क्रियाकलाप)"
)
def propose(recommendation_id:UUID,req:RecommendationToActivityRequest):
    if recommendation_id!=req.recommendation_id:
        return JSONResponse(
          status_code=422,
          content=jsonable_encoder(
            error_response(
              code="PROACTIVE_PLANNER",
              message="recommendation_id mismatch."
            )
          )
        )
    try:
        return success_response(recommendation_to_activity(req))
    except (
      ActivityRegisterNotFound,
      ActivityRegisterConflict,
      ActivityRegisterValidation,
    ) as e:
        return _err(e)


@router.get(
  "/proactive-planner/board",
  operation_id="getProactivePlannerBoard",
  summary="Proactive Farm Operations Board (सक्रिय शेत कार्य फलक)"
)
def board(
  farm_id:UUID|None=None,
  crop_cycle_id:UUID|None=None,
  date_from:date|None=None,
  date_to:date|None=None,
):
    try:
        return success_response(
          proactive_board(farm_id,crop_cycle_id,date_from,date_to)
        )
    except (
      ActivityRegisterNotFound,
      ActivityRegisterConflict,
      ActivityRegisterValidation,
    ) as e:
        return _err(e)


@router.post(
  "/proactive-planner/activities/{activity_id}/priority",
  operation_id="setPlannerPriority"
)
def priority(activity_id:UUID,req:PriorityRequest):
    try:return success_response(set_priority(activity_id,req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)


@router.post(
  "/proactive-planner/activities/{activity_id}/hold",
  operation_id="holdPlannerActivity"
)
def hold(activity_id:UUID,req:HoldRequest):
    try:return success_response(hold_activity(activity_id,req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)


@router.post(
  "/proactive-planner/activities/{activity_id}/release",
  operation_id="releasePlannerHold"
)
def release(activity_id:UUID,req:ReleaseHoldRequest):
    try:return success_response(release_hold(activity_id,req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)


@router.post(
  "/proactive-planner/activities/{activity_id}/reschedule",
  operation_id="reschedulePlannerActivity"
)
def reschedule_api(activity_id:UUID,req:PlannerRescheduleRequest):
    try:return success_response(reschedule(activity_id,req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)


@router.post(
  "/proactive-planner/activities/{activity_id}/dismiss",
  operation_id="dismissPlannerActivity"
)
def dismiss_api(activity_id:UUID,req:DismissRequest):
    try:return success_response(dismiss(activity_id,req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)
