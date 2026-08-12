#!/usr/bin/env python3
"""Verify that the production OpenAPI schema exposes B1/B2/B3 actions."""
import json
import sys
import urllib.request

url = sys.argv[1] if len(sys.argv) > 1 else \
    "https://farmai-stock-manager-v7-2.vercel.app/openapi.json"

with urllib.request.urlopen(url) as response:
    schema = json.load(response)

expected = {
    ("/api/v1/inventory/purchases/batch", "post"): "recordBatchStockPurchase",
    ("/api/v1/inventory/issues/batch", "post"): "recordBatchStockUsage",
    ("/api/v1/products", "post"): "createProduct",
}

failed = False
for (path, method), operation_id in expected.items():
    actual = schema.get("paths", {}).get(path, {}).get(method, {}).get("operationId")
    ok = actual == operation_id
    print(f"{'PASS' if ok else 'FAIL'} {method.upper():4} {path} -> {actual}")
    if not ok:
        failed = True

sys.exit(1 if failed else 0)
