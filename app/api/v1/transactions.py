"""
FarmAI Core API v1 - Stock transaction endpoints.

Responsibilities:
    • Record stock purchases.
    • Record stock usage/issues.
    • Record physical verification adjustments.
    • Read transaction history.

All writes:
    • validate product/location,
    • normalize quantity units,
    • preserve idempotency,
    • enforce stock availability,
    • write to the PostgreSQL transaction ledger,
    • return previous and resulting balances.

Opening-balance migration remains outside this operational API.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...core.responses import error_response, success_response
from ...core.security import require_api_key
from ...db import connection
from ...quantity import (
    QuantityNormalizationError,
    canonical_unit,
    normalize_quantity,
)


router = APIRouter(
    prefix="/api/v1",
    tags=["Transactions"],
    dependencies=[Depends(require_api_key)],
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class PurchaseRequest(BaseModel):
    product_code: str = Field(min_length=1, max_length=100)
    quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=20)
    location_code: str = Field(default="MAIN", min_length=1, max_length=50)
    idempotency_key: str = Field(min_length=8, max_length=200)
    effective_at: datetime | None = None
    batch_number: str | None = Field(default=None, max_length=100)
    expiry_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class StockIssueRequest(BaseModel):
    product_code: str = Field(min_length=1, max_length=100)
    quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=20)
    location_code: str = Field(default="MAIN", min_length=1, max_length=50)
    idempotency_key: str = Field(min_length=8, max_length=200)
    effective_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)
    external_task_id: str | None = Field(default=None, max_length=200)
    external_activity_id: str | None = Field(default=None, max_length=200)


class StockAdjustmentRequest(BaseModel):
    product_code: str = Field(min_length=1, max_length=100)
    verified_quantity: Decimal = Field(ge=0)
    unit: str = Field(min_length=1, max_length=20)
    location_code: str = Field(default="MAIN", min_length=1, max_length=50)
    idempotency_key: str = Field(min_length=8, max_length=200)
    effective_at: datetime | None = None
    reason: str = Field(min_length=3, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _transaction_no() -> str:
    return (
        f"TXN-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-"
        f"{uuid4().hex[:8].upper()}"
    )


def _get_product(conn, product_code: str):
    row = conn.execute(
        """
        SELECT *
        FROM products
        WHERE LOWER(product_code) = LOWER(%s)
          AND active = TRUE
        """,
        (product_code.strip(),),
    ).fetchone()

    return row


def _get_location(conn, location_code: str):
    row = conn.execute(
        """
        SELECT *
        FROM stock_locations
        WHERE LOWER(location_code) = LOWER(%s)
          AND active = TRUE
        """,
        (location_code.strip(),),
    ).fetchone()

    return row


def _physical_stock(conn, product_id, location_id) -> Decimal:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(quantity_in - quantity_out), 0) AS qty
        FROM stock_transactions
        WHERE product_id = %s
          AND location_id = %s
          AND status = 'CONFIRMED'
        """,
        (product_id, location_id),
    ).fetchone()

    return _decimal(row["qty"])


def _reserved_stock(conn, product_id, location_id) -> Decimal:
    row = conn.execute(
        """
        SELECT COALESCE(
            SUM(quantity_reserved - quantity_consumed - quantity_released),
            0
        ) AS qty
        FROM stock_reservations
        WHERE product_id = %s
          AND location_id = %s
          AND status = 'ACTIVE'
        """,
        (product_id, location_id),
    ).fetchone()

    return _decimal(row["qty"])


def _available_stock(conn, product_id, location_id) -> Decimal:
    return (
        _physical_stock(conn, product_id, location_id)
        - _reserved_stock(conn, product_id, location_id)
    )


def _normalize_or_error(
    quantity: Decimal,
    submitted_unit: str,
    base_unit: str,
):
    try:
        return normalize_quantity(
            quantity,
            submitted_unit,
            base_unit,
        )
    except QuantityNormalizationError as exc:
        return JSONResponse(
            status_code=422,
            content=error_response(
                code="INVALID_UNIT_CONVERSION",
                message=str(exc),
                details={
                    "submitted_unit": submitted_unit,
                    "base_unit": base_unit,
                },
            ),
        )


