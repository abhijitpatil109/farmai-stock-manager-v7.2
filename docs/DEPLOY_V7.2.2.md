# Deploy FarmAI Stock Manager V7.2.2

## 1. Branch

Deploy first to `feature/bulk-import`; keep `main` on the last validated production version.

## 2. Upload

Replace repository files with this package. Do not upload local `__pycache__` directories.

## 3. Database

No SQL migration is required for V7.2.2.

## 4. Verify health

```bash
curl -s -H "X-API-Key: YOUR_API_KEY" \
  "YOUR_PREVIEW_URL/health"
```

Expected version: `7.2.2`.

## 5. Smoke-test normalization

Create `normalization-test.json`:

```json
{
  "opening_balances": [
    {
      "idempotency_key": "test-normalize-FERT-113624-v722",
      "product_code": "FERT-113624",
      "quantity": 400,
      "unit": "g",
      "location_code": "MAIN"
    }
  ],
  "atomic": true,
  "reject_nonzero_existing": true
}
```

Run:

```bash
curl -i -X POST \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  --data-binary @normalization-test.json \
  "YOUR_PREVIEW_URL/inventory/import-opening-balances"
```

Expected normalized quantity: `0.400`, unit: `kg`.

Use a product/location with zero existing stock or reverse the test transaction after validation.

## 6. Merge

Merge to `main` only after health, conversion, zero-skip, incompatible-unit and duplicate tests pass.
