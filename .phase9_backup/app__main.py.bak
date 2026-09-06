from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query

from .api.v1.health import router as health_router
from .api.v1.activity_register import router as activity_register_router
from .api.v1.inventory import router as inventory_router
from .api.v1.registry import router as registry_router
from .api.v1.products import router as products_router
from .api.v1.transactions import router as transactions_router
from .api.v1.batch_purchases import router as batch_purchases_router
from .api.v1.batch_usage import router as batch_usage_router
from .api.v1.create_product import router as create_product_router
from .api.v1.activity_import import router as activity_import_router
from .api.v1.activity_intelligence import router as activity_intelligence_router
from .api.v1.activity_proactive_planner import router as activity_proactive_planner_router
from .api.v1.weather_intelligence import router as weather_intelligence_router
from .db import connection
from .models import (
    AvailabilityRequest,
    BulkOpeningBalanceRequest,
    ReleaseRequest,
    ReservationRequest,
    TransactionRequest,
)
from .quantity import QuantityNormalizationError, canonical_unit, normalize_quantity
from .security import require_api_key

VERSION = "7.2.3"

app = FastAPI(
    title="FarmAI Stock Manager API",
    version=VERSION,
    servers=[
        {
            "url": "https://farmai-stock-manager-v7-2.vercel.app",
            "description": "FarmAI Stock Manager API",
        }
    ],
)

# Agent-facing API v1: these are intentionally exposed in OpenAPI.
app.include_router(health_router)
app.include_router(activity_register_router)
app.include_router(inventory_router)
app.include_router(registry_router)
app.include_router(products_router)
app.include_router(transactions_router)
app.include_router(batch_purchases_router)
app.include_router(batch_usage_router)
app.include_router(create_product_router)

app.include_router(activity_import_router)
app.include_router(activity_intelligence_router)
app.include_router(activity_proactive_planner_router)
app.include_router(weather_intelligence_router)
def d(value):
    return Decimal(str(value or 0))


def txn_no():
    return f"TXN-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid4().hex[:8].upper()}"


def product(conn, code):
    row = conn.execute(
        "select * from products where lower(product_code)=lower(%s) and active=true",
        (code,),
    ).fetchone()
    if not row:
        raise HTTPException(
            404,
            detail={"code": "PRODUCT_NOT_FOUND", "message": "Product not found."},
        )
    return row


def location(conn, code):
    row = conn.execute(
        "select * from stock_locations where lower(location_code)=lower(%s) and active=true",
        (code,),
    ).fetchone()
    if not row:
        raise HTTPException(
            404,
            detail={"code": "LOCATION_NOT_FOUND", "message": "Location not found."},
        )
    return row


def available(conn, product_id, location_id):
    stock = conn.execute(
        """select coalesce(sum(quantity_in-quantity_out),0) qty
           from stock_transactions
           where product_id=%s and location_id=%s and status='CONFIRMED'""",
        (product_id, location_id),
    ).fetchone()["qty"]
    reserved = conn.execute(
        """select coalesce(sum(quantity_reserved-quantity_consumed-quantity_released),0) qty
           from stock_reservations
           where product_id=%s and location_id=%s and status='ACTIVE'""",
        (product_id, location_id),
    ).fetchone()["qty"]
    return d(stock) - d(reserved)


def normalized_or_422(quantity, submitted_unit, base_unit):
    try:
        return normalize_quantity(quantity, submitted_unit, base_unit)
    except QuantityNormalizationError as exc:
        raise HTTPException(
            422,
            detail={
                "code": "INVALID_UNIT_CONVERSION",
                "message": str(exc),
                "submitted_unit": submitted_unit,
                "base_unit": base_unit,
            },
        ) from exc


@app.get("/", include_in_schema=False)
def root():
    return {"ok": True, "service": "FarmAI Stock Manager", "version": VERSION}


# ---------------------------------------------------------------------------
# Legacy V7.2.2 routes.
# They remain operational for backward compatibility, but are intentionally
# hidden from OpenAPI so the Stock Agent sees only /api/v1 operations.
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    dependencies=[Depends(require_api_key)],
    include_in_schema=False,
)
def health():
    with connection() as conn:
        conn.execute("select 1")
    return {"ok": True, "data": {"version": VERSION, "status": "ok"}}


