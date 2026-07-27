# Bulk Opening-Balance Import — V7.2.2

Endpoint:

`POST /inventory/import-opening-balances`

The endpoint accepts compatible units and normalizes each quantity to the product's base unit.

Example:

```json
{
  "opening_balances": [
    {
      "action": "recordOpeningBalance",
      "idempotency_key": "opening-FERT-113624-20260727",
      "product_code": "FERT-113624",
      "quantity": 400,
      "unit": "g",
      "location_code": "MAIN",
      "effective_at": "2026-07-27T00:00:00+05:30",
      "notes": "FarmAI V7.2 Initial Opening Balance"
    },
    {
      "action": "recordOpeningBalance",
      "idempotency_key": "opening-MICRO-METRO-20260727",
      "product_code": "MICRO-METRO",
      "quantity": 0,
      "unit": "g",
      "location_code": "MAIN"
    }
  ],
  "atomic": true,
  "reject_nonzero_existing": true
}
```

Expected behavior:

- `400 g` for a product whose base unit is `kg` becomes `0.400 kg`.
- A zero row is returned under `skipped_zero` and does not create a stock transaction.
- In atomic mode, any invalid non-duplicate row prevents all positive rows from being inserted.
- Reusing the same idempotency key returns the existing transaction as a duplicate.
