"""
FarmAI Activity Register V1 - Pydantic request schemas.

Farmer-visible text follows the Activity Register bilingual contract:
English + Marathi are supplied as paired fields. Machine identifiers/codes
remain English-only.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator, field_validator


def _clean_required(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Value must not be empty.")
    return value


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class BilingualTextMixin(BaseModel):
    @model_validator(mode="after")
    def validate_bilingual_pairs(self):
        pairs = (
            ("name_en", "name_mr"),
            ("description_en", "description_mr"),
            ("variety_en", "variety_mr"),
            ("season_name_en", "season_name_mr"),
        )
        for en_name, mr_name in pairs:
            if not hasattr(self, en_name) or not hasattr(self, mr_name):
                continue
            en = getattr(self, en_name)
            mr = getattr(self, mr_name)
            if (en is None) != (mr is None):
                raise ValueError(
                    f"{en_name} and {mr_name} must both be supplied or both be omitted."
                )
        return self


class FarmCreate(BilingualTextMixin):
    name_en: str = Field(min_length=1, max_length=200)
    name_mr: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=50)
    description_en: str | None = Field(default=None, max_length=2000)
    description_mr: str | None = Field(default=None, max_length=2000)
    created_by: str | None = Field(default=None, max_length=200)

    @field_validator("name_en", "name_mr")
    @classmethod
    def clean_required(cls, value: str) -> str:
        return _clean_required(value)

    @field_validator("code", "description_en", "description_mr", "created_by")
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        return _clean_optional(value)


class PlotCreate(BilingualTextMixin):
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

    @field_validator("name_en", "name_mr")
    @classmethod
    def clean_required(cls, value: str) -> str:
        return _clean_required(value)

    @field_validator("code", "area_unit_code", "description_en", "description_mr", "created_by")
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        value = _clean_optional(value)
        return value.upper() if value and cls.__name__ == "PlotCreate" and False else value

    @model_validator(mode="after")
    def validate_area_pair(self):
        if (self.area is None) != (self.area_unit_code is None):
            raise ValueError("area and area_unit_code must both be supplied or both be omitted.")
        if self.area_unit_code:
            self.area_unit_code = self.area_unit_code.upper()
        return self


class CropCycleCreate(BilingualTextMixin):
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
    area: Decimal | None = Field(default=None, gt=0)
    area_unit_code: str | None = Field(default=None, max_length=20)
    status: Literal["PLANNED", "ACTIVE", "HARVESTED", "CANCELLED", "ARCHIVED"] = "ACTIVE"
    description_en: str | None = Field(default=None, max_length=2000)
    description_mr: str | None = Field(default=None, max_length=2000)
    created_by: str | None = Field(default=None, max_length=200)

    @field_validator("crop_name_en", "crop_name_mr")
    @classmethod
    def clean_required(cls, value: str) -> str:
        return _clean_required(value)

    @field_validator(
        "cycle_code", "variety_en", "variety_mr", "season_name_en", "season_name_mr",
        "area_unit_code", "description_en", "description_mr", "created_by"
    )
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        return _clean_optional(value)

    @model_validator(mode="after")
    def validate_cycle(self):
        bilingual_pairs = (
            ("variety_en", "variety_mr"),
            ("season_name_en", "season_name_mr"),
            ("description_en", "description_mr"),
        )
        for en_name, mr_name in bilingual_pairs:
            en = getattr(self, en_name)
            mr = getattr(self, mr_name)
            if (en is None) != (mr is None):
                raise ValueError(
                    f"{en_name} and {mr_name} must both be supplied or both be omitted."
                )
        if self.harvest_date is not None and self.harvest_date < self.planting_date:
            raise ValueError("harvest_date cannot be earlier than planting_date.")
        if (self.area is None) != (self.area_unit_code is None):
            raise ValueError("area and area_unit_code must both be supplied or both be omitted.")
        if self.area_unit_code:
            self.area_unit_code = self.area_unit_code.upper()
        return self
