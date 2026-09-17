"""Normalization for optional history query fields received as URL strings."""
from datetime import date
from typing import Annotated
from uuid import UUID

from pydantic import BeforeValidator

from .activity_register import ExecutionStatus


def optional_query(value):
    if isinstance(value, str):
        value = value.strip()
        if value.casefold() in {"", "null", "none"}:
            return None
    return value


def optional_status(value):
    value = optional_query(value)
    if isinstance(value, str):
        value = value.upper()
        if value == "ALL":
            return None
    return value


HistoryCycleId = Annotated[UUID | None, BeforeValidator(optional_query)]
HistoryDate = Annotated[date | None, BeforeValidator(optional_query)]
HistoryCropName = Annotated[str | None, BeforeValidator(optional_query)]
HistoryStatus = Annotated[ExecutionStatus | None, BeforeValidator(optional_status)]
