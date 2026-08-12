"""
FarmAI Stock Manager V7.2 - B1 Batch Purchase API

POST /api/v1/inventory/purchases/batch

- Atomic: all items succeed or none are committed.
- PostgreSQL remains source of truth.
- One request-level idempotency key.
- Deterministic per-item idempotency keys.
- Normalizes quantities to product base units.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from ...core.responses import error_response, success_response
from ...core.security import require_api_key
from ...db import connection
from ...quantity import QuantityNormalizationError, canonical_unit, normalize_quantity

router = APIRouter(
    prefix="/api/v1",
    tags=["Batch Transactions"],
    dependencies=[Depends(require_api_key)],
)


class BatchPurchaseItem(BaseModel):
    product_code: str = Field(min_length=1, max_length=100)
    quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=20)
    location_code: str = Field(default="MAIN", min_length=1, max_length=50)
    effective_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class BatchPurchaseRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=200)
    items: list[BatchPurchaseItem] = Field(min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_unique_product_location(self):
        seen = set()
        duplicates = []
        for item in self.items:
            key = (item.product_code.strip().lower(), item.location_code.strip().lower())
            if key in seen:
                duplicates.append(item.product_code)
            seen.add(key)
        if duplicates:
            raise ValueError(
                "Duplicate product/location rows are not allowed; merge quantities first: "
                + ", ".join(sorted(set(duplicates)))
            )
        return self


def _batch_no():
    return f"BAT-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid4().hex[:8].upper()}"


def _txn_no():
    return f"TXN-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid4().hex[:8].upper()}"


def _error(status_code, code, message, details=None):
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(
            error_response(code=code, message=message, details=details)
        ),
    )


def _product(conn, code):
    return conn.execute(
        """select id,product_code,product_name,base_unit
           from products
           where lower(product_code)=lower(%s) and active=true""",
        (code.strip(),),
    ).fetchone()


def _location(conn, code):
    return conn.execute(
        """select id,location_code
           from stock_locations
           where lower(location_code)=lower(%s) and active=true""",
        (code.strip(),),
    ).fetchone()


def _inventory(conn, product_code, location_code):
    return conn.execute(
        """select physical_stock,reserved_stock,available_stock,unit
           from current_inventory
           where lower(product_code)=lower(%s)
             and lower(location_code)=lower(%s)""",
        (product_code, location_code),
    ).fetchone()


def _existing_batch(conn, batch_key):
    return conn.execute(
        """select st.id,st.transaction_no,st.transaction_type,st.quantity_in,
                  st.quantity_out,st.unit,st.effective_at,st.status,
                  p.product_code,p.product_name,sl.location_code
           from stock_transactions st
           join products p on p.id=st.product_id
           join stock_locations sl on sl.id=st.location_id
           where st.idempotency_key like %s
           order by st.created_at,st.id""",
        (f"{batch_key}:%",),
    ).fetchall()


@router.post(
    "/inventory/purchases/batch",
    operation_id="recordBatchStockPurchase",
    summary="Record multiple stock purchases atomically",
)
def record_batch_stock_purchase(req: BatchPurchaseRequest):
    with connection() as conn:
        try:
            existing = _existing_batch(conn, req.idempotency_key)
            if existing:
                items = []
                for row in existing:
                    inv = _inventory(conn, row["product_code"], row["location_code"])
                    items.append({
                        "transaction_id": row["id"],
                        "transaction_no": row["transaction_no"],
                        "product_code": row["product_code"],
                        "product_name": row["product_name"],
                        "location_code": row["location_code"],
                        "quantity_in": row["quantity_in"],
                        "unit": row["unit"],
                        "current_physical_stock": inv["physical_stock"] if inv else Decimal("0"),
                        "current_available_stock": inv["available_stock"] if inv else Decimal("0"),
                        "status": row["status"],
                    })
                return success_response(
                    {
                        "duplicate": True,
                        "batch_idempotency_key": req.idempotency_key,
                        "item_count": len(items),
                        "items": items,
                    },
                    meta={"source": "postgresql.stock_transactions"},
                )

            prepared, errors = [], []

            for index, item in enumerate(req.items):
                p = _product(conn, item.product_code)
                if not p:
                    errors.append({
                        "index": index,
                        "product_code": item.product_code,
                        "code": "PRODUCT_NOT_FOUND",
                        "message": f"Product '{item.product_code}' was not found.",
                    })
                    continue

                loc = _location(conn, item.location_code)
                if not loc:
                    errors.append({
                        "index": index,
                        "product_code": p["product_code"],
                        "location_code": item.location_code,
                        "code": "LOCATION_NOT_FOUND",
                        "message": f"Location '{item.location_code}' was not found.",
                    })
                    continue

                try:
                    normalized = normalize_quantity(item.quantity, item.unit, p["base_unit"])
                except QuantityNormalizationError as exc:
                    errors.append({
                        "index": index,
                        "product_code": p["product_code"],
                        "code": "INVALID_UNIT_CONVERSION",
                        "message": str(exc),
                        "submitted_quantity": item.quantity,
                        "submitted_unit": item.unit,
                        "base_unit": p["base_unit"],
                    })
                    continue

                item_key = f"{req.idempotency_key}:{index + 1}"
                conflict = conn.execute(
                    "select id from stock_transactions where idempotency_key=%s",
                    (item_key,),
                ).fetchone()
                if conflict:
                    errors.append({
                        "index": index,
                        "product_code": p["product_code"],
                        "code": "IDEMPOTENCY_CONFLICT",
                        "message": "Deterministic item idempotency key already exists.",
                    })
                    continue

                prepared.append({
                    "index": index,
                    "item": item,
                    "product": p,
                    "location": loc,
                    "normalized": normalized,
                    "item_key": item_key,
                })

            if errors:
                conn.rollback()
                return _error(
                    422,
                    "BATCH_VALIDATION_FAILED",
                    "No purchases were recorded because one or more items failed validation.",
                    {"errors": errors},
                )

            for product_id in sorted({x["product"]["id"] for x in prepared}):
                conn.execute("select id from products where id=%s for update", (product_id,))

            batch_no = _batch_no()
            results = []

            for entry in prepared:
                item = entry["item"]
                p = entry["product"]
                loc = entry["location"]
                normalized = entry["normalized"]

                before = _inventory(conn, p["product_code"], loc["location_code"])
                old_physical = before["physical_stock"] if before else Decimal("0")
                old_available = before["available_stock"] if before else Decimal("0")

                notes = " | ".join(
                    x for x in [req.notes, item.notes, f"Batch: {batch_no}"] if x
                )

                tx = conn.execute(
                    """insert into stock_transactions(
                       transaction_no,transaction_type,product_id,location_id,
                       quantity_in,quantity_out,unit,effective_at,notes,
                       idempotency_key,status)
                       values(%s,'PURCHASE',%s,%s,%s,0,%s,coalesce(%s,now()),%s,%s,'CONFIRMED')
                       returning *""",
                    (
                        _txn_no(), p["id"], loc["id"], normalized, p["base_unit"],
                        item.effective_at, notes, entry["item_key"],
                    ),
                ).fetchone()

                after = _inventory(conn, p["product_code"], loc["location_code"])

                results.append({
                    "index": entry["index"],
                    "transaction_id": tx["id"],
                    "transaction_no": tx["transaction_no"],
                    "product_code": p["product_code"],
                    "product_name": p["product_name"],
                    "location_code": loc["location_code"],
                    "submitted_quantity": item.quantity,
                    "submitted_unit": canonical_unit(item.unit),
                    "normalized_quantity": normalized,
                    "normalized_unit": p["base_unit"],
                    "previous_physical_stock": old_physical,
                    "previous_available_stock": old_available,
                    "new_physical_stock": after["physical_stock"],
                    "new_available_stock": after["available_stock"],
                    "effective_at": tx["effective_at"],
                    "status": tx["status"],
                })

            conn.commit()

            return success_response(
                {
                    "duplicate": False,
                    "batch_no": batch_no,
                    "batch_idempotency_key": req.idempotency_key,
                    "transaction_type": "PURCHASE",
                    "status": "COMPLETED",
                    "item_count": len(results),
                    "items": results,
                },
                meta={"source": "postgresql.stock_transactions"},
            )
        except Exception:
            conn.rollback()
            raise
