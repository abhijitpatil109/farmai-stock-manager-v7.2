#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://farmai-stock-manager-v7-2.vercel.app}"
API_KEY="${FARMAI_API_KEY:?Set FARMAI_API_KEY first}"

curl -i -X POST \
  -H "X-API-Key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "product_code": "TEST-B3-001",
    "product_name": "B3 Test Product",
    "category": "Fertilizers",
    "base_unit": "kg",
    "brand": "FarmAI Test",
    "notes": "B3 smoke test - remove after validation"
  }' \
  "${BASE_URL}/api/v1/products"