def _duplicate_transaction(conn, idempotency_key: str):
    return conn.execute(
        """
        SELECT
            st.*,
            p.product_code,
            p.product_name,
            sl.location_code
        FROM stock_transactions st
        JOIN products p ON p.id = st.product_id
        JOIN stock_locations sl ON sl.id = st.location_id
        WHERE st.idempotency_key = %s
        """,
        (idempotency_key,),
    ).fetchone()


def _transaction_result(
    *,
    transaction,
    product,
    location,
    submitted_quantity,
    submitted_unit,
    normalized_quantity,
    previous_physical,
    previous_available,
    new_physical,
    new_available,
    duplicate: bool,
):
    return {
        "duplicate": duplicate,
        "transaction_id": transaction["id"],
        "transaction_no": transaction["transaction_no"],
        "transaction_type": transaction["transaction_type"],
        "product_code": product["product_code"],
        "product_name": product["product_name"],
        "location_code": location["location_code"],
        "submitted_quantity": submitted_quantity,
        "submitted_unit": canonical_unit(submitted_unit),
        "normalized_quantity": normalized_quantity,
        "normalized_unit": product["base_unit"],
        "previous_physical_stock": previous_physical,
        "previous_available_stock": previous_available,
        "new_physical_stock": new_physical,
        "new_available_stock": new_available,
        "effective_at": transaction["effective_at"],
        "status": transaction["status"],
    }


# ---------------------------------------------------------------------------
# Purchase
# ---------------------------------------------------------------------------

@router.post(
    "/inventory/purchases",
    operation_id="recordStockPurchase",
    summary="Record a stock purchase",
    description=(
        "Adds purchased stock to the FarmAI transaction ledger. "
        "Quantity is normalized to the product base unit and duplicate "
        "requests are protected by idempotency_key."
    ),
)
def record_stock_purchase(req: PurchaseRequest):
    with connection() as conn:
        try:
            duplicate = _duplicate_transaction(conn, req.idempotency_key)
            if duplicate:
                product = _get_product(conn, duplicate["product_code"])
                location = _get_location(conn, duplicate["location_code"])

                physical = _physical_stock(
                    conn,
                    product["id"],
                    location["id"],
                )
                available = _available_stock(
                    conn,
                    product["id"],
                    location["id"],
                )

                return success_response(
                    {
                        "duplicate": True,
                        "transaction_id": duplicate["id"],
                        "transaction_no": duplicate["transaction_no"],
                        "transaction_type": duplicate["transaction_type"],
                        "product_code": duplicate["product_code"],
                        "product_name": duplicate["product_name"],
                        "location_code": duplicate["location_code"],
                        "current_physical_stock": physical,
                        "current_available_stock": available,
                        "unit": duplicate["unit"],
                        "status": duplicate["status"],
                    },
                    meta={"source": "postgresql.stock_transactions"},
                )

            product = _get_product(conn, req.product_code)
            if not product:
                return JSONResponse(
                    status_code=404,
                    content=error_response(
                        code="PRODUCT_NOT_FOUND",
                        message=f"Product '{req.product_code}' was not found.",
                    ),
                )

            location = _get_location(conn, req.location_code)
            if not location:
                return JSONResponse(
                    status_code=404,
                    content=error_response(
                        code="LOCATION_NOT_FOUND",
                        message=f"Location '{req.location_code}' was not found.",
                    ),
                )

            normalized = _normalize_or_error(
                req.quantity,
                req.unit,
                product["base_unit"],
            )
            if isinstance(normalized, JSONResponse):
                return normalized

            # Serialize concurrent writes for this product.
            conn.execute(
                "SELECT id FROM products WHERE id = %s FOR UPDATE",
                (product["id"],),
            )

            previous_physical = _physical_stock(
                conn,
                product["id"],
                location["id"],
            )
            previous_available = _available_stock(
                conn,
                product["id"],
                location["id"],
            )

            batch_id = None
            if req.batch_number:
                batch_id = conn.execute(
                    """
                    INSERT INTO stock_batches(
                        product_id,
                        location_id,
                        batch_number,
                        expiry_date
                    )
                    VALUES(%s, %s, %s, %s)
                    ON CONFLICT(product_id, location_id, batch_number)
                    DO UPDATE SET
                        expiry_date = COALESCE(
                            EXCLUDED.expiry_date,
                            stock_batches.expiry_date
                        )
                    RETURNING id
                    """,
                    (
                        product["id"],
                        location["id"],
                        req.batch_number,
                        req.expiry_date,
                    ),
                ).fetchone()["id"]

            transaction = conn.execute(
                """
                INSERT INTO stock_transactions(
                    transaction_no,
                    transaction_type,
                    product_id,
                    location_id,
                    batch_id,
                    quantity_in,
                    quantity_out,
                    unit,
                    effective_at,
                    notes,
                    idempotency_key
                )
                VALUES(
                    %s,
                    'PURCHASE',
                    %s,
                    %s,
                    %s,
                    %s,
                    0,
                    %s,
                    COALESCE(%s, NOW()),
                    %s,
                    %s
                )
                RETURNING *
                """,
                (
                    _transaction_no(),
                    product["id"],
                    location["id"],
                    batch_id,
                    normalized,
                    product["base_unit"],
                    req.effective_at,
                    req.notes,
                    req.idempotency_key,
                ),
            ).fetchone()

            new_physical = previous_physical + normalized
            new_available = previous_available + normalized

            conn.commit()

            return success_response(
                _transaction_result(
                    transaction=transaction,
                    product=product,
                    location=location,
                    submitted_quantity=req.quantity,
                    submitted_unit=req.unit,
                    normalized_quantity=normalized,
                    previous_physical=previous_physical,
                    previous_available=previous_available,
                    new_physical=new_physical,
                    new_available=new_available,
                    duplicate=False,
                ),
                meta={"source": "postgresql.stock_transactions"},
            )

        except Exception:
            conn.rollback()
            raise


