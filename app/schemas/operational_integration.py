from __future__ import annotations

from typing import Literal
from pydantic import BaseModel
from .activity_farmer_entry import FarmerActivityEntry


class OperationalActivityCompleteRequest(BaseModel):
    """Explicit authorization envelope for farmer-visible operational writes."""
    farmer_authorized: Literal[True]
    entry: FarmerActivityEntry


class OperationalModeContract(BaseModel):
    mode: Literal["FARMAI_OPERATIONAL"] = "FARMAI_OPERATIONAL"
    authoritative_source: str = "FarmAI production APIs/PostgreSQL"
    memory_policy: str = (
        "Conversation memory may help interpret language but must not replace live "
        "FarmAI state for current stock, activity, crop-cycle, planner, weather, "
        "remote-sensing, scouting, or execution facts."
    )