@app.get(
    "/products/search",
    dependencies=[Depends(require_api_key)],
    include_in_schema=False,
)
def search_products(q: str = Query(min_length=1)):
    with connection() as conn:
        pattern = f"%{q}%"
        rows = conn.execute(
            """select p.*, coalesce(json_agg(ai.active_ingredient)
               filter(where ai.active_ingredient is not null),'[]') active_ingredients
               from products p
               left join product_active_ingredients ai on ai.product_id=p.id
               where p.active=true and (
                 p.product_name ilike %s or p.product_code ilike %s
                 or coalesce(p.brand,'') ilike %s
                 or exists(select 1 from product_active_ingredients x
                    where x.product_id=p.id and x.active_ingredient ilike %s)
               )
               group by p.id order by p.product_name limit 30""",
            (pattern, pattern, pattern, pattern),
        ).fetchall()
    return {"ok": True, "data": rows}


@app.get(
    "/inventory",
    dependencies=[Depends(require_api_key)],
    include_in_schema=False,
)
def inventory():
    with connection() as conn:
        rows = conn.execute(
            "select * from current_inventory order by category, product_name, location_code"
        ).fetchall()
    return {"ok": True, "data": rows}


@app.post(
    "/inventory/availability",
    dependencies=[Depends(require_api_key)],
    include_in_schema=False,
)
def availability(req: AvailabilityRequest):
    with connection() as conn:
        p = product(conn, req.product_code)
        required = normalized_or_422(req.required_quantity, req.unit, p["base_unit"])
        rows = conn.execute("select * from stock_locations where active=true").fetchall()
        total = Decimal("0")
        locations = []
        for loc in rows:
            qty = available(conn, p["id"], loc["id"])
            total += qty
            locations.append({"location_code": loc["location_code"], "available": qty})
        status = "AVAILABLE" if total >= required else ("PARTIAL" if total > 0 else "UNAVAILABLE")
        batches = conn.execute(
            "select * from current_batch_availability where product_id=%s order by expiry_date nulls last",
            (p["id"],),
        ).fetchall()
    return {
        "ok": True,
        "data": {
            "product_code": p["product_code"],
            "product_name": p["product_name"],
            "submitted_quantity": req.required_quantity,
            "submitted_unit": canonical_unit(req.unit),
            "required_quantity": required,
            "available_quantity": total,
            "unit": p["base_unit"],
            "sufficiency": status,
            "locations": locations,
            "batches": batches,
        },
    }