# ---------------------------------------------------------------------------
# Stock issue / usage
# ---------------------------------------------------------------------------

@router.post(
    "/inventory/issues",
    operation_id="recordStockUsage",
    summary="Record stock usage",
    description=(
        "Deducts stock used for a farm operation. The backend validates "
        "available unreserved stock before writing the usage transaction."
    ),
)
def record_stock_usage(req: StockIssueRequest):
    with connection() as conn:
        try:
            duplicate = _duplicate_transaction(conn, req.idempotency_key)
            if duplicate:
                return success_response(
                    {
                        "duplicate": True,
                        "transaction_id": duplicate["id"],
                        "transaction_no": duplicate["transaction_no"],
                        "transaction_type": duplicate["transaction_type"],
                        "product_code": duplicate["product_code"],
                        "product_name": duplicate["product_name"],
                        "location_code": duplicate["location_code"],
                        "unit": duplicate["unit"],
                        "status": duplicate["status"],
                    },
                    meta={"source": "postgresql.stock_transactions"},
                )

            product = _get_product(conn, req.product_code)
            if not product:
                return JSONResponse(
                    status_code=404,
                    content=error_response(
                        code="PRODUCT_NOT_FOUND",
                        message=f"Product '{req.product_code}' was not found.",
                    ),
                )

            location = _get_location(conn, req.location_code)
            if not location:
                return JSONResponse(
                    status_code=404,
                    content=error_response(
                        code="LOCATION_NOT_FOUND",
                        message=f"Location '{req.location_code}' was not found.",
                    ),
                )

            normalized = _normalize_or_error(
                req.quantity,
                req.unit,
                product["base_unit"],
            )
            if isinstance(normalized, JSONResponse):
                return normalized

            conn.execute(
                "SELECT id FROM products WHERE id = %s FOR UPDATE",
                (product["id"],),
            )

            previous_physical = _physical_stock(
                conn,
                product["id"],
                location["id"],
            )
            previous_available = _available_stock(
                conn,
                product["id"],
                location["id"],
            )

            if normalized > previous_available:
                return JSONResponse(
                    status_code=409,
                    content=error_response(
                        code="INSUFFICIENT_STOCK",
                        message="Insufficient unreserved stock.",
                        details={
                            "product_code": product["product_code"],
                            "requested_quantity": normalized,
                            "available_quantity": previous_available,
                            "unit": product["base_unit"],
                        },
                    ),
                )

            transaction = conn.execute(
                """
                INSERT INTO stock_transactions(
                    transaction_no,
                    transaction_type,
                    product_id,
                    location_id,
                    quantity_in,
                    quantity_out,
                    unit,
                    effective_at,
                    notes,
                    idempotency_key,
                    external_task_id,
                    external_activity_id
                )
                VALUES(
                    %s,
                    'USAGE',
                    %s,
                    %s,
                    0,
                    %s,
                    %s,
                    COALESCE(%s, NOW()),
                    %s,
                    %s,
                    %s,
                    %s
                )
                RETURNING *
                """,
                (
                    _transaction_no(),
                    product["id"],
                    location["id"],
                    normalized,
                    product["base_unit"],
                    req.effective_at,
                    req.notes,
                    req.idempotency_key,
                    req.external_task_id,
                    req.external_activity_id,
                ),
            ).fetchone()

            new_physical = previous_physical - normalized
            new_available = previous_available - normalized

            conn.commit()

            return success_response(
                _transaction_result(
                    transaction=transaction,
                    product=product,
                    location=location,
                    submitted_quantity=req.quantity,
                    submitted_unit=req.unit,
                    normalized_quantity=normalized,
                    previous_physical=previous_physical,
                    previous_available=previous_available,
                    new_physical=new_physical,
                    new_available=new_available,
                    duplicate=False,
                ),
                meta={"source": "postgresql.stock_transactions"},
            )

        except Exception:
            conn.rollback()
            raise


