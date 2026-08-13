# FarmAI V7.2 — Automated B6 Certification

This package automates the backend certification layer for FarmAI Stock Manager V7.2.

## What it tests

- Health
- Required OpenAPI actions
- Product creation
- Duplicate-product rejection
- Invalid category/base-unit rejection
- Product search and lookup
- Single purchase
- Single-write idempotency
- Batch purchase
- Batch purchase retry
- Atomic batch-purchase rejection
- Batch usage
- Batch-usage retry
- Atomic insufficient-stock rejection
- Physical verification
- Transaction history
- Live inventory read

## Install

No third-party Python package is required for the API tests.

Place this directory at:

```text
scripts/b6_certification/
```

## Environment

From repo root:

```bash
export BASE_URL="https://farmai-stock-manager-v7-2.vercel.app"
export FARMAI_API_KEY="YOUR_SECRET_API_KEY"
```

Optional:

```bash
export FARMAI_LOCATION_CODE="MAIN"
export FARMAI_TIMEOUT_SECONDS="30"
```

## Run

```bash
python3 scripts/b6_certification/run_b6.py
```

The run creates:

```text
scripts/b6_certification/b6_state.json
```

which records the certification run ID and generated test product codes.

## Cleanup preview

After certification:

```bash
python3 scripts/b6_certification/cleanup_preview.py
```

This only displays test inventory and transactions. It does NOT mutate data.

Then review:

```text
scripts/b6_certification/cleanup_b6.sql
```

Do not hard-delete stock history. Use reversal transactions and deactivate test products.

## GPT certification

After backend certification passes, follow:

```text
GPT_MANUAL_CERTIFICATION.md
```

Only the GPT routing/orchestration tests remain manual.

## Important

B6 deliberately creates dedicated products named:

```text
B6 CERT ...
```

and idempotency keys beginning with:

```text
b6-
```

This makes certification data easy to identify and safely clean later.
