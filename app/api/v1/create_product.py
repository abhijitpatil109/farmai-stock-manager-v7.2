"""
FarmAI Stock Manager V7.2 - B3 Create Product API

POST /api/v1/products

Purpose
-------
Create a new canonical FarmAI product in the product master.

Safety
------
- Explicit product creation only.
- Reject duplicate product_code.
- Reject duplicate product_name + brand when already active.
- Validate category and base unit.
- Never creates stock automatically.
- Newly created products begin with zero inventory until a purchase,
  opening balance, or physical verification is recorded.
"""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from ...core.responses import error_response, success_response
from ...core.security import require_api_key
from ...db import connection

router = APIRouter(
    prefix="/api/v1",
    tags=["Products"],
    dependencies=[Depends(require_api_key)],
)

ALLOWED_CATEGORIES = {
    "Fertilizers",
    "Biostimulants & Growth Promoters",
    "Micronutrients",
    "Fungicides",
    "Insecticides",
    "Herbicides",
    "Bio-fertilizers & Bio-pesticides",
    "Adjuvants / Stickers",
}

ALLOWED_BASE_UNITS = {"kg", "g", "L", "ml"}


class CreateProductRequest(BaseModel):
    product_code: str = Field(min_length=3, max_length=100)
    product_name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    base_unit: str = Field(min_length=1, max_length=20)

    brand: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, max_length=500)
    primary_function: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)
    active: bool = True

    @field_validator("product_code")
    @classmethod
    def validate_product_code(cls, value: str):
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{2,99}", value):
            raise ValueError(
                "product_code may contain only letters, numbers, '-' and '_' "
                "and must start with a letter or number."
            )
        return value

    @field_validator("product_name", "category", "base_unit")
    @classmethod
    def strip_required(cls, value: str):
        return value.strip()

    @field_validator("brand", "content", "primary_function", "notes")
    @classmethod
    def strip_optional(cls, value):
        if value is None:
            return None
        value = value.strip()
        return value or None


def _error(status_code: int, code: str, message: str, details=None):
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(
            error_response(code=code, message=message, details=details)
        ),
    )


def _existing_by_code(conn, product_code: str):
    return conn.execute(
        """
        SELECT *
        FROM products
        WHERE LOWER(product_code)=LOWER(%s)
        LIMIT 1
        """,
        (product_code,),
    ).fetchone()


def _existing_by_name_brand(conn, product_name: str, brand: str | None):
    return conn.execute(
        """
        SELECT *
        FROM products
        WHERE LOWER(product_name)=LOWER(%s)
          AND LOWER(COALESCE(brand,''))=LOWER(COALESCE(%s,''))
          AND active=TRUE
        LIMIT 1
        """,
        (product_name, brand),
    ).fetchone()


def _column_names(conn):
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public'
          AND table_name='products'
        """
    ).fetchall()
    return {row["column_name"] for row in rows}


@router.post(
    "/products",
    operation_id="createProduct",
    summary="Create a new canonical FarmAI product",
    description=(
        "Creates a product-master record only. This operation does not add stock. "
        "Use purchase, opening-balance, or verification APIs after creation."
    ),
)
def create_product(req: CreateProductRequest):
    if req.category not in ALLOWED_CATEGORIES:
        return _error(
            422,
            "INVALID_CATEGORY",
            "Category must match one of the eight FarmAI Stock Registry V6.3 categories.",
            {"allowed_categories": sorted(ALLOWED_CATEGORIES)},
        )

    if req.base_unit not in ALLOWED_BASE_UNITS:
        return _error(
            422,
            "INVALID_BASE_UNIT",
            "base_unit must be one of kg, g, L or ml.",
            {"allowed_base_units": sorted(ALLOWED_BASE_UNITS)},
        )

    with connection() as conn:
        try:
            by_code = _existing_by_code(conn, req.product_code)
            if by_code:
                return _error(
                    409,
                    "PRODUCT_CODE_EXISTS",
                    f"Product code '{req.product_code}' already exists.",
                    {
                        "product_code": by_code["product_code"],
                        "product_name": by_code["product_name"],
                    },
                )

            by_name = _existing_by_name_brand(conn, req.product_name, req.brand)
            if by_name:
                return _error(
                    409,
                    "PRODUCT_ALREADY_EXISTS",
                    "An active product with the same name and brand already exists.",
                    {
                        "product_code": by_name["product_code"],
                        "product_name": by_name["product_name"],
                        "brand": by_name.get("brand"),
                    },
                )

            # Support the current FarmAI products table while remaining tolerant
            # of optional metadata columns that may not yet exist.
            available_columns = _column_names(conn)

            payload = {
                "product_code": req.product_code,
                "product_name": req.product_name,
                "category": req.category,
                "base_unit": req.base_unit,
                "brand": req.brand,
                "content": req.content,
                "primary_function": req.primary_function,
                "notes": req.notes,
                "active": req.active,
            }

            insert_payload = {
                key: value
                for key, value in payload.items()
                if key in available_columns
            }

            mandatory = {"product_code", "product_name", "category", "base_unit"}
            missing = mandatory - set(insert_payload)
            if missing:
                return _error(
                    500,
                    "PRODUCT_SCHEMA_MISMATCH",
                    "The products table is missing fields required by the B3 API.",
                    {"missing_columns": sorted(missing)},
                )

            columns = list(insert_payload.keys())
            placeholders = ",".join(["%s"] * len(columns))
            sql = (
                f"INSERT INTO products ({','.join(columns)}) "
                f"VALUES ({placeholders}) RETURNING *"
            )

            row = conn.execute(
                sql,
                tuple(insert_payload[col] for col in columns),
            ).fetchone()

            conn.commit()

            return success_response(
                {
                    "created": True,
                    "product": row,
                    "initial_stock": 0,
                    "message": (
                        "Product created in the master. No stock movement was created."
                    ),
                },
                meta={"source": "postgresql.products"},
            )

        except Exception:
            conn.rollback()
            raise