# ---------------------------------------------------------------------------
# Physical verification / adjustment
# ---------------------------------------------------------------------------

@router.post(
    "/inventory/adjustments",
    operation_id="recordStockAdjustment",
    summary="Record a physical stock adjustment",
    description=(
        "Sets the physical stock to a verified quantity by recording only "
        "the variance as a VERIFICATION_ADJUSTMENT transaction."
    ),
)
def record_stock_adjustment(req: StockAdjustmentRequest):
    with connection() as conn:
        try:
            duplicate = _duplicate_transaction(conn, req.idempotency_key)
            if duplicate:
                return success_response(
                    {
                        "duplicate": True,
                        "transaction_id": duplicate["id"],
                        "transaction_no": duplicate["transaction_no"],
                        "transaction_type": duplicate["transaction_type"],
                        "product_code": duplicate["product_code"],
                        "product_name": duplicate["product_name"],
                        "location_code": duplicate["location_code"],
                        "unit": duplicate["unit"],
                        "status": duplicate["status"],
                    },
                    meta={"source": "postgresql.stock_transactions"},
                )

            product = _get_product(conn, req.product_code)
            if not product:
                return JSONResponse(
                    status_code=404,
                    content=error_response(
                        code="PRODUCT_NOT_FOUND",
                        message=f"Product '{req.product_code}' was not found.",
                    ),
                )

            location = _get_location(conn, req.location_code)
            if not location:
                return JSONResponse(
                    status_code=404,
                    content=error_response(
                        code="LOCATION_NOT_FOUND",
                        message=f"Location '{req.location_code}' was not found.",
                    ),
                )

            verified = _normalize_or_error(
                req.verified_quantity,
                req.unit,
                product["base_unit"],
            )
            if isinstance(verified, JSONResponse):
                return verified

            conn.execute(
                "SELECT id FROM products WHERE id = %s FOR UPDATE",
                (product["id"],),
            )

            previous_physical = _physical_stock(
                conn,
                product["id"],
                location["id"],
            )
            previous_reserved = _reserved_stock(
                conn,
                product["id"],
                location["id"],
            )
            previous_available = previous_physical - previous_reserved

            variance = verified - previous_physical

            if variance == 0:
                conn.commit()
                return success_response(
                    {
                        "duplicate": False,
                        "transaction_id": None,
                        "transaction_no": None,
                        "transaction_type": "VERIFICATION_ADJUSTMENT",
                        "product_code": product["product_code"],
                        "product_name": product["product_name"],
                        "location_code": location["location_code"],
                        "submitted_quantity": req.verified_quantity,
                        "submitted_unit": canonical_unit(req.unit),
                        "normalized_quantity": verified,
                        "normalized_unit": product["base_unit"],
                        "variance": Decimal("0.000"),
                        "previous_physical_stock": previous_physical,
                        "new_physical_stock": previous_physical,
                        "previous_available_stock": previous_available,
                        "new_available_stock": previous_available,
                        "reason": req.reason,
                        "status": "NO_CHANGE",
                    },
                    meta={"source": "postgresql.stock_transactions"},
                )

            quantity_in = variance if variance > 0 else Decimal("0")
            quantity_out = abs(variance) if variance < 0 else Decimal("0")

            combined_notes = f"Reason: {req.reason}"
            if req.notes:
                combined_notes += f" | {req.notes}"

            transaction = conn.execute(
                """
                INSERT INTO stock_transactions(
                    transaction_no,
                    transaction_type,
                    product_id,
                    location_id,
                    quantity_in,
                    quantity_out,
                    unit,
                    effective_at,
                    notes,
                    idempotency_key
                )
                VALUES(
                    %s,
                    'VERIFICATION_ADJUSTMENT',
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    COALESCE(%s, NOW()),
                    %s,
                    %s
                )
                RETURNING *
                """,
                (
                    _transaction_no(),
                    product["id"],
                    location["id"],
                    quantity_in,
                    quantity_out,
                    product["base_unit"],
                    req.effective_at,
                    combined_notes,
                    req.idempotency_key,
                ),
            ).fetchone()

            new_physical = verified
            new_available = verified - previous_reserved

            conn.commit()

            return success_response(
                {
                    "duplicate": False,
                    "transaction_id": transaction["id"],
                    "transaction_no": transaction["transaction_no"],
                    "transaction_type": transaction["transaction_type"],
                    "product_code": product["product_code"],
                    "product_name": product["product_name"],
                    "location_code": location["location_code"],
                    "submitted_quantity": req.verified_quantity,
                    "submitted_unit": canonical_unit(req.unit),
                    "normalized_quantity": verified,
                    "normalized_unit": product["base_unit"],
                    "variance": variance,
                    "previous_physical_stock": previous_physical,
                    "new_physical_stock": new_physical,
                    "previous_available_stock": previous_available,
                    "new_available_stock": new_available,
                    "reason": req.reason,
                    "effective_at": transaction["effective_at"],
                    "status": transaction["status"],
                },
                meta={"source": "postgresql.stock_transactions"},
            )

        except Exception:
            conn.rollback()
            raise


