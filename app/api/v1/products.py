"""
FarmAI Core API v1 - Product lookup endpoints.

Responsibilities:
    • Search the active FarmAI product master.
    • Resolve products by name, code, brand, or active ingredient.
    • Return canonical product metadata for Stock Agent use.

These endpoints are read-only and are intended to help the FarmAI Stock Agent
resolve user-entered product names to stable backend product codes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from ...core.responses import error_response, success_response
from ...core.security import require_api_key
from ...db import connection


router = APIRouter(
    prefix="/api/v1",
    tags=["Products"],
    dependencies=[Depends(require_api_key)],
)


@router.get(
    "/products/search",
    operation_id="searchProducts",
    summary="Search FarmAI product master",
    description=(
        "Searches active products by product name, canonical product code, "
        "brand, or active ingredient. Intended for reliable Stock Agent "
        "product resolution before inventory write operations."
    ),
)
def search_products(
    q: str = Query(
        ...,
        min_length=1,
        max_length=100,
        description="Product name, product code, brand, or active ingredient.",
    ),
):
    search_term = q.strip()

    if not search_term:
        return JSONResponse(
            status_code=422,
            content=error_response(
                code="INVALID_SEARCH_QUERY",
                message="Search query must not be empty.",
            ),
        )

    pattern = f"%{search_term}%"

    with connection() as conn:
        rows = conn.execute(
            """
            SELECT
                p.product_code,
                p.product_name,
                p.brand,
                p.category,
                p.formulation,
                p.composition_text,
                p.base_unit,
                p.reorder_level,
                p.minimum_stock,
                p.active,
                COALESCE(
                    json_agg(
                        DISTINCT jsonb_build_object(
                            'active_ingredient', pai.active_ingredient,
                            'concentration', pai.concentration
                        )
                    ) FILTER (
                        WHERE pai.active_ingredient IS NOT NULL
                    ),
                    '[]'::json
                ) AS active_ingredients
            FROM products p
            LEFT JOIN product_active_ingredients pai
                ON pai.product_id = p.id
            WHERE p.active = TRUE
              AND (
                    p.product_name ILIKE %s
                 OR p.product_code ILIKE %s
                 OR COALESCE(p.brand, '') ILIKE %s
                 OR COALESCE(p.formulation, '') ILIKE %s
                 OR COALESCE(p.composition_text, '') ILIKE %s
                 OR EXISTS (
                        SELECT 1
                        FROM product_active_ingredients x
                        WHERE x.product_id = p.id
                          AND (
                                x.active_ingredient ILIKE %s
                             OR COALESCE(x.concentration, '') ILIKE %s
                          )
                    )
              )
            GROUP BY
                p.id,
                p.product_code,
                p.product_name,
                p.brand,
                p.category,
                p.formulation,
                p.composition_text,
                p.base_unit,
                p.reorder_level,
                p.minimum_stock,
                p.active
            ORDER BY
                CASE
                    WHEN LOWER(p.product_code) = LOWER(%s) THEN 0
                    WHEN LOWER(p.product_name) = LOWER(%s) THEN 1
                    WHEN p.product_name ILIKE %s THEN 2
                    ELSE 3
                END,
                p.product_name
            LIMIT 30
            """,
            (
                pattern,
                pattern,
                pattern,
                pattern,
                pattern,
                pattern,
                pattern,
                search_term,
                search_term,
                f"{search_term}%",
            ),
        ).fetchall()

    return success_response(
        rows,
        meta={
            "query": search_term,
            "record_count": len(rows),
            "source": "postgresql.products",
        },
    )


@router.get(
    "/products/{product_code}",
    operation_id="getProduct",
    summary="Get one FarmAI product",
    description=(
        "Returns canonical product-master metadata for one product code. "
        "This endpoint does not return live stock; use getProductInventory "
        "for current inventory."
    ),
)
def get_product(product_code: str):
    normalized_code = product_code.strip()

    with connection() as conn:
        row = conn.execute(
            """
            SELECT
                p.product_code,
                p.product_name,
                p.brand,
                p.category,
                p.formulation,
                p.composition_text,
                p.base_unit,
                p.reorder_level,
                p.minimum_stock,
                p.active,
                COALESCE(
                    json_agg(
                        DISTINCT jsonb_build_object(
                            'active_ingredient', pai.active_ingredient,
                            'concentration', pai.concentration
                        )
                    ) FILTER (
                        WHERE pai.active_ingredient IS NOT NULL
                    ),
                    '[]'::json
                ) AS active_ingredients
            FROM products p
            LEFT JOIN product_active_ingredients pai
                ON pai.product_id = p.id
            WHERE LOWER(p.product_code) = LOWER(%s)
            GROUP BY
                p.id,
                p.product_code,
                p.product_name,
                p.brand,
                p.category,
                p.formulation,
                p.composition_text,
                p.base_unit,
                p.reorder_level,
                p.minimum_stock,
                p.active
            """,
            (normalized_code,),
        ).fetchone()

    if not row:
        return JSONResponse(
            status_code=404,
            content=error_response(
                code="PRODUCT_NOT_FOUND",
                message=f"Product '{normalized_code}' was not found.",
            ),
        )

    return success_response(
        row,
        meta={
            "source": "postgresql.products",
        },
    )