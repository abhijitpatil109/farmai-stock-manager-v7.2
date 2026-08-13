from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from client import FarmAIClient
from config import Config
from report import CertificationReport


def _run_id():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{stamp}-{uuid4().hex[:6].upper()}"


def _contains_operation(schema: dict, path: str, method: str, op_id: str) -> bool:
    return (
        schema.get("paths", {})
        .get(path, {})
        .get(method, {})
        .get("operationId")
        == op_id
    )


def _extract_product_code(body):
    data = FarmAIClient.data(body)
    if isinstance(data, dict):
        if data.get("product_code"):
            return data["product_code"]
        product = data.get("product")
        if isinstance(product, dict):
            return product.get("product_code")
    return None


def _extract_inventory(body):
    data = FarmAIClient.data(body)
    if isinstance(data, list):
        return data[0] if data else {}
    if isinstance(data, dict):
        if isinstance(data.get("items"), list):
            return data["items"][0] if data["items"] else {}
        return data
    return {}


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def run_all(config: Config, report: CertificationReport) -> dict:
    client = FarmAIClient(config)
    run = _run_id()

    state = {
        "run_id": run,
        "idempotency_prefix": f"b6-{run}".lower(),
        "products": [],
        "transactions": [],
    }

    # ---------------------------------------------------------
    # B6.1 Health
    # ---------------------------------------------------------
    r = client.get("/api/v1/health")
    report.add(
        "B6.1 Health endpoint",
        r.status == 200,
        f"HTTP {r.status}",
    )
    if r.status != 200:
        return state

    # ---------------------------------------------------------
    # B6.1 OpenAPI
    # ---------------------------------------------------------
    r = client.get("/openapi.json")
    schema = r.body if isinstance(r.body, dict) else {}
    expected = {
        ("/api/v1/health", "get"): "healthCheck",
        ("/api/v1/inventory", "get"): "getCurrentInventory",
        ("/api/v1/products/search", "get"): "searchProducts",
        ("/api/v1/products/{product_code}", "get"): "getProduct",
        ("/api/v1/products", "post"): "createProduct",
        ("/api/v1/inventory/purchases", "post"): "recordStockPurchase",
        ("/api/v1/inventory/issues", "post"): "recordStockUsage",
        ("/api/v1/inventory/adjustments", "post"): "recordStockAdjustment",
        ("/api/v1/inventory/purchases/batch", "post"): "recordBatchStockPurchase",
        ("/api/v1/inventory/issues/batch", "post"): "recordBatchStockUsage",
        ("/api/v1/transactions", "get"): "getStockTransactions",
    }
    openapi_ok = r.status == 200 and all(
        _contains_operation(schema, p, m, op)
        for (p, m), op in expected.items()
    )
    report.add(
        "B6.1 Required OpenAPI operations",
        openapi_ok,
        f"{len(expected)} operations checked",
    )

    # ---------------------------------------------------------
    # B6.2 Product validation
    # ---------------------------------------------------------
    bad_category = client.post(
        "/api/v1/products",
        {
            "product_name": f"B6 CERT Invalid Category {run}",
            "category": "NOT_A_CATEGORY",
            "base_unit": "kg",
        },
    )
    report.add(
        "B6.2 Invalid category rejected",
        bad_category.status == 422,
        f"HTTP {bad_category.status}",
    )

    bad_unit = client.post(
        "/api/v1/products",
        {
            "product_name": f"B6 CERT Invalid Unit {run}",
            "category": "Fertilizers",
            "base_unit": "bags",
        },
    )
    report.add(
        "B6.2 Invalid base unit rejected",
        bad_unit.status == 422,
        f"HTTP {bad_unit.status}",
    )

    # Create two safe certification products.
    created_codes = []
    for suffix in ("A", "B"):
        name = f"B6 CERT Fertilizer {suffix} {run}"
        create = client.post(
            "/api/v1/products",
            {
                "product_name": name,
                "category": "Fertilizers",
                "base_unit": "kg",
                "brand": "FarmAI B6",
                "notes": f"B6 certification run {run}",
            },
        )
        code = _extract_product_code(create.body)
        ok = create.status == 200 and bool(code)
        report.add(
            f"B6.2 Create test product {suffix}",
            ok,
            f"HTTP {create.status}; code={code}",
        )
        if ok:
            created_codes.append(code)
            state["products"].append(
                {"product_code": code, "product_name": name}
            )

    if len(created_codes) < 2:
        return state

    p1, p2 = created_codes

    # Duplicate product should be blocked.
    duplicate = client.post(
        "/api/v1/products",
        {
            "product_name": state["products"][0]["product_name"],
            "category": "Fertilizers",
            "base_unit": "kg",
            "brand": "FarmAI B6",
        },
    )
    report.add(
        "B6.2 Duplicate product rejected",
        duplicate.status == 409,
        f"HTTP {duplicate.status}",
    )

    # Search / lookup.
    search = client.get(
        "/api/v1/products/search",
        {"q": state["products"][0]["product_name"]},
    )
    report.add(
        "B6.2 Product search",
        search.status == 200 and p1.lower() in str(search.body).lower(),
        f"HTTP {search.status}",
    )

    lookup = client.get(f"/api/v1/products/{p1}")
    report.add(
        "B6.2 Product lookup",
        lookup.status == 200 and p1.lower() in str(lookup.body).lower(),
        f"HTTP {lookup.status}",
    )

    # ---------------------------------------------------------
    # B6.3 Single purchase + idempotency
    # ---------------------------------------------------------
    purchase_key = f"b6-{run}-purchase-single".lower()
    purchase_payload = {
        "product_code": p1,
        "quantity": 10,
        "unit": "kg",
        "location_code": config.location_code,
        "idempotency_key": purchase_key,
        "notes": f"B6 single purchase {run}",
    }

    first = client.post("/api/v1/inventory/purchases", purchase_payload)
    report.add(
        "B6.3 Single purchase",
        first.status == 200,
        f"HTTP {first.status}",
    )

    retry = client.post("/api/v1/inventory/purchases", purchase_payload)
    duplicate_text = str(retry.body).lower()
    report.add(
        "B6.3 Single purchase idempotent retry",
        retry.status == 200 and (
            "duplicate" in duplicate_text
            or "already" in duplicate_text
        ),
        f"HTTP {retry.status}",
    )

    inv = client.get(f"/api/v1/inventory/{p1}")
    inv1 = _extract_inventory(inv.body)
    physical_after_single = _number(
        inv1.get("physical_stock")
        or inv1.get("current_physical_stock")
        or inv1.get("physical")
    )
    report.add(
        "B6.3 No duplicate stock addition",
        inv.status == 200
        and physical_after_single is not None
        and abs(physical_after_single - 10.0) < 0.0001,
        f"physical={physical_after_single}",
    )

    # ---------------------------------------------------------
    # B6.4 Batch purchase
    # ---------------------------------------------------------
    batch_purchase_key = f"b6-{run}-purchase-batch".lower()
    batch_purchase_payload = {
        "idempotency_key": batch_purchase_key,
        "notes": f"B6 batch purchase {run}",
        "items": [
            {
                "product_code": p1,
                "quantity": 5,
                "unit": "kg",
                "location_code": config.location_code,
            },
            {
                "product_code": p2,
                "quantity": 20,
                "unit": "kg",
                "location_code": config.location_code,
            },
        ],
    }

    batch_buy = client.post(
        "/api/v1/inventory/purchases/batch",
        batch_purchase_payload,
    )
    report.add(
        "B6.4 Batch purchase",
        batch_buy.status == 200,
        f"HTTP {batch_buy.status}",
    )

    batch_buy_retry = client.post(
        "/api/v1/inventory/purchases/batch",
        batch_purchase_payload,
    )
    report.add(
        "B6.4 Batch purchase duplicate retry",
        batch_buy_retry.status == 200
        and "duplicate" in str(batch_buy_retry.body).lower(),
        f"HTTP {batch_buy_retry.status}",
    )

    # Atomic invalid-product batch purchase.
    invalid_batch_key = f"b6-{run}-purchase-invalid".lower()
    before_invalid = client.get(f"/api/v1/inventory/{p1}")
    before_invalid_inv = _extract_inventory(before_invalid.body)
    before_invalid_qty = _number(
        before_invalid_inv.get("physical_stock")
        or before_invalid_inv.get("current_physical_stock")
    )

    invalid_batch = client.post(
        "/api/v1/inventory/purchases/batch",
        {
            "idempotency_key": invalid_batch_key,
            "items": [
                {
                    "product_code": p1,
                    "quantity": 3,
                    "unit": "kg",
                    "location_code": config.location_code,
                },
                {
                    "product_code": "B6-NOT-A-REAL-PRODUCT",
                    "quantity": 3,
                    "unit": "kg",
                    "location_code": config.location_code,
                },
            ],
        },
    )
    after_invalid = client.get(f"/api/v1/inventory/{p1}")
    after_invalid_inv = _extract_inventory(after_invalid.body)
    after_invalid_qty = _number(
        after_invalid_inv.get("physical_stock")
        or after_invalid_inv.get("current_physical_stock")
    )
    report.add(
        "B6.4 Batch purchase atomic rejection",
        invalid_batch.status == 422
        and before_invalid_qty is not None
        and after_invalid_qty is not None
        and abs(before_invalid_qty - after_invalid_qty) < 0.0001,
        f"HTTP {invalid_batch.status}; before={before_invalid_qty}; after={after_invalid_qty}",
    )

    # ---------------------------------------------------------
    # B6.5 Batch usage
    # ---------------------------------------------------------
    usage_key = f"b6-{run}-usage-batch".lower()
    usage_payload = {
        "idempotency_key": usage_key,
        "crop": "B6 CERT",
        "plot": "B6 CERT",
        "method": "B6 Certification",
        "notes": f"B6 completed activity {run}",
        "items": [
            {
                "product_code": p1,
                "quantity": 2,
                "unit": "kg",
                "location_code": config.location_code,
            },
            {
                "product_code": p2,
                "quantity": 4,
                "unit": "kg",
                "location_code": config.location_code,
            },
        ],
    }

    usage = client.post(
        "/api/v1/inventory/issues/batch",
        usage_payload,
    )
    report.add(
        "B6.5 Batch usage",
        usage.status == 200,
        f"HTTP {usage.status}",
    )

    usage_retry = client.post(
        "/api/v1/inventory/issues/batch",
        usage_payload,
    )
    report.add(
        "B6.5 Batch usage duplicate retry",
        usage_retry.status == 200
        and "duplicate" in str(usage_retry.body).lower(),
        f"HTTP {usage_retry.status}",
    )

    # Insufficient stock must reject the complete batch.
    before_insufficient_1 = _extract_inventory(
        client.get(f"/api/v1/inventory/{p1}").body
    )
    before_insufficient_2 = _extract_inventory(
        client.get(f"/api/v1/inventory/{p2}").body
    )
    b1 = _number(before_insufficient_1.get("physical_stock"))
    b2 = _number(before_insufficient_2.get("physical_stock"))

    insufficient = client.post(
        "/api/v1/inventory/issues/batch",
        {
            "idempotency_key": f"b6-{run}-usage-insufficient".lower(),
            "crop": "B6 CERT",
            "method": "Atomic rejection test",
            "items": [
                {
                    "product_code": p1,
                    "quantity": 1,
                    "unit": "kg",
                    "location_code": config.location_code,
                },
                {
                    "product_code": p2,
                    "quantity": 999999,
                    "unit": "kg",
                    "location_code": config.location_code,
                },
            ],
        },
    )

    after_insufficient_1 = _extract_inventory(
        client.get(f"/api/v1/inventory/{p1}").body
    )
    after_insufficient_2 = _extract_inventory(
        client.get(f"/api/v1/inventory/{p2}").body
    )
    a1 = _number(after_insufficient_1.get("physical_stock"))
    a2 = _number(after_insufficient_2.get("physical_stock"))

    report.add(
        "B6.5 Insufficient-stock batch is atomic",
        insufficient.status == 409
        and b1 is not None
        and b2 is not None
        and a1 is not None
        and a2 is not None
        and abs(b1 - a1) < 0.0001
        and abs(b2 - a2) < 0.0001,
        f"HTTP {insufficient.status}",
    )

    # ---------------------------------------------------------
    # B6.6 Physical verification
    # ---------------------------------------------------------
    current = _extract_inventory(
        client.get(f"/api/v1/inventory/{p1}").body
    )
    current_physical = _number(current.get("physical_stock"))
    if current_physical is not None:
        verified = max(current_physical - 1, 0)
        adjustment_key = f"b6-{run}-verification".lower()
        adjust = client.post(
            "/api/v1/inventory/adjustments",
            {
                "product_code": p1,
                "verified_quantity": verified,
                "unit": "kg",
                "location_code": config.location_code,
                "idempotency_key": adjustment_key,
                "reason": "B6 certification physical verification",
                "notes": f"B6 run {run}",
            },
        )
        report.add(
            "B6.6 Physical verification adjustment",
            adjust.status == 200,
            f"HTTP {adjust.status}",
        )
    else:
        report.add(
            "B6.6 Physical verification adjustment",
            False,
            "Could not read physical stock",
        )

    # ---------------------------------------------------------
    # B6.7 Transaction history
    # ---------------------------------------------------------
    history = client.get(
        "/api/v1/transactions",
        {"product_code": p1, "limit": 50},
    )
    history_text = str(history.body).lower()
    report.add(
        "B6.7 Transaction history available",
        history.status == 200
        and purchase_key.lower() in history_text
        and usage_key.lower() in history_text,
        f"HTTP {history.status}",
    )

    # ---------------------------------------------------------
    # B6.8 Current inventory read
    # ---------------------------------------------------------
    inventory = client.get("/api/v1/inventory")
    inventory_text = str(inventory.body).lower()
    report.add(
        "B6.8 Live inventory includes test products",
        inventory.status == 200
        and p1.lower() in inventory_text
        and p2.lower() in inventory_text,
        f"HTTP {inventory.status}",
    )

    return state