# ---------------------------------------------------------------------------
# Transaction history
# ---------------------------------------------------------------------------

@router.get(
    "/inventory/transactions",
    operation_id="getStockTransactions",
    summary="Get stock transaction history",
    description=(
        "Returns recent stock-ledger transactions with optional filtering "
        "by product code and transaction type."
    ),
)
def get_stock_transactions(
    product_code: str | None = Query(default=None, max_length=100),
    transaction_type: Literal[
        "OPENING_BALANCE",
        "PURCHASE",
        "USAGE",
        "DAMAGE",
        "EXPIRY_DISPOSAL",
        "VERIFICATION_ADJUSTMENT",
        "REVERSAL",
    ] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    where = ["1=1"]
    params: list[object] = []

    if product_code:
        where.append("LOWER(p.product_code) = LOWER(%s)")
        params.append(product_code.strip())

    if transaction_type:
        where.append("st.transaction_type = %s")
        params.append(transaction_type)

    params.append(limit)

    query = f"""
        SELECT
            st.id,
            st.transaction_no,
            st.transaction_type,
            p.product_code,
            p.product_name,
            sl.location_code,
            st.quantity_in,
            st.quantity_out,
            st.unit,
            st.effective_at,
            st.notes,
            st.idempotency_key,
            st.external_task_id,
            st.external_activity_id,
            st.reversal_of,
            st.status,
            st.created_at
        FROM stock_transactions st
        JOIN products p ON p.id = st.product_id
        JOIN stock_locations sl ON sl.id = st.location_id
        WHERE {' AND '.join(where)}
        ORDER BY st.effective_at DESC, st.created_at DESC
        LIMIT %s
    """

    with connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    return success_response(
        rows,
        meta={
            "record_count": len(rows),
            "limit": limit,
            "product_code": product_code,
            "transaction_type": transaction_type,
            "source": "postgresql.stock_transactions",
        },
    )