from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field, model_validator

SourceType = Literal["CHAT_HISTORY","PHYSICAL_REGISTER","STOCK_HISTORY","MANUAL","FILE_IMPORT","OTHER"]
Confidence = Literal["UNVERIFIED","PARTIAL","PROBABLE","CONFIRMED"]
Verification = Literal["UNVERIFIED","REVIEW_REQUIRED","VERIFIED","CONFIRMED"]
DuplicateDecision = Literal["ACCEPT_AS_NEW","LINK_EXISTING","REJECT_IMPORT"]

class ImportBatchCreate(BaseModel):
    batch_code: str = Field(min_length=3,max_length=150)
    farm_id: UUID
    source_type: SourceType
    source_name: str = Field(min_length=1,max_length=300)
    source_reference: str|None = Field(default=None,max_length=1000)
    notes_en: str|None = Field(default=None,max_length=4000)
    notes_mr: str|None = Field(default=None,max_length=4000)
    created_by: str|None = Field(default=None,max_length=200)
    @model_validator(mode="after")
    def bilingual(self):
        if (self.notes_en is None)!=(self.notes_mr is None):
            raise ValueError("notes_en and notes_mr must both be supplied or both omitted.")
        self.batch_code=self.batch_code.strip(); self.source_name=self.source_name.strip()
        return self

class ImportInputCreate(BaseModel):
    source_sequence: int|None = Field(default=None,ge=1)
    raw_product_name: str|None = Field(default=None,max_length=300)
    raw_product_code: str|None = Field(default=None,max_length=100)
    dose: Decimal|None = Field(default=None,gt=0)
    dose_unit_code: str|None = Field(default=None,max_length=20)
    dose_basis_code: str|None = Field(default=None,max_length=40)
    total_quantity: Decimal|None = Field(default=None,gt=0)
    total_unit_code: str|None = Field(default=None,max_length=20)
    notes_en: str|None = Field(default=None,max_length=2000)
    notes_mr: str|None = Field(default=None,max_length=2000)
    @model_validator(mode="after")
    def validate_pairs(self):
        if not self.raw_product_name and not self.raw_product_code:
            raise ValueError("raw_product_name or raw_product_code is required.")
        d=(self.dose,self.dose_unit_code,self.dose_basis_code)
        if any(x is not None for x in d) and not all(x is not None for x in d):
            raise ValueError("dose, dose_unit_code and dose_basis_code must be supplied together.")
        t=(self.total_quantity,self.total_unit_code)
        if any(x is not None for x in t) and not all(x is not None for x in t):
            raise ValueError("total_quantity and total_unit_code must be supplied together.")
        if (self.notes_en is None)!=(self.notes_mr is None):
            raise ValueError("notes_en and notes_mr must both be supplied or both omitted.")
        if self.dose_unit_code: self.dose_unit_code=self.dose_unit_code.upper().strip()
        if self.dose_basis_code: self.dose_basis_code=self.dose_basis_code.upper().strip()
        if self.total_unit_code: self.total_unit_code=self.total_unit_code.upper().strip()
        if self.raw_product_code: self.raw_product_code=self.raw_product_code.strip()
        if self.raw_product_name: self.raw_product_name=self.raw_product_name.strip()
        return self

class ImportRecordCreate(BaseModel):
    source_record_key: str = Field(min_length=1,max_length=300)
    source_sequence: int|None = Field(default=None,ge=1)
    raw_payload: dict[str,Any]
    farm_id: UUID|None=None
    plot_id: UUID|None=None
    crop_cycle_id: UUID|None=None
    activity_date: date|None=None
    activity_type_code: str|None=Field(default=None,max_length=60)
    application_method_code: str|None=Field(default=None,max_length=60)
    name_en: str|None=Field(default=None,max_length=300)
    name_mr: str|None=Field(default=None,max_length=300)
    description_en: str|None=Field(default=None,max_length=4000)
    description_mr: str|None=Field(default=None,max_length=4000)
    notes_en: str|None=Field(default=None,max_length=4000)
    notes_mr: str|None=Field(default=None,max_length=4000)
    pump_count: Decimal|None=Field(default=None,gt=0)
    water_volume: Decimal|None=Field(default=None,gt=0)
    water_unit_code: str|None=Field(default=None,max_length=20)
    area: Decimal|None=Field(default=None,gt=0)
    area_unit_code: str|None=Field(default=None,max_length=20)
    source_confidence: Confidence="UNVERIFIED"
    verification_status: Verification="UNVERIFIED"
    inputs: list[ImportInputCreate]=Field(default_factory=list)
    @model_validator(mode="after")
    def validate_record(self):
        for a,b in [("name_en","name_mr"),("description_en","description_mr"),("notes_en","notes_mr")]:
            if (getattr(self,a) is None)!=(getattr(self,b) is None):
                raise ValueError(f"{a} and {b} must both be supplied or both omitted.")
        if (self.water_volume is None)!=(self.water_unit_code is None):
            raise ValueError("water_volume and water_unit_code must be supplied together.")
        if (self.area is None)!=(self.area_unit_code is None):
            raise ValueError("area and area_unit_code must be supplied together.")
        if self.activity_type_code: self.activity_type_code=self.activity_type_code.upper().strip()
        if self.application_method_code: self.application_method_code=self.application_method_code.upper().strip()
        if self.water_unit_code: self.water_unit_code=self.water_unit_code.upper().strip()
        if self.area_unit_code: self.area_unit_code=self.area_unit_code.upper().strip()
        self.source_record_key=self.source_record_key.strip()
        return self

class ContextResolution(BaseModel):
    farm_id: UUID
    plot_id: UUID
    crop_cycle_id: UUID
    activity_date: date
    activity_type_code: str
    application_method_code: str|None=None
    reviewed_by: str|None=Field(default=None,max_length=200)

class ProductResolution(BaseModel):
    import_input_id: UUID
    product_code: str=Field(min_length=1,max_length=100)
    reviewed_by: str|None=Field(default=None,max_length=200)

class SourceConflictResolution(BaseModel):
    issue_id: UUID
    reviewed_by: str=Field(min_length=1,max_length=200)
    resolution_en: str=Field(min_length=1,max_length=2000)
    resolution_mr: str=Field(min_length=1,max_length=2000)

class PurposeResolution(BaseModel):
    purpose_codes: list[str]=Field(min_length=1,max_length=20)
    source_text: str|None=Field(default=None,max_length=4000)
    reviewed_by: str=Field(min_length=1,max_length=200)
    @model_validator(mode="after")
    def normalize(self):
        self.purpose_codes=list(dict.fromkeys(code.strip().upper() for code in self.purpose_codes if code.strip()))
        if not self.purpose_codes: raise ValueError("At least one purpose code is required.")
        return self

class DuplicateResolution(BaseModel):
    decision: DuplicateDecision
    candidate_activity_id: UUID
    reviewed_by: str=Field(min_length=1,max_length=200)
    resolution_en: str=Field(min_length=1,max_length=2000)
    resolution_mr: str=Field(min_length=1,max_length=2000)

class ReviewCommand(BaseModel):
    reviewed_by: str=Field(min_length=1,max_length=200)
    notes_en: str|None=Field(default=None,max_length=2000)
    notes_mr: str|None=Field(default=None,max_length=2000)
    @model_validator(mode="after")
    def bilingual(self):
        if (self.notes_en is None)!=(self.notes_mr is None):
            raise ValueError("notes_en and notes_mr must both be supplied or both omitted.")
        return self
