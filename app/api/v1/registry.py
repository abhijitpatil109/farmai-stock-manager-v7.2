"""
FarmAI Core API v1 - FarmAI Stock Registry V7.2 read endpoint.

V7.2.3 Presentation Consistency Patch.

Responsibilities:
    • Assemble the presentation-ready FarmAI Stock Registry V7.2.
    • Reuse live stock from PostgreSQL current_inventory.
    • Join product_display_metadata for bilingual/display fields.
    • Normalize legacy product categories into the frozen V7.2 taxonomy.
    • Aggregate stock across locations so each canonical product appears once.
    • Compute the registry stock status server-side.
    • Return all 8 frozen categories, including empty categories.

This module is READ ONLY. It does not calculate ledger balances and does not
modify inventory, transactions, products, or metadata.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...core.responses import success_response
from ...core.security import require_api_key
from ...db import connection


class RegistryProductV72(BaseModel):
    product_code: str
    product_en: str
    product_mr: str | None = None
    show_marathi_name: bool
    stock_quantity: Decimal
    stock_unit: str | None = None
    stock_display: str
    status_code: Literal["GOOD", "LOW", "OUT", "UNKNOWN"]
    status_display: str
    used_for_en: str
    used_for_mr: str
    apply_when_en: str
    apply_when_mr: str
    dose: str
    content: str
    farmai_advice_en: str
    farmai_advice_mr: str
    inventory_discrepancy: bool


class RegistryCategoryV72(BaseModel):
    order: int = Field(ge=1, le=8)
    key: str
    name_en: str
    name_mr: str
    products: list[RegistryProductV72]


class RegistryDataV72(BaseModel):
    registry_version: Literal["7.2"]
    source: str
    columns: list[str]
    categories: list[RegistryCategoryV72]


class RegistryMetaV72(BaseModel):
    category_count: int
    product_count: int
    unmapped_product_count: int
    unmapped_product_codes: list[str]
    source: str


class RegistryEnvelopeV72(BaseModel):
    ok: bool
    data: RegistryDataV72
    meta: RegistryMetaV72


router = APIRouter(
    prefix="/api/v1",
    tags=["Registry"],
    dependencies=[Depends(require_api_key)],
)


CATEGORY_DEFINITIONS = [
    {
        "order": 1,
        "key": "fertilizers",
        "name_en": "Fertilizers",
        "name_mr": "खते",
    },
    {
        "order": 2,
        "key": "biostimulants_biofertilizers",
        "name_en": "Biostimulants & Biofertilizers",
        "name_mr": "जैव उत्तेजक व जैव खते",
    },
    {
        "order": 3,
        "key": "micronutrients",
        "name_en": "Micronutrients",
        "name_mr": "सूक्ष्म अन्नद्रव्ये",
    },
    {
        "order": 4,
        "key": "fungicides",
        "name_en": "Fungicides",
        "name_mr": "बुरशीनाशके",
    },
    {
        "order": 5,
        "key": "insecticides",
        "name_en": "Insecticides",
        "name_mr": "कीटकनाशके",
    },
    {
        "order": 6,
        "key": "herbicides",
        "name_en": "Herbicides",
        "name_mr": "तणनाशके",
    },
    {
        "order": 7,
        "key": "biopesticides",
        "name_en": "Biopesticides",
        "name_mr": "जैव कीटकनाशके",
    },
    {
        "order": 8,
        "key": "adjuvants_stickers",
        "name_en": "Adjuvants / Stickers",
        "name_mr": "सहाय्यक द्रव्ये / स्टिकर्स",
    },
]

CATEGORY_BY_NAME = {
    category["name_en"]: category for category in CATEGORY_DEFINITIONS
}


def _format_quantity(value: Decimal | int | float | None) -> str:
    """Format stock without unnecessary trailing zeroes."""
    if value is None:
        return "Unknown"

    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    text = format(decimal_value, "f")

    if "." in text:
        text = text.rstrip("0").rstrip(".")

    return text or "0"


def _stock_display(
    quantity: Decimal | int | float | None,
    unit: str | None,
) -> str:
    if quantity is None:
        return "Unknown"

    quantity_text = _format_quantity(quantity)
    return f"{quantity_text} {unit}" if unit else quantity_text


def _status(
    available_stock: Decimal | int | float | None,
    reorder_level: Decimal | int | float | None,
) -> tuple[str, str, bool]:
    """
    V7.2 status:
      negative -> UNKNOWN + discrepancy
      zero     -> OUT
      positive <= configured reorder level -> LOW
      otherwise -> GOOD
    """
    if available_stock is None:
        return "UNKNOWN", "⚪ Unknown", False

    stock = (
        available_stock
        if isinstance(available_stock, Decimal)
        else Decimal(str(available_stock))
    )

    if stock < 0:
        return "UNKNOWN", "⚪ Unknown", True

    if stock == 0:
        return "OUT", "🔴 Out", False

    reorder = (
        reorder_level
        if isinstance(reorder_level, Decimal)
        else Decimal(str(reorder_level or 0))
    )

    if reorder > 0 and stock <= reorder:
        return "LOW", "🟡 Low", False

    return "GOOD", "🟢 Good", False


def _show_marathi_product_name(product_name: str, product_name_mr: str | None) -> bool:
    """
    Frozen V7.2 Product Display Exception:
    if the visible Product contains numbers, do not render a Marathi product line.
    """
    if not product_name_mr:
        return False

    return not any(character.isdigit() for character in product_name)


@router.get(
    "/registry/v7.2",
    operation_id="getRegistryV72",
    response_model=RegistryEnvelopeV72,
    summary="Get FarmAI Stock Registry V7.2",
    description=(
        "Returns the authoritative presentation-ready FarmAI Stock Registry V7.2 "
        "using live PostgreSQL inventory. Use this endpoint for today's stock, "
        "current stock, inventory, register, registry and FULL REGISTRY requests. "
        "The response contains all 8 frozen categories and backend-supplied "
        "bilingual display metadata. Do not substitute getCurrentInventory for "
        "FULL REGISTRY rendering."
    ),
)
def get_registry_v72():
    with connection() as conn:
        rows = conn.execute(
            """
            WITH inventory_totals AS (
                SELECT
                    product_code,
                    MAX(unit) AS inventory_unit,
                    SUM(physical_stock) AS physical_stock,
                    SUM(reserved_stock) AS reserved_stock,
                    SUM(available_stock) AS available_stock
                FROM public.current_inventory
                GROUP BY product_code
            )
            SELECT
                p.id AS product_id,
                p.product_code,
                p.product_name,
                p.brand,
                p.category AS database_category,
                p.base_unit,
                p.reorder_level,
                p.minimum_stock,

                COALESCE(
                    pdm.registry_category,
                    CASE p.category
                        WHEN 'Fertilizers'
                            THEN 'Fertilizers'
                        WHEN 'Biostimulants & Growth Promoters'
                            THEN 'Biostimulants & Biofertilizers'
                        WHEN 'Micronutrients'
                            THEN 'Micronutrients'
                        WHEN 'Fungicides'
                            THEN 'Fungicides'
                        WHEN 'Insecticides'
                            THEN 'Insecticides'
                        WHEN 'Herbicides'
                            THEN 'Herbicides'
                        WHEN 'Adjuvants'
                            THEN 'Adjuvants / Stickers'
                        ELSE NULL
                    END
                ) AS registry_category,

                pdm.product_name_mr,
                pdm.used_for_en,
                pdm.used_for_mr,
                pdm.apply_when_en,
                pdm.apply_when_mr,
                pdm.standard_dose,
                pdm.content,
                pdm.farmai_advice_en,
                pdm.farmai_advice_mr,

                COALESCE(it.inventory_unit, p.base_unit) AS stock_unit,
                COALESCE(it.physical_stock, 0) AS physical_stock,
                COALESCE(it.reserved_stock, 0) AS reserved_stock,
                COALESCE(it.available_stock, 0) AS available_stock

            FROM public.products p

            LEFT JOIN inventory_totals it
                ON LOWER(it.product_code) = LOWER(p.product_code)

            LEFT JOIN public.product_display_metadata pdm
                ON pdm.product_id = p.id

            WHERE p.active = TRUE

            ORDER BY
                CASE COALESCE(
                    pdm.registry_category,
                    CASE p.category
                        WHEN 'Fertilizers'
                            THEN 'Fertilizers'
                        WHEN 'Biostimulants & Growth Promoters'
                            THEN 'Biostimulants & Biofertilizers'
                        WHEN 'Micronutrients'
                            THEN 'Micronutrients'
                        WHEN 'Fungicides'
                            THEN 'Fungicides'
                        WHEN 'Insecticides'
                            THEN 'Insecticides'
                        WHEN 'Herbicides'
                            THEN 'Herbicides'
                        WHEN 'Adjuvants'
                            THEN 'Adjuvants / Stickers'
                        ELSE NULL
                    END
                )
                    WHEN 'Fertilizers' THEN 1
                    WHEN 'Biostimulants & Biofertilizers' THEN 2
                    WHEN 'Micronutrients' THEN 3
                    WHEN 'Fungicides' THEN 4
                    WHEN 'Insecticides' THEN 5
                    WHEN 'Herbicides' THEN 6
                    WHEN 'Biopesticides' THEN 7
                    WHEN 'Adjuvants / Stickers' THEN 8
                    ELSE 99
                END,
                p.product_name
            """
        ).fetchall()

    categories: dict[str, dict[str, Any]] = {
        category["name_en"]: {
            **category,
            "products": [],
        }
        for category in CATEGORY_DEFINITIONS
    }

    unmapped_products: list[str] = []

    for row in rows:
        registry_category = row["registry_category"]

        if registry_category not in categories:
            unmapped_products.append(row["product_code"])
            continue

        status_code, status_display, discrepancy = _status(
            row["available_stock"],
            row["reorder_level"],
        )

        show_marathi_name = _show_marathi_product_name(
            row["product_name"],
            row["product_name_mr"],
        )

        product = {
            "product_code": row["product_code"],
            "product_en": row["product_name"],
            "product_mr": row["product_name_mr"] if show_marathi_name else None,
            "show_marathi_name": show_marathi_name,
            "stock_quantity": row["available_stock"],
            "stock_unit": row["stock_unit"],
            "stock_display": _stock_display(
                row["available_stock"],
                row["stock_unit"],
            ),
            "status_code": status_code,
            "status_display": status_display,
            "used_for_en": row["used_for_en"] or "Unknown",
            "used_for_mr": row["used_for_mr"] or "Unknown",
            "apply_when_en": row["apply_when_en"] or "Unknown",
            "apply_when_mr": row["apply_when_mr"] or "Unknown",
            "dose": row["standard_dose"] or "Unknown",
            "content": row["content"] or "Unknown",
            "farmai_advice_en": row["farmai_advice_en"] or "—",
            "farmai_advice_mr": row["farmai_advice_mr"] or "—",
            "inventory_discrepancy": discrepancy,
        }

        categories[registry_category]["products"].append(product)

    data = {
        "registry_version": "7.2",
        "source": (
            "postgresql.current_inventory+products+product_display_metadata"
        ),
        "columns": [
            "Product",
            "Stock",
            "Status",
            "Used For",
            "Apply When",
            "Dose",
            "Content",
            "FarmAI Advice",
        ],
        "categories": [
            categories[category["name_en"]]
            for category in CATEGORY_DEFINITIONS
        ],
    }

    return success_response(
        data,
        meta={
            "category_count": len(CATEGORY_DEFINITIONS),
            "product_count": sum(
                len(category["products"])
                for category in data["categories"]
            ),
            "unmapped_product_count": len(unmapped_products),
            "unmapped_product_codes": unmapped_products,
            "source": data["source"],
        },
    )
