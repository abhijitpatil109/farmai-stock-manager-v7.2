"""
FarmAI Stock Manager V7.2 - B3.4 Create Product API

Canonical product code policy
-----------------------------
Backend-generated product codes use an isolated production namespace:

    FERT-P0001
    FERT-P0002
    MIC-P0001
    FUNG-P0001

Rules
-----
1. Client never supplies product_code.
2. Backend generates the canonical code.
3. Only P-prefixed codes participate in sequencing.
4. Legacy/manual codes (e.g. FERT-191921) are ignored.
5. The highest existing P-code in the category determines the next code.
6. Product creation does NOT create stock.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...core.security import require_api_key
from ...db import connection

router = APIRouter(
    prefix="/api/v1",
    tags=["Products"],
    dependencies=[Depends(require_api_key)],
)

CATEGORY_PREFIX = {
    "Fertilizers": "FERT",
    "Biostimulants & Growth Promoters": "BST",
    "Micronutrients": "MIC",
    "Fungicides": "FUNG",
    "Insecticides": "INS",
    "Herbicides": "HERB",
    "Bio-fertilizers & Bio-pesticides": "BIO",
    "Adjuvants / Stickers": "ADJ",
}


class CreateProductRequest(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    category: str
    base_unit: str
    brand: str | None = None
    content: str | None = None
    primary_function: str | None = None
    notes: str | None = None
    active: bool = True


def generate_product_code(conn, category: str) -> str:
    """
    Returns:
        FERT-P0001
        FERT-P0002
        MIC-P0001
    """
    prefix = CATEGORY_PREFIX[category]

    row = conn.execute(
        """
        SELECT product_code
        FROM products
        WHERE product_code ~ %s
        ORDER BY CAST(SUBSTRING(product_code FROM '[0-9]+$') AS INTEGER) DESC
        LIMIT 1
        """,
        (rf"^{prefix}-P[0-9]{{4}}$",),
    ).fetchone()

    if not row:
        return f"{prefix}-P0001"

    last = int(row["product_code"].split("-P")[1])
    return f"{prefix}-P{last + 1:04d}"


@router.post(
    "/products",
    operation_id="createProduct",
    summary="Create canonical FarmAI product",
)
def create_product(req: CreateProductRequest):
    with connection() as conn:
        conn.execute("LOCK TABLE products IN SHARE ROW EXCLUSIVE MODE")

        existing = conn.execute(
            """
            SELECT product_code
            FROM products
            WHERE LOWER(product_name)=LOWER(%s)
              AND LOWER(COALESCE(brand,''))=
                  LOWER(COALESCE(%s,''))
              AND active=TRUE
            LIMIT 1
            """,
            (req.product_name.strip(), req.brand),
        ).fetchone()

        if existing:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PRODUCT_ALREADY_EXISTS",
                    "product_code": existing["product_code"],
                },
            )

        product_code = generate_product_code(conn, req.category)

        row = conn.execute(
            """
            INSERT INTO products(
                product_code,
                product_name,
                category,
                base_unit,
                brand,
                content,
                primary_function,
                notes,
                active
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                product_code,
                req.product_name.strip(),
                req.category,
                req.base_unit,
                req.brand,
                req.content,
                req.primary_function,
                req.notes,
                req.active,
            ),
        ).fetchone()

        conn.commit()

        return {
            "created": True,
            "product_code": row["product_code"],
            "product": row,
            "initial_stock": 0,
            "message": "Product master created successfully. No stock movement recorded."
        }