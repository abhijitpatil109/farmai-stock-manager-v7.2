from datetime import date, datetime, time
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field, model_validator

class WeatherLocationUpsert(BaseModel):
 farm_id:UUID; plot_id:UUID|None=None
 latitude:float=Field(ge=-90,le=90);longitude:float=Field(ge=-180,le=180)
 timezone:str="Asia/Kolkata";elevation_m:float|None=None
 source:Literal["MANUAL","GPS","GEOCODED","IMPORT"]="MANUAL"

class WeatherRefreshRequest(BaseModel):
 farm_id:UUID;plot_id:UUID|None=None;forecast_days:int=Field(default=3,ge=1,le=7)

class OperationalWeatherCheckRequest(BaseModel):
 crop_cycle_id:UUID|None=None;activity_id:UUID|None=None;farm_id:UUID;plot_id:UUID|None=None
 operation_type:Literal["SPRAY","FERTIGATION","IRRIGATION","OTHER"]
 planned_start:datetime;expected_duration_minutes:int=Field(gt=0,le=1440)
 rainfast_minutes:int|None=Field(default=None,ge=0,le=1440);safety_buffer_minutes:int=Field(default=30,ge=0,le=360)
 persist:bool=True
 @model_validator(mode="after")
 def aware_time(self):
  if self.planned_start.tzinfo is None:raise ValueError("planned_start must include timezone offset")
  return self

class SprayWindowConsultRequest(BaseModel):
 farm_id:UUID|None=None
 farm_name:str|None=Field(default=None,min_length=1,max_length=200)
 plot_id:UUID|None=None
 plot_name:str|None=Field(default=None,min_length=1,max_length=200)
 crop_cycle_id:UUID|None=None
 crop_name:str|None=Field(default=None,min_length=1,max_length=200)
 target_day:Literal["TODAY","TOMORROW"]="TOMORROW"
 target_date:date|None=None
 expected_duration_minutes:int=Field(default=120,gt=0,le=720)
 rainfast_minutes:int|None=Field(default=None,ge=0,le=1440)
 screening_rainfree_minutes:int=Field(default=240,ge=60,le=1440)
 safety_buffer_minutes:int=Field(default=30,ge=0,le=360)
 earliest_local_time:time=time(6,0)
 latest_local_time:time=time(18,0)
 candidate_interval_minutes:int=Field(default=60,ge=30,le=180)
 max_wind_kmh:float=Field(default=15,gt=0,le=100)
 max_gust_kmh:float=Field(default=25,gt=0,le=150)
 max_temperature_c:float=Field(default=32,ge=0,le=60)
 min_relative_humidity_pct:float=Field(default=40,ge=0,le=100)
 refresh_before_assessment:bool=True
 persist:bool=False

 @model_validator(mode="after")
 def validate_window(self):
  if self.earliest_local_time>=self.latest_local_time:
   raise ValueError("earliest_local_time must be before latest_local_time")
  if self.max_gust_kmh<self.max_wind_kmh:
   raise ValueError("max_gust_kmh cannot be lower than max_wind_kmh")
  return self

class WeatherObservationCreate(BaseModel):
 farm_id:UUID;plot_id:UUID|None=None;observed_at:datetime
 evidence_class:Literal["OFFICIAL_STATION","RADAR","FARM_SENSOR","MANUAL_OBSERVATION","MODEL_ANALYSIS","REANALYSIS"]
 source_code:str=Field(min_length=1,max_length=80);precipitation_mm:float|None=Field(default=None,ge=0)
 temperature_c:float|None=None;relative_humidity_pct:float|None=Field(default=None,ge=0,le=100)
 wind_speed_kmh:float|None=Field(default=None,ge=0);wind_gust_kmh:float|None=Field(default=None,ge=0)
 quality_status:Literal["UNVERIFIED","VERIFIED","REJECTED"]="UNVERIFIED"
 source_reference:str|None=None;raw_evidence:dict[str,Any]=Field(default_factory=dict)
 @model_validator(mode="after")
 def aware_time(self):
  if self.observed_at.tzinfo is None:raise ValueError("observed_at must include timezone offset")
  return self

class WeatherVerificationRequest(BaseModel):
 farm_id:UUID;plot_id:UUID|None=None;start:datetime|None=None;end:datetime|None=None