@app.post(
    "/inventory/transactions",
    dependencies=[Depends(require_api_key)],
    include_in_schema=False,
)
def transact(req: TransactionRequest):
    with connection() as conn:
        try:
            duplicate = conn.execute(
                "select * from stock_transactions where idempotency_key=%s",
                (req.idempotency_key,),
            ).fetchone()
            if duplicate:
                return {"ok": True, "data": {"duplicate": True, "transaction": duplicate}}

            if req.action == "reverseTransaction":
                original = conn.execute(
                    "select * from stock_transactions where id=%s for update",
                    (req.transaction_id,),
                ).fetchone()
                if not original:
                    raise HTTPException(
                        404,
                        detail={"code": "TRANSACTION_NOT_FOUND", "message": "Transaction not found."},
                    )
                transaction = conn.execute(
                    """insert into stock_transactions(
                       transaction_no,transaction_type,product_id,location_id,batch_id,
                       quantity_in,quantity_out,unit,notes,idempotency_key,reversal_of)
                       values(%s,'REVERSAL',%s,%s,%s,%s,%s,%s,%s,%s,%s) returning *""",
                    (
                        txn_no(), original["product_id"], original["location_id"],
                        original["batch_id"], original["quantity_out"], original["quantity_in"],
                        original["unit"], req.notes, req.idempotency_key, original["id"],
                    ),
                ).fetchone()
                conn.commit()
                return {"ok": True, "data": {"duplicate": False, "transaction": transaction}}

            p = product(conn, req.product_code)
            loc = location(conn, req.location_code)
            source_unit = req.unit or p["base_unit"]

            normalized_quantity = (
                normalized_or_422(req.quantity, source_unit, p["base_unit"])
                if req.quantity is not None else None
            )
            normalized_verified_quantity = (
                normalized_or_422(req.verified_quantity, source_unit, p["base_unit"])
                if req.verified_quantity is not None else None
            )

            conn.execute("select id from products where id=%s for update", (p["id"],))
            incoming_actions = {
                "recordOpeningBalance": "OPENING_BALANCE",
                "recordPurchase": "PURCHASE",
            }
            outgoing_actions = {
                "recordUsage": "USAGE",
                "recordDamage": "DAMAGE",
                "recordExpiryDisposal": "EXPIRY_DISPOSAL",
            }

            if req.action == "recordVerification":
                current = available(conn, p["id"], loc["id"])
                variance = normalized_verified_quantity - current
                if variance == 0:
                    conn.commit()
                    return {
                        "ok": True,
                        "data": {
                            "duplicate": False,
                            "adjustment": None,
                            "variance": Decimal("0.000"),
                            "unit": p["base_unit"],
                        },
                    }
                tx_type = "VERIFICATION_ADJUSTMENT"
                qty_in = variance if variance > 0 else Decimal("0")
                qty_out = abs(variance) if variance < 0 else Decimal("0")
            elif req.action in incoming_actions:
                tx_type = incoming_actions[req.action]
                qty_in, qty_out = normalized_quantity, Decimal("0")
            else:
                tx_type = outgoing_actions[req.action]
                qty_in, qty_out = Decimal("0"), normalized_quantity
                if qty_out > available(conn, p["id"], loc["id"]):
                    raise HTTPException(
                        409,
                        detail={
                            "code": "INSUFFICIENT_STOCK",
                            "message": "Insufficient unreserved stock.",
                        },
                    )

            batch_id = None
            if req.batch_number:
                batch_id = conn.execute(
                    """insert into stock_batches(product_id,location_id,batch_number,expiry_date)
                       values(%s,%s,%s,%s)
                       on conflict(product_id,location_id,batch_number)
                       do update set expiry_date=coalesce(excluded.expiry_date,stock_batches.expiry_date)
                       returning id""",
                    (p["id"], loc["id"], req.batch_number, req.expiry_date),
                ).fetchone()["id"]

            transaction = conn.execute(
                """insert into stock_transactions(
                   transaction_no,transaction_type,product_id,location_id,batch_id,
                   quantity_in,quantity_out,unit,effective_at,notes,idempotency_key,
                   external_task_id,external_activity_id)
                   values(%s,%s,%s,%s,%s,%s,%s,%s,coalesce(%s,now()),%s,%s,%s,%s)
                   returning *""",
                (
                    txn_no(), tx_type, p["id"], loc["id"], batch_id, qty_in, qty_out,
                    p["base_unit"], req.effective_at, req.notes, req.idempotency_key,
                    req.external_task_id, req.external_activity_id,
                ),
            ).fetchone()
            conn.commit()
            return {
                "ok": True,
                "data": {
                    "duplicate": False,
                    "submitted_quantity": (
                        req.verified_quantity
                        if req.action == "recordVerification"
                        else req.quantity
                    ),
                    "submitted_unit": canonical_unit(source_unit),
                    "normalized_quantity": (
                        normalized_verified_quantity
                        if req.action == "recordVerification"
                        else normalized_quantity
                    ),
                    "normalized_unit": p["base_unit"],
                    "transaction": transaction,
                },
            }
        except Exception:
            conn.rollback()
            raise


