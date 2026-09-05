from __future__ import annotations
from pydantic import BaseModel,Field
from .activity_farmer_entry import FarmerActivityEntry
class FarmerCorrectionRequest(BaseModel):
    original_execution_id: str
    reason_en: str=Field(min_length=3,max_length=1000)
    reason_mr: str=Field(min_length=1,max_length=1000)
    corrected_by: str="FARMER"
    replacement: FarmerActivityEntry
