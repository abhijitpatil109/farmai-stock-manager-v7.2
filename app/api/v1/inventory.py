"""
FarmAI Core API v1 - Inventory read endpoints.

Responsibilities:
    • Return the live current inventory from PostgreSQL.
    • Return the live balance for one canonical product code.

These endpoints are read-only and are intended to be used by the FarmAI
Stock Agent as the authoritative source for current stock.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ...core.responses import error_response, success_response
from ...core.security import require_api_key
from ...db import connection


router = APIRouter(
    prefix="/api/v1",
    tags=["Inventory"],
    dependencies=[Depends(require_api_key)],
)


@router.get(
    "/inventory",
    operation_id="getCurrentInventory",
    summary="Get current FarmAI inventory",
    description=(
        "Returns the live physical, reserved and available stock for every "
        "active FarmAI product and active stock location."
    ),
)
def get_current_inventory():
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT
                product_code,
                product_name,
                brand,
                category,
                unit,
                location_code,
                physical_stock,
                reserved_stock,
                available_stock
            FROM current_inventory
            ORDER BY category, product_name, location_code
            """
        ).fetchall()

    return success_response(
        rows,
        meta={
            "record_count": len(rows),
            "source": "postgresql.current_inventory",
        },
    )


@router.get(
    "/inventory/{product_code}",
    operation_id="getProductInventory",
    summary="Get inventory for one product",
    description=(
        "Returns the current physical, reserved and available stock for one "
        "canonical FarmAI product code across all active stock locations."
    ),
)
def get_product_inventory(product_code: str):
    normalized_code = product_code.strip()

    with connection() as conn:
        rows = conn.execute(
            """
            SELECT
                product_code,
                product_name,
                brand,
                category,
                unit,
                location_code,
                physical_stock,
                reserved_stock,
                available_stock
            FROM current_inventory
            WHERE LOWER(product_code) = LOWER(%s)
            ORDER BY location_code
            """,
            (normalized_code,),
        ).fetchall()

    if not rows:
        return JSONResponse(
            status_code=404,
            content=error_response(
                code="PRODUCT_NOT_FOUND",
                message=f"Product '{normalized_code}' was not found.",
            ),
        )

    first = rows[0]

    physical_total = sum(row["physical_stock"] for row in rows)
    reserved_total = sum(row["reserved_stock"] for row in rows)
    available_total = sum(row["available_stock"] for row in rows)

    data = {
        "product_code": first["product_code"],
        "product_name": first["product_name"],
        "brand": first["brand"],
        "category": first["category"],
        "unit": first["unit"],
        "physical_stock": physical_total,
        "reserved_stock": reserved_total,
        "available_stock": available_total,
        "locations": [
            {
                "location_code": row["location_code"],
                "physical_stock": row["physical_stock"],
                "reserved_stock": row["reserved_stock"],
                "available_stock": row["available_stock"],
            }
            for row in rows
        ],
    }

    return success_response(
        data,
        meta={
            "location_count": len(rows),
            "source": "postgresql.current_inventory",
        },
    )