"""FarmAI Activity Planner — Phase 3 operational request schemas."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, model_validator

PlannerStatus = Literal["DRAFT","PLANNED","SCHEDULED","IN_PROGRESS","PARTIALLY_COMPLETED","COMPLETED","SKIPPED","CANCELLED"]

class PlannerInput(BaseModel):
    product_code: str = Field(min_length=1, max_length=100)
    sequence_no: int = Field(default=1, ge=1)
    planned_dose: Decimal|None = Field(default=None, gt=0)
    planned_dose_unit_code: str|None = None
    dose_basis_code: str|None = None
    planned_total_quantity: Decimal|None = Field(default=None, gt=0)
    planned_total_unit_code: str|None = None
    notes_en: str|None = None
    notes_mr: str|None = None

class ActivityPlanUpdate(BaseModel):
    planned_date: date|None = None
    scheduled_date: date|None = None
    planned_area: Decimal|None = Field(default=None, gt=0)
    planned_area_unit_code: str|None = None
    planned_pump_count: Decimal|None = Field(default=None, gt=0)
    planned_water_volume: Decimal|None = Field(default=None, gt=0)
    planned_water_unit_code: str|None = None
    name_en: str|None = None
    name_mr: str|None = None
    description_en: str|None = None
    description_mr: str|None = None
    notes_en: str|None = None
    notes_mr: str|None = None
    purpose_codes: list[str]|None = None
    inputs: list[PlannerInput]|None = None
    updated_by: str|None = None

    @model_validator(mode="after")
    def pairs(self):
        if (self.planned_area is None) != (self.planned_area_unit_code is None):
            raise ValueError("planned_area and planned_area_unit_code must be supplied together.")
        if (self.planned_water_volume is None) != (self.planned_water_unit_code is None):
            raise ValueError("planned_water_volume and planned_water_unit_code must be supplied together.")
        if self.purpose_codes is not None:
            self.purpose_codes=[x.upper().strip() for x in self.purpose_codes]
            if len(self.purpose_codes)!=len(set(self.purpose_codes)):
                raise ValueError("purpose_codes must not contain duplicates.")
        if self.inputs is not None:
            codes=[x.product_code.lower().strip() for x in self.inputs]
            if len(codes)!=len(set(codes)):
                raise ValueError("The same product cannot appear twice.")
        return self

class ScheduleCommand(BaseModel):
    scheduled_date: date
    changed_by: str|None = None
    reason_en: str|None = None
    reason_mr: str|None = None

class StartCommand(BaseModel):
    changed_by: str|None = None
    reason_en: str|None = None
    reason_mr: str|None = None
