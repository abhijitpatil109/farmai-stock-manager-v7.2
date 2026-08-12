#!/usr/bin/env python3
"""
FarmAI B6 API Certification Runner

Usage:
  export FARMAI_API_KEY="..."
  python B6_certification.py

Optional:
  export BASE_URL="https://farmai-stock-manager-v7-2.vercel.app"

IMPORTANT:
- Replace TEST_* product codes with safe real test products before running.
- This script is intentionally conservative and does not auto-delete test data.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from copy import deepcopy

BASE_URL = os.environ.get(
    "BASE_URL",
    "https://farmai-stock-manager-v7-2.vercel.app",
).rstrip("/")
API_KEY = os.environ.get("FARMAI_API_KEY")

if not API_KEY:
    raise SystemExit("FARMAI_API_KEY is required")

HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json",
}

# Replace with safe test product codes available in your environment.
TEST_PURCHASE_CODE_1 = os.environ.get("TEST_PURCHASE_CODE_1", "REPLACE_CODE_1")
TEST_PURCHASE_CODE_2 = os.environ.get("TEST_PURCHASE_CODE_2", "REPLACE_CODE_2")
TEST_USAGE_CODE_1 = os.environ.get("TEST_USAGE_CODE_1", "REPLACE_CODE_1")
TEST_USAGE_CODE_2 = os.environ.get("TEST_USAGE_CODE_2", "REPLACE_CODE_2")


def request(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        headers=HEADERS,
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body}
        return exc.code, parsed


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def show(name, status, detail=""):
    print(f"{'PASS' if status else 'FAIL'} - {name} {detail}")


def test_openapi():
    with urllib.request.urlopen(BASE_URL + "/openapi.json") as resp:
        schema = json.load(resp)
    expected = {
        ("/api/v1/inventory/purchases/batch", "post"): "recordBatchStockPurchase",
        ("/api/v1/inventory/issues/batch", "post"): "recordBatchStockUsage",
        ("/api/v1/products", "post"): "createProduct",
    }
    for (path, method), opid in expected.items():
        actual = schema.get("paths", {}).get(path, {}).get(method, {}).get("operationId")
        assert_true(actual == opid, f"{path} expected {opid}, got {actual}")


def test_batch_purchase_duplicate():
    key = "b6-purchase-duplicate-001"
    payload = {
        "idempotency_key": key,
        "notes": "B6 duplicate purchase test",
        "items": [
            {
                "product_code": TEST_PURCHASE_CODE_1,
                "quantity": 1,
                "unit": "g",
                "location_code": "MAIN",
            }
        ],
    }
    s1, r1 = request("POST", "/api/v1/inventory/purchases/batch", payload)
    assert_true(s1 == 200 and r1.get("ok") is True, f"first purchase failed: {s1} {r1}")

    s2, r2 = request("POST", "/api/v1/inventory/purchases/batch", payload)
    assert_true(s2 == 200 and r2.get("ok") is True, f"retry failed: {s2} {r2}")
    assert_true(r2.get("data", {}).get("duplicate") is True, "duplicate flag not true")


def test_batch_purchase_atomic_invalid_product():
    payload = {
        "idempotency_key": "b6-purchase-atomic-invalid-001",
        "items": [
            {
                "product_code": TEST_PURCHASE_CODE_1,
                "quantity": 1,
                "unit": "g",
                "location_code": "MAIN",
            },
            {
                "product_code": "B6-NOT-A-REAL-PRODUCT",
                "quantity": 1,
                "unit": "g",
                "location_code": "MAIN",
            },
        ],
    }
    status, body = request("POST", "/api/v1/inventory/purchases/batch", payload)
    assert_true(status == 422, f"expected 422, got {status} {body}")


def test_batch_usage_atomic_insufficient():
    payload = {
        "idempotency_key": "b6-usage-insufficient-001",
        "crop": "B6 TEST",
        "method": "B6 Atomicity Test",
        "items": [
            {
                "product_code": TEST_USAGE_CODE_1,
                "quantity": 1,
                "unit": "g",
                "location_code": "MAIN",
            },
            {
                "product_code": TEST_USAGE_CODE_2,
                "quantity": 999999,
                "unit": "kg",
                "location_code": "MAIN",
            },
        ],
    }
    status, body = request("POST", "/api/v1/inventory/issues/batch", payload)
    assert_true(status == 409, f"expected 409, got {status} {body}")


def test_create_product_invalid_category():
    payload = {
        "product_code": "B6-INVALID-CATEGORY-001",
        "product_name": "B6 Invalid Category Product",
        "category": "Not A FarmAI Category",
        "base_unit": "kg",
    }
    status, body = request("POST", "/api/v1/products", payload)
    assert_true(status == 422, f"expected 422, got {status} {body}")


def test_create_product_invalid_unit():
    payload = {
        "product_code": "B6-INVALID-UNIT-001",
        "product_name": "B6 Invalid Unit Product",
        "category": "Fertilizers",
        "base_unit": "bags",
    }
    status, body = request("POST", "/api/v1/products", payload)
    assert_true(status == 422, f"expected 422, got {status} {body}")


TESTS = [
    ("OpenAPI actions", test_openapi),
    ("Batch purchase duplicate", test_batch_purchase_duplicate),
    ("Batch purchase atomic invalid product", test_batch_purchase_atomic_invalid_product),
    ("Batch usage atomic insufficient stock", test_batch_usage_atomic_insufficient),
    ("Create product invalid category", test_create_product_invalid_category),
    ("Create product invalid base unit", test_create_product_invalid_unit),
]

failed = 0
for name, fn in TESTS:
    try:
        fn()
        show(name, True)
    except Exception as exc:
        failed += 1
        show(name, False, f"- {exc}")

print()
print(f"Tests: {len(TESTS)}, Passed: {len(TESTS)-failed}, Failed: {failed}")
sys.exit(1 if failed else 0)
