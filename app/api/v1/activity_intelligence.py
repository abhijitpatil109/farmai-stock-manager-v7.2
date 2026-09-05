from uuid import UUID
from fastapi import APIRouter,Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from ...core.responses import error_response,success_response
from ...core.security import require_api_key
from ...schemas.activity_intelligence import IntelligenceRequest,RecommendationDecision
from ...services.activity_intelligence import build_intelligence_context,evaluate_intelligence,decide_recommendation
from ...services.activity_register import ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation

router=APIRouter(prefix="/api/v1",tags=["FarmAI Intelligence"],dependencies=[Depends(require_api_key)])

def _err(e):
    status=404 if isinstance(e,ActivityRegisterNotFound) else 409 if isinstance(e,ActivityRegisterConflict) else 422
    return JSONResponse(status_code=status,content=jsonable_encoder(error_response(code="FARMAI_INTELLIGENCE",message=str(e))))

@router.get("/crop-cycles/{crop_cycle_id}/intelligence-context",operation_id="getFarmAIIntelligenceContext")
def context(crop_cycle_id:UUID,history_days:int=45):
    try:return success_response(build_intelligence_context(crop_cycle_id,history_days=history_days))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.post("/activity-intelligence/evaluate",operation_id="evaluateFarmAIIntelligence")
def evaluate(req:IntelligenceRequest):
    try:return success_response(evaluate_intelligence(req.crop_cycle_id,req.as_of_date,req.history_days,req.persist))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.post("/activity-intelligence/recommendations/{recommendation_id}/decision",operation_id="decideFarmAIRecommendation")
def decision(recommendation_id:UUID,req:RecommendationDecision):
    try:return success_response(decide_recommendation(recommendation_id,req))
    except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)
