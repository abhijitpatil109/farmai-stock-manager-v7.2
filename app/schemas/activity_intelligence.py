from __future__ import annotations
from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,Field

class IntelligenceRequest(BaseModel):
    crop_cycle_id: UUID
    as_of_date: date|None=None
    history_days: int=Field(default=45,ge=7,le=365)
    persist: bool=False

class RecommendationDecision(BaseModel):
    decision: Literal["ACCEPTED","REJECTED"]
    reason_en: str|None=None
    reason_mr: str|None=None
    decided_by: str="FARMER"