@app.post(
    "/inventory/import-opening-balances",
    dependencies=[Depends(require_api_key)],
    include_in_schema=False,
)
def import_opening_balances(req: BulkOpeningBalanceRequest):
    """Import an opening-stock snapshot with validation, normalization and idempotency."""
    with connection() as conn:
        try:
            prepared = []
            duplicates = []
            errors = []

            for index, item in enumerate(req.opening_balances):
                existing_tx = conn.execute(
                    "select * from stock_transactions where idempotency_key=%s",
                    (item.idempotency_key,),
                ).fetchone()
                if existing_tx:
                    duplicates.append({
                        "index": index,
                        "product_code": item.product_code,
                        "idempotency_key": item.idempotency_key,
                        "transaction_id": existing_tx["id"],
                        "status": "DUPLICATE",
                    })
                    continue

                p = conn.execute(
                    "select * from products where lower(product_code)=lower(%s) and active=true",
                    (item.product_code,),
                ).fetchone()
                if not p:
                    errors.append({
                        "index": index,
                        "product_code": item.product_code,
                        "code": "PRODUCT_NOT_FOUND",
                        "message": "Product not found.",
                    })
                    continue

                loc = conn.execute(
                    "select * from stock_locations where lower(location_code)=lower(%s) and active=true",
                    (item.location_code,),
                ).fetchone()
                if not loc:
                    errors.append({
                        "index": index,
                        "product_code": item.product_code,
                        "code": "LOCATION_NOT_FOUND",
                        "message": "Location not found.",
                    })
                    continue

                try:
                    normalized_quantity = normalize_quantity(
                        item.quantity,
                        item.unit,
                        p["base_unit"],
                    )
                except QuantityNormalizationError as exc:
                    errors.append({
                        "index": index,
                        "product_code": item.product_code,
                        "code": "INVALID_UNIT_CONVERSION",
                        "message": str(exc),
                        "submitted_quantity": item.quantity,
                        "submitted_unit": item.unit,
                        "base_unit": p["base_unit"],
                    })
                    continue

                physical = conn.execute(
                    """select coalesce(sum(quantity_in-quantity_out),0) qty
                       from stock_transactions
                       where product_id=%s and location_id=%s and status='CONFIRMED'""",
                    (p["id"], loc["id"]),
                ).fetchone()["qty"]

                if req.reject_nonzero_existing and normalized_quantity > 0 and d(physical) != 0:
                    errors.append({
                        "index": index,
                        "product_code": item.product_code,
                        "code": "NONZERO_EXISTING_STOCK",
                        "message": (
                            f"Existing physical stock is {physical} {p['base_unit']}. "
                            "Clear/reverse test data or use a verification workflow before importing."
                        ),
                    })
                    continue

                prepared.append({
                    "index": index,
                    "item": item,
                    "product": p,
                    "location": loc,
                    "normalized_quantity": normalized_quantity,
                    "skip_zero": normalized_quantity == 0,
                })

            if errors and req.atomic:
                raise HTTPException(
                    422,
                    detail={
                        "code": "IMPORT_VALIDATION_FAILED",
                        "message": "No rows were imported because atomic validation failed.",
                        "errors": errors,
                        "duplicate_count": len(duplicates),
                    },
                )

            imported = []
            skipped_zero = []

            for entry in prepared:
                index = entry["index"]
                item = entry["item"]
                p = entry["product"]
                loc = entry["location"]
                normalized_quantity = entry["normalized_quantity"]

                if entry["skip_zero"]:
                    skipped_zero.append({
                        "index": index,
                        "product_code": p["product_code"],
                        "submitted_quantity": item.quantity,
                        "submitted_unit": canonical_unit(item.unit),
                        "normalized_quantity": Decimal("0.000"),
                        "normalized_unit": p["base_unit"],
                        "status": "SKIPPED_ZERO",
                        "message": "No stock movement was created; product remains at zero stock.",
                    })
                    continue

                conn.execute(
                    "select id from products where id=%s for update",
                    (p["id"],),
                )

                batch_id = None
                if item.batch_number:
                    batch_id = conn.execute(
                        """insert into stock_batches(product_id,location_id,batch_number,expiry_date)
                           values(%s,%s,%s,%s)
                           on conflict(product_id,location_id,batch_number)
                           do update set expiry_date=coalesce(excluded.expiry_date,stock_batches.expiry_date)
                           returning id""",
                        (p["id"], loc["id"], item.batch_number, item.expiry_date),
                    ).fetchone()["id"]

                tx = conn.execute(
                    """insert into stock_transactions(
                       transaction_no,transaction_type,product_id,location_id,batch_id,
                       quantity_in,quantity_out,unit,effective_at,notes,idempotency_key)
                       values(%s,'OPENING_BALANCE',%s,%s,%s,%s,0,%s,coalesce(%s,now()),%s,%s)
                       returning *""",
                    (
                        txn_no(), p["id"], loc["id"], batch_id, normalized_quantity,
                        p["base_unit"], item.effective_at, item.notes, item.idempotency_key,
                    ),
                ).fetchone()

                imported.append({
                    "index": index,
                    "product_code": p["product_code"],
                    "submitted_quantity": item.quantity,
                    "submitted_unit": canonical_unit(item.unit),
                    "normalized_quantity": normalized_quantity,
                    "normalized_unit": p["base_unit"],
                    "status": "IMPORTED",
                    "transaction_id": tx["id"],
                    "transaction_no": tx["transaction_no"],
                })

            conn.commit()

            return {
                "ok": True,
                "data": {
                    "atomic": req.atomic,
                    "requested": len(req.opening_balances),
                    "imported_count": len(imported),
                    "duplicate_count": len(duplicates),
                    "skipped_zero_count": len(skipped_zero),
                    "failed_count": len(errors),
                    "imported": imported,
                    "duplicates": duplicates,
                    "skipped_zero": skipped_zero,
                    "errors": errors,
                },
            }
        except HTTPException:
            conn.rollback()
            raise
        except Exception:
            conn.rollback()
            raise


