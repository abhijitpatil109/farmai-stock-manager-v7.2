from __future__ import annotations
from datetime import date
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel,Field
class FarmerOutcomeRequest(BaseModel):
    crop_cycle_id: UUID
    observation_type_code: str
    observed_date: date
    activity_id: UUID|None=None
    execution_id: UUID|None=None
    severity: str|None=None
    numeric_value: Decimal|None=None
    value_unit_code: str|None=None
    description_en: str
    description_mr: str
    notes_en: str|None=None
    notes_mr: str|None=None
    created_by: str="FARMER"
