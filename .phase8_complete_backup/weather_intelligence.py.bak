from fastapi import APIRouter,Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from ...core.responses import error_response,success_response
from ...core.security import require_api_key
from ...schemas.weather_intelligence import (WeatherLocationUpsert,WeatherRefreshRequest,
 OperationalWeatherCheckRequest,WeatherObservationCreate,WeatherVerificationRequest)
from ...services.external_weather import (upsert_location,refresh_weather,refresh_ensembles,refresh_all,
 operational_check,record_observation,verify_forecasts)
from ...services.activity_register import ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation

router=APIRouter(prefix="/api/v1",tags=["External Intelligence / Weather"],dependencies=[Depends(require_api_key)])
def _err(e):
 status=404 if isinstance(e,ActivityRegisterNotFound) else 409 if isinstance(e,ActivityRegisterConflict) else 422
 return JSONResponse(status_code=status,content=jsonable_encoder(error_response(code="FARMAI_WEATHER",message=str(e))))

@router.put("/weather-intelligence/locations",operation_id="upsertFarmWeatherLocation")
def location(req:WeatherLocationUpsert):
 try:return success_response(upsert_location(req))
 except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.post("/weather-intelligence/refresh",operation_id="refreshFarmWeather")
def refresh(req:WeatherRefreshRequest):
 try:return success_response(refresh_weather(req.farm_id,req.plot_id,req.forecast_days))
 except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.post("/weather-intelligence/refresh-ensembles",operation_id="refreshFarmWeatherEnsembles")
def ensembles(req:WeatherRefreshRequest):
 try:return success_response(refresh_ensembles(req.farm_id,req.plot_id,req.forecast_days))
 except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.post("/weather-intelligence/refresh-all",operation_id="refreshAllFarmWeatherEvidence")
def all_weather(req:WeatherRefreshRequest):
 try:return success_response(refresh_all(req.farm_id,req.plot_id,req.forecast_days))
 except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.post("/weather-intelligence/operational-check",operation_id="checkOperationalWeather")
def check(req:OperationalWeatherCheckRequest):
 try:return success_response(operational_check(req))
 except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.post("/weather-intelligence/observations",operation_id="recordWeatherObservation")
def observation(req:WeatherObservationCreate):
 try:return success_response(record_observation(req))
 except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)

@router.post("/weather-intelligence/verify-forecasts",operation_id="verifyWeatherForecasts")
def verify(req:WeatherVerificationRequest):
 try:return success_response(verify_forecasts(req.farm_id,req.plot_id,req.start,req.end))
 except (ActivityRegisterNotFound,ActivityRegisterConflict,ActivityRegisterValidation) as e:return _err(e)
