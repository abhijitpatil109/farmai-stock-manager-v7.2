#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://farmai-stock-manager-v7-2.vercel.app}"
API_KEY="${FARMAI_API_KEY:?Set FARMAI_API_KEY first}"

curl -i -X POST \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "idempotency_key": "purchase-batch-smoke-001",
    "notes": "B1 batch purchase smoke test",
    "items": [
      {
        "product_code": "FERT-113624",
        "quantity": 10,
        "unit": "g",
        "location_code": "MAIN",
        "notes": "B1 smoke item"
      }
    ]
  }' \
  "${BASE_URL}/api/v1/inventory/purchases/batch"
