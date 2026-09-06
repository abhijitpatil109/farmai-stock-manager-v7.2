from uuid import UUID
from fastapi import APIRouter,Depends,Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from ...core.responses import error_response,success_response
from ...core.security import require_api_key
from ...services.activity_register import ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation
from ...schemas.phase9 import SceneDiscoverRequest,RemoteRefreshRequest,AnomalyEvaluateRequest,ScoutingTaskCreate,ScoutingObservationCreate,SeasonComparisonRequest
from ...services.geospatial import get_active_geometry
from ...services.remote_sensing import discover_scenes,refresh_plot,latest,timeline
from ...services.remote_anomaly import evaluate_anomaly
from ...services.scouting import create_task,list_tasks,complete_task
from ...services.season_intelligence import cycle_summary,compare_cycles

router=APIRouter(prefix="/api/v1",tags=["Phase 9 / Remote Sensing & Scouting"],dependencies=[Depends(require_api_key)])
def _err(e):
    status=404 if isinstance(e,ActivityRegisterNotFound) else 409 if isinstance(e,ActivityRegisterConflict) else 422
    return JSONResponse(status_code=status,content=jsonable_encoder(error_response(code="FARMAI_PHASE9",message=str(e))))

@router.get("/remote-sensing/plots/{plot_id}/geometry")
def geometry(plot_id:UUID):
    try:return success_response(get_active_geometry(plot_id))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.post("/remote-sensing/scenes/discover")
def discover(req:SceneDiscoverRequest):
    try:return success_response(discover_scenes(req.plot_id,req.date_from,req.date_to,req.max_cloud_cover_pct,req.limit))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.post("/remote-sensing/plots/{plot_id}/refresh")
def refresh(plot_id:UUID,req:RemoteRefreshRequest):
    try:
        if plot_id!=req.plot_id:raise ActivityRegisterValidation("Path and request plot_id must match.")
        return success_response(refresh_plot(req.plot_id,req.date_from,req.date_to,req.max_cloud_cover_pct,req.max_scenes,req.analysis_scope))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.get("/remote-sensing/plots/{plot_id}/latest")
def latest_obs(plot_id:UUID):
    try:return success_response(latest(plot_id))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.get("/remote-sensing/plots/{plot_id}/timeline")
def get_timeline(plot_id:UUID,limit:int=Query(50,ge=1,le=250)):
    try:return success_response(timeline(plot_id,limit))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.post("/remote-sensing/anomalies/evaluate")
def anomaly(req:AnomalyEvaluateRequest):
    try:return success_response(evaluate_anomaly(req.plot_id,req.observation_id))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.post("/scouting/tasks")
def scout_create(req:ScoutingTaskCreate):
    try:return success_response(create_task(req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.get("/scouting/tasks")
def scout_list(farm_id:UUID|None=None,plot_id:UUID|None=None,status:str|None=None,limit:int=Query(100,ge=1,le=250)):
    try:return success_response(list_tasks(farm_id,plot_id,status,limit))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.post("/scouting/tasks/{task_id}/complete")
def scout_complete(task_id:UUID,req:ScoutingObservationCreate):
    try:return success_response(complete_task(task_id,req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.get("/season-intelligence/crop-cycles/{crop_cycle_id}")
def season(crop_cycle_id:UUID):
    try:return success_response(cycle_summary(crop_cycle_id))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.post("/season-intelligence/compare")
def compare(req:SeasonComparisonRequest):
    try:return success_response(compare_cycles(req.current_crop_cycle_id,req.baseline_crop_cycle_id,req.metric_code))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)
