from __future__ import annotations
from datetime import date
from pydantic import BaseModel, Field
class StockReserveRequest(BaseModel):
    location_code: str = "MAIN"
    required_date: date | None = None
    changed_by: str = "ADMIN"
class StockReleaseRequest(BaseModel):
    changed_by: str = "ADMIN"
    reason_en: str | None = None
    reason_mr: str | None = None
class StockSyncRequest(BaseModel):
    location_code: str = "MAIN"
    changed_by: str = "ADMIN"
class StockReverseRequest(BaseModel):
    changed_by: str = "ADMIN"
    reason_en: str = Field(min_length=3,max_length=1000)
    reason_mr: str = Field(min_length=1,max_length=1000)
