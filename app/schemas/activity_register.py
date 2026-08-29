"""
FarmAI Activity Register - Phase 2A request schemas.

Machine codes are English-only. Farmer-visible free text is stored as paired
English + Marathi fields.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


ActivityStatus = Literal[
    "DRAFT", "PLANNED", "SCHEDULED", "IN_PROGRESS",
    "PARTIALLY_COMPLETED", "COMPLETED", "SKIPPED", "CANCELLED"
]
ExecutionStatus = Literal[
    "IN_PROGRESS", "PARTIALLY_COMPLETED", "COMPLETED", "CANCELLED"
]
SourceType = Literal["MANUAL", "AI_CHAT", "PLANNER", "RECOMMENDATION", "IMPORT", "API"]
VerificationStatus = Literal["UNVERIFIED", "REVIEW_REQUIRED", "VERIFIED", "CONFIRMED"]
SourceConfidence = Literal["UNVERIFIED", "PARTIAL", "PROBABLE", "CONFIRMED"]
Severity = Literal["LOW", "MODERATE", "HIGH", "SEVERE"]


def _strip_required(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Value must not be empty.")
    return value


def _strip_optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class BilingualPairsMixin(BaseModel):
    @model_validator(mode="after")
    def bilingual_pairs(self):
        for en_name, mr_name in (
            ("name_en", "name_mr"),
            ("description_en", "description_mr"),
            ("notes_en", "notes_mr"),
            ("variety_en", "variety_mr"),
            ("season_name_en", "season_name_mr"),
        ):
            if hasattr(self, en_name) and hasattr(self, mr_name):
                en = getattr(self, en_name)
                mr = getattr(self, mr_name)
                if (en is None) != (mr is None):
                    raise ValueError(
                        f"{en_name} and {mr_name} must both be supplied or both be omitted."
                    )
        return self


# ---------------------------------------------------------------------------
# Existing agricultural-context foundation schemas
# ---------------------------------------------------------------------------

class FarmCreate(BilingualPairsMixin):
    name_en: str = Field(min_length=1, max_length=200)
    name_mr: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=50)
    description_en: str | None = Field(default=None, max_length=2000)
    description_mr: str | None = Field(default=None, max_length=2000)
    created_by: str | None = Field(default=None, max_length=200)

    @field_validator("name_en", "name_mr")
    @classmethod
    def required(cls, v): return _strip_required(v)

    @field_validator("code", "description_en", "description_mr", "created_by")
    @classmethod
    def optional(cls, v): return _strip_optional(v)


class PlotCreate(BilingualPairsMixin):
    farm_id: UUID
    parent_plot_id: UUID | None = None
    code: str | None = Field(default=None, max_length=50)
    name_en: str = Field(min_length=1, max_length=200)
    name_mr: str = Field(min_length=1, max_length=200)
    area: Decimal | None = Field(default=None, gt=0)
    area_unit_code: str | None = Field(default=None, max_length=20)
    description_en: str | None = Field(default=None, max_length=2000)
    description_mr: str | None = Field(default=None, max_length=2000)
    created_by: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def area_pair(self):
        if (self.area is None) != (self.area_unit_code is None):
            raise ValueError("area and area_unit_code must both be supplied or both be omitted.")
        if self.area_unit_code:
            self.area_unit_code = self.area_unit_code.upper()
        return self


class CropCycleCreate(BilingualPairsMixin):
    farm_id: UUID
    plot_id: UUID
    cycle_code: str | None = Field(default=None, max_length=100)
    crop_name_en: str = Field(min_length=1, max_length=200)
    crop_name_mr: str = Field(min_length=1, max_length=200)
    variety_en: str | None = Field(default=None, max_length=200)
    variety_mr: str | None = Field(default=None, max_length=200)
    season_name_en: str | None = Field(default=None, max_length=200)
    season_name_mr: str | None = Field(default=None, max_length=200)
    planting_date: date
    harvest_date: date | None = None
    dap_baseline_date: date | None = None
    dap_baseline_type: Literal[
        "PLANTING", "TRANSPLANTING", "CUTTING", "PRUNING",
        "RATOON_START", "GERMINATION", "OTHER"
    ] = "PLANTING"
    area: Decimal | None = Field(default=None, gt=0)
    area_unit_code: str | None = Field(default=None, max_length=20)
    status: Literal["PLANNED", "ACTIVE", "HARVESTED", "CANCELLED", "ARCHIVED"] = "ACTIVE"
    description_en: str | None = Field(default=None, max_length=2000)
    description_mr: str | None = Field(default=None, max_length=2000)
    created_by: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def cycle_rules(self):
        if self.harvest_date and self.harvest_date < self.planting_date:
            raise ValueError("harvest_date cannot be earlier than planting_date.")
        if self.dap_baseline_date is None:
            self.dap_baseline_date = self.planting_date
        if (self.area is None) != (self.area_unit_code is None):
            raise ValueError("area and area_unit_code must both be supplied or both be omitted.")
        if self.area_unit_code:
            self.area_unit_code = self.area_unit_code.upper()
        return self


# ---------------------------------------------------------------------------
# Core Activity Recording
# ---------------------------------------------------------------------------

class PlannedInputCreate(BilingualPairsMixin):
    product_code: str = Field(min_length=1, max_length=100)
    sequence_no: int = Field(default=1, ge=1)
    planned_dose: Decimal | None = Field(default=None, gt=0)
    planned_dose_unit_code: str | None = Field(default=None, max_length=20)
    dose_basis_code: str | None = Field(default=None, max_length=40)
    planned_total_quantity: Decimal | None = Field(default=None, gt=0)
    planned_total_unit_code: str | None = Field(default=None, max_length=20)
    notes_en: str | None = Field(default=None, max_length=2000)
    notes_mr: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def quantity_pairs(self):
        dose_parts = (self.planned_dose, self.planned_dose_unit_code, self.dose_basis_code)
        if any(v is not None for v in dose_parts) and not all(v is not None for v in dose_parts):
            raise ValueError(
                "planned_dose, planned_dose_unit_code and dose_basis_code must be supplied together."
            )
        total_parts = (self.planned_total_quantity, self.planned_total_unit_code)
        if any(v is not None for v in total_parts) and not all(v is not None for v in total_parts):
            raise ValueError(
                "planned_total_quantity and planned_total_unit_code must be supplied together."
            )
        if self.planned_dose_unit_code:
            self.planned_dose_unit_code = self.planned_dose_unit_code.upper()
        if self.planned_total_unit_code:
            self.planned_total_unit_code = self.planned_total_unit_code.upper()
        if self.dose_basis_code:
            self.dose_basis_code = self.dose_basis_code.upper()
        self.product_code = self.product_code.strip()
        return self


class ActivityCreate(BilingualPairsMixin):
    crop_cycle_id: UUID
    activity_type_code: str = Field(min_length=1, max_length=60)
    application_method_code: str | None = Field(default=None, max_length=60)
    status: Literal["DRAFT", "PLANNED", "SCHEDULED"] = "PLANNED"

    planned_date: date | None = None
    scheduled_date: date | None = None
    planned_area: Decimal | None = Field(default=None, gt=0)
    planned_area_unit_code: str | None = Field(default=None, max_length=20)
    planned_pump_count: Decimal | None = Field(default=None, gt=0)
    planned_water_volume: Decimal | None = Field(default=None, gt=0)
    planned_water_unit_code: str | None = Field(default=None, max_length=20)

    name_en: str | None = Field(default=None, max_length=300)
    name_mr: str | None = Field(default=None, max_length=300)
    description_en: str | None = Field(default=None, max_length=4000)
    description_mr: str | None = Field(default=None, max_length=4000)
    notes_en: str | None = Field(default=None, max_length=4000)
    notes_mr: str | None = Field(default=None, max_length=4000)

    purpose_codes: list[str] = Field(default_factory=list)
    inputs: list[PlannedInputCreate] = Field(default_factory=list)

    source_type: SourceType = "MANUAL"
    source_reference: str | None = Field(default=None, max_length=500)
    verification_status: VerificationStatus = "CONFIRMED"
    source_confidence: SourceConfidence = "CONFIRMED"
    created_by: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def activity_rules(self):
        if self.status == "SCHEDULED" and self.scheduled_date is None:
            raise ValueError("scheduled_date is required when status=SCHEDULED.")
        if (self.planned_area is None) != (self.planned_area_unit_code is None):
            raise ValueError("planned_area and planned_area_unit_code must be supplied together.")
        if (self.planned_water_volume is None) != (self.planned_water_unit_code is None):
            raise ValueError(
                "planned_water_volume and planned_water_unit_code must be supplied together."
            )
        if self.planned_area_unit_code:
            self.planned_area_unit_code = self.planned_area_unit_code.upper()
        if self.planned_water_unit_code:
            self.planned_water_unit_code = self.planned_water_unit_code.upper()
        self.activity_type_code = self.activity_type_code.upper().strip()
        if self.application_method_code:
            self.application_method_code = self.application_method_code.upper().strip()
        self.purpose_codes = [x.upper().strip() for x in self.purpose_codes]
        if len(self.purpose_codes) != len(set(self.purpose_codes)):
            raise ValueError("purpose_codes must not contain duplicates.")
        product_codes = [x.product_code.lower() for x in self.inputs]
        if len(product_codes) != len(set(product_codes)):
            raise ValueError("The same product cannot appear twice in one planned activity.")
        return self


class ExecutionInputCreate(BilingualPairsMixin):
    product_code: str = Field(min_length=1, max_length=100)
    actual_dose: Decimal | None = Field(default=None, gt=0)
    actual_dose_unit_code: str | None = Field(default=None, max_length=20)
    dose_basis_code: str | None = Field(default=None, max_length=40)
    actual_total_quantity: Decimal | None = Field(default=None, gt=0)
    actual_total_unit_code: str | None = Field(default=None, max_length=20)
    notes_en: str | None = Field(default=None, max_length=2000)
    notes_mr: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def actual_pairs(self):
        dose_parts = (self.actual_dose, self.actual_dose_unit_code, self.dose_basis_code)
        if any(v is not None for v in dose_parts) and not all(v is not None for v in dose_parts):
            raise ValueError(
                "actual_dose, actual_dose_unit_code and dose_basis_code must be supplied together."
            )
        total_parts = (self.actual_total_quantity, self.actual_total_unit_code)
        if any(v is not None for v in total_parts) and not all(v is not None for v in total_parts):
            raise ValueError(
                "actual_total_quantity and actual_total_unit_code must be supplied together."
            )
        if self.actual_dose_unit_code:
            self.actual_dose_unit_code = self.actual_dose_unit_code.upper()
        if self.actual_total_unit_code:
            self.actual_total_unit_code = self.actual_total_unit_code.upper()
        if self.dose_basis_code:
            self.dose_basis_code = self.dose_basis_code.upper()
        self.product_code = self.product_code.strip()
        return self


class ExecutionCreate(BilingualPairsMixin):
    execution_date: date
    status: ExecutionStatus = "COMPLETED"
    started_at: datetime | None = None
    completed_at: datetime | None = None

    area_treated: Decimal | None = Field(default=None, gt=0)
    area_unit_code: str | None = Field(default=None, max_length=20)
    pump_count: Decimal | None = Field(default=None, gt=0)
    water_volume: Decimal | None = Field(default=None, gt=0)
    water_unit_code: str | None = Field(default=None, max_length=20)

    performed_by: str | None = Field(default=None, max_length=200)
    notes_en: str | None = Field(default=None, max_length=4000)
    notes_mr: str | None = Field(default=None, max_length=4000)
    inputs: list[ExecutionInputCreate] = Field(default_factory=list)
    created_by: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def execution_rules(self):
        if (self.area_treated is None) != (self.area_unit_code is None):
            raise ValueError("area_treated and area_unit_code must be supplied together.")
        if (self.water_volume is None) != (self.water_unit_code is None):
            raise ValueError("water_volume and water_unit_code must be supplied together.")
        if self.completed_at and self.started_at and self.completed_at < self.started_at:
            raise ValueError("completed_at cannot be earlier than started_at.")
        if self.area_unit_code:
            self.area_unit_code = self.area_unit_code.upper()
        if self.water_unit_code:
            self.water_unit_code = self.water_unit_code.upper()
        product_codes = [x.product_code.lower() for x in self.inputs]
        if len(product_codes) != len(set(product_codes)):
            raise ValueError("The same product cannot appear twice in one execution.")
        return self


class ActivityStatusCommand(BilingualPairsMixin):
    reason_en: str | None = Field(default=None, max_length=2000)
    reason_mr: str | None = Field(default=None, max_length=2000)
    changed_by: str | None = Field(default=None, max_length=200)


class ObservationCreate(BilingualPairsMixin):
    observation_type_code: str = Field(min_length=1, max_length=60)
    observed_at: datetime | None = None
    activity_id: UUID | None = None
    execution_id: UUID | None = None
    severity: Severity | None = None
    numeric_value: Decimal | None = None
    value_unit_code: str | None = Field(default=None, max_length=20)
    description_en: str = Field(min_length=1, max_length=4000)
    description_mr: str = Field(min_length=1, max_length=4000)
    notes_en: str | None = Field(default=None, max_length=4000)
    notes_mr: str | None = Field(default=None, max_length=4000)
    source_type: SourceType = "MANUAL"
    source_reference: str | None = Field(default=None, max_length=500)
    verification_status: VerificationStatus = "CONFIRMED"
    created_by: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def observation_rules(self):
        if (self.numeric_value is None) != (self.value_unit_code is None):
            raise ValueError("numeric_value and value_unit_code must be supplied together.")
        if self.execution_id and not self.activity_id:
            raise ValueError("activity_id is required when execution_id is supplied.")
        self.observation_type_code = self.observation_type_code.upper().strip()
        if self.value_unit_code:
            self.value_unit_code = self.value_unit_code.upper()
        self.description_en = _strip_required(self.description_en)
        self.description_mr = _strip_required(self.description_mr)
        return self
