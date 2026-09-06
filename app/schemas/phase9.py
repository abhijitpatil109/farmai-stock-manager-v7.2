from __future__ import annotations
from datetime import date,datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,Field,field_validator

class SceneDiscoverRequest(BaseModel):
    plot_id: UUID
    date_from: date
    date_to: date
    max_cloud_cover_pct: float = Field(default=80,ge=0,le=100)
    limit: int = Field(default=20,ge=1,le=100)
    @field_validator("date_to")
    @classmethod
    def order(cls,v,info):
        if info.data.get("date_from") and v<info.data["date_from"]: raise ValueError("date_to cannot be before date_from")
        return v

class RemoteRefreshRequest(SceneDiscoverRequest):
    max_scenes: int = Field(default=3,ge=1,le=10)
    analysis_scope: Literal["AUTO","FULL_POLYGON","INTERIOR_POLYGON"]="AUTO"

class AnomalyEvaluateRequest(BaseModel):
    plot_id: UUID
    observation_id: UUID|None=None

class ScoutingTaskCreate(BaseModel):
    farm_id: UUID
    plot_id: UUID
    crop_cycle_id: UUID|None=None
    anomaly_id: UUID|None=None
    source_type: Literal["MANUAL","REMOTE_SENSING","WEATHER","INTELLIGENCE","PLANNER"]="MANUAL"
    title_en: str = Field(min_length=3,max_length=240)
    title_mr: str = Field(min_length=1,max_length=240)
    reason_en: str|None=None
    reason_mr: str|None=None
    priority: Literal["LOW","MEDIUM","HIGH","URGENT"]="MEDIUM"
    checklist: list[str]=Field(default_factory=list)
    due_date: date|None=None
    created_by: str=Field(min_length=1,max_length=120)
    idempotency_key: str=Field(min_length=8,max_length=240)

class ScoutingObservationCreate(BaseModel):
    observed_at: datetime
    observer: str
    latitude: float|None=Field(default=None,ge=-90,le=90)
    longitude: float|None=Field(default=None,ge=-180,le=180)
    severity: Literal["NONE","LOW","MEDIUM","HIGH","SEVERE"]|None=None
    affected_area_pct: float|None=Field(default=None,ge=0,le=100)
    symptom_codes: list[str]=Field(default_factory=list)
    soil_moisture_condition: str|None=None
    waterlogging: bool|None=None
    wilting: bool|None=None
    yellowing: bool|None=None
    pest_visible: bool|None=None
    disease_symptom_visible: bool|None=None
    notes_en: str|None=None
    notes_mr: str|None=None
    verification_status: Literal["FARMER_REPORTED","FIELD_VERIFIED","EXPERT_VERIFIED"]="FARMER_REPORTED"
    @field_validator("observed_at")
    @classmethod
    def aware(cls,v):
        if v.tzinfo is None or v.utcoffset() is None: raise ValueError("observed_at must include timezone")
        return v

class SeasonComparisonRequest(BaseModel):
    current_crop_cycle_id: UUID
    baseline_crop_cycle_id: UUID
    metric_code: str="NDVI"