@app.post(
    "/inventory/reservations",
    dependencies=[Depends(require_api_key)],
    include_in_schema=False,
)
def reserve(req: ReservationRequest):
    with connection() as conn:
        try:
            duplicate = conn.execute(
                "select * from stock_reservations where idempotency_key=%s",
                (req.idempotency_key,),
            ).fetchone()
            if duplicate:
                return {
                    "ok": True,
                    "data": {
                        "duplicate": True,
                        "reservation": duplicate,
                    },
                }

            p = product(conn, req.product_code)
            loc = location(conn, "MAIN")
            normalized_quantity = normalized_or_422(
                req.quantity,
                req.unit,
                p["base_unit"],
            )

            if normalized_quantity > available(conn, p["id"], loc["id"]):
                raise HTTPException(
                    409,
                    detail={
                        "code": "INSUFFICIENT_STOCK",
                        "message": "Insufficient stock to reserve.",
                    },
                )

            row = conn.execute(
                """insert into stock_reservations(
                   external_task_id,product_id,location_id,quantity_reserved,unit,
                   required_date,status,idempotency_key)
                   values(%s,%s,%s,%s,%s,%s,'ACTIVE',%s) returning *""",
                (
                    req.task_id, p["id"], loc["id"], normalized_quantity,
                    p["base_unit"], req.required_date, req.idempotency_key,
                ),
            ).fetchone()

            conn.commit()

            return {
                "ok": True,
                "data": {
                    "duplicate": False,
                    "submitted_quantity": req.quantity,
                    "submitted_unit": canonical_unit(req.unit),
                    "normalized_quantity": normalized_quantity,
                    "normalized_unit": p["base_unit"],
                    "reservation": row,
                },
            }
        except Exception:
            conn.rollback()
            raise


@app.post(
    "/inventory/reservations/release",
    dependencies=[Depends(require_api_key)],
    include_in_schema=False,
)
def release(req: ReleaseRequest):
    with connection() as conn:
        try:
            event = conn.execute(
                "select * from reservation_events where idempotency_key=%s",
                (req.idempotency_key,),
            ).fetchone()
            if event:
                return {
                    "ok": True,
                    "data": {
                        "duplicate": True,
                        "event": event,
                    },
                }

            reservation = conn.execute(
                "select * from stock_reservations where id=%s for update",
                (req.reservation_id,),
            ).fetchone()

            if not reservation:
                raise HTTPException(
                    404,
                    detail={
                        "code": "RESERVATION_NOT_FOUND",
                        "message": "Reservation not found.",
                    },
                )

            conn.execute(
                """update stock_reservations
                   set quantity_released=quantity_reserved,status='RELEASED'
                   where id=%s""",
                (req.reservation_id,),
            )

            event = conn.execute(
                """insert into reservation_events(
                   reservation_id,event_type,idempotency_key)
                   values(%s,'RELEASED',%s) returning *""",
                (req.reservation_id, req.idempotency_key),
            ).fetchone()

            conn.commit()

            return {
                "ok": True,
                "data": {
                    "duplicate": False,
                    "event": event,
                },
            }
        except Exception:
            conn.rollback()
            raise
