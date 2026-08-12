#!/usr/bin/env bash
set -euo pipefail
BASE_URL="${BASE_URL:-https://farmai-stock-manager-v7-2.vercel.app}"
API_KEY="${FARMAI_API_KEY:?Set FARMAI_API_KEY first}"
curl -i -X POST -H "X-API-Key: ${API_KEY}" -H "Content-Type: application/json" \
-d '{"idempotency_key":"usage-batch-smoke-001","crop":"TEST","plot":"TEST","method":"B2 Smoke Test",
"items":[{"product_code":"REPLACE_WITH_REAL_CODE","quantity":1,"unit":"g","location_code":"MAIN"}]}' \
"${BASE_URL}/api/v1/inventory/issues/batch"
