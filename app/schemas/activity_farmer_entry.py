from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, model_validator

DoseBasis = Literal["TOTAL","PER_PUMP","PER_LITRE_WATER","PER_ACRE","PER_HECTARE","PER_BED","PER_PLANT"]

class FarmerInput(BaseModel):
    product_code: str = Field(min_length=1,max_length=100)
    dose: Decimal = Field(gt=0)
    dose_unit_code: str = Field(min_length=1,max_length=20)
    dose_basis_code: DoseBasis
    notes_en: str|None=None
    notes_mr: str|None=None

class FarmerActivityEntry(BaseModel):
    idempotency_key: str = Field(min_length=8,max_length=160)
    crop_cycle_id: UUID|None=None
    crop_name: str|None=Field(default=None,max_length=200)
    activity_type_code: str
    application_method_code: str|None=None
    execution_date: date
    execution_status: Literal["PARTIALLY_COMPLETED","COMPLETED"]="COMPLETED"
    purpose_codes: list[str]=Field(default_factory=list)
    pump_count: Decimal|None=Field(default=None,gt=0)
    pump_volume_l: Decimal|None=Field(default=None,gt=0)
    water_volume_l: Decimal|None=Field(default=None,gt=0)
    area: Decimal|None=Field(default=None,gt=0)
    area_unit_code: str|None=None
    bed_count: Decimal|None=Field(default=None,gt=0)
    plant_count: Decimal|None=Field(default=None,gt=0)
    performed_by: str|None=None
    notes_en: str|None=None
    notes_mr: str|None=None
    inputs: list[FarmerInput]=Field(min_length=1)
    sync_stock: bool=True
    stock_location_code: str="MAIN"
    created_by: str="FARMER"

    @model_validator(mode="after")
    def validate_context(self):
        if not self.crop_cycle_id and not self.crop_name:
            raise ValueError("crop_cycle_id or crop_name is required.")
        if self.pump_count and not (self.pump_volume_l or self.water_volume_l):
            # PER_PUMP is still calculable; PER_LITRE needs volume. Service validates per input.
            pass
        if self.area and not self.area_unit_code:
            raise ValueError("area_unit_code is required when area is supplied.")
        return self
