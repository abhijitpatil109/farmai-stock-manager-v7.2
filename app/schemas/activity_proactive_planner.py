
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

Priority = Literal["LOW","MEDIUM","HIGH","CRITICAL"]


class RecommendationToActivityRequest(BaseModel):
    recommendation_id: UUID
    activity_type_code: str = Field(min_length=1,max_length=60)
    application_method_code: str|None = Field(default=None,max_length=60)
    planned_date: date|None = None
    scheduled_date: date|None = None
    planned_area: Decimal|None = Field(default=None,gt=0)
    planned_area_unit_code: str|None = Field(default=None,max_length=20)
    planned_pump_count: Decimal|None = Field(default=None,gt=0)
    planned_water_volume: Decimal|None = Field(default=None,gt=0)
    planned_water_unit_code: str|None = Field(default=None,max_length=20)
    name_en: str|None = Field(default=None,max_length=300)
    name_mr: str|None = Field(default=None,max_length=300)
    description_en: str|None = Field(default=None,max_length=4000)
    description_mr: str|None = Field(default=None,max_length=4000)
    notes_en: str|None = Field(default=None,max_length=4000)
    notes_mr: str|None = Field(default=None,max_length=4000)
    purpose_codes: list[str] = Field(default_factory=list)
    priority: Priority = "MEDIUM"
    created_by: str = Field(default="FARMER",min_length=1,max_length=200)

    @model_validator(mode="after")
    def validate_contract(self):
        for en,mr in (
            ("name_en","name_mr"),
            ("description_en","description_mr"),
            ("notes_en","notes_mr"),
        ):
            if (getattr(self,en) is None)!=(getattr(self,mr) is None):
                raise ValueError(f"{en} and {mr} must both be supplied or both omitted.")

        if (self.planned_area is None)!=(self.planned_area_unit_code is None):
            raise ValueError("planned_area and planned_area_unit_code must be supplied together.")
        if (self.planned_water_volume is None)!=(self.planned_water_unit_code is None):
            raise ValueError("planned_water_volume and planned_water_unit_code must be supplied together.")
        if self.scheduled_date and self.planned_date and self.scheduled_date < self.planned_date:
            raise ValueError("scheduled_date cannot be earlier than planned_date.")

        self.activity_type_code=self.activity_type_code.upper().strip()
        if self.application_method_code:
            self.application_method_code=self.application_method_code.upper().strip()
        if self.planned_area_unit_code:
            self.planned_area_unit_code=self.planned_area_unit_code.upper().strip()
        if self.planned_water_unit_code:
            self.planned_water_unit_code=self.planned_water_unit_code.upper().strip()

        self.purpose_codes=[x.upper().strip() for x in self.purpose_codes]
        if len(self.purpose_codes)!=len(set(self.purpose_codes)):
            raise ValueError("purpose_codes must not contain duplicates.")
        return self


class PriorityRequest(BaseModel):
    priority: Priority
    changed_by: str = Field(default="FARMER",min_length=1,max_length=200)


class HoldRequest(BaseModel):
    hold_until: date|None = None
    reason_en: str = Field(min_length=1,max_length=2000)
    reason_mr: str = Field(min_length=1,max_length=2000)
    changed_by: str = Field(default="FARMER",min_length=1,max_length=200)


class ReleaseHoldRequest(BaseModel):
    changed_by: str = Field(default="FARMER",min_length=1,max_length=200)


class PlannerRescheduleRequest(BaseModel):
    scheduled_date: date
    changed_by: str = Field(default="FARMER",min_length=1,max_length=200)


class DismissRequest(BaseModel):
    reason_en: str = Field(min_length=1,max_length=2000)
    reason_mr: str = Field(min_length=1,max_length=2000)
    changed_by: str = Field(default="FARMER",min_length=1,max_length=200)
