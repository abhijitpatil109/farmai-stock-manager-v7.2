# Bulk Opening Balance Import

Endpoint: `POST /inventory/import-opening-balances`

Defaults:
- `atomic: true` — if any new row is invalid, no new rows are inserted.
- `reject_nonzero_existing: true` — prevents adding an opening balance on top of existing stock.
- Existing idempotency keys are reported as duplicates and are not inserted again.

Payload:
```json
{
  "opening_balances": [
    {
      "action": "recordOpeningBalance",
      "idempotency_key": "opening-FERT-CN-20260727",
      "product_code": "FERT-CN",
      "quantity": 50,
      "unit": "kg",
      "location_code": "MAIN",
      "effective_at": "2026-07-27T00:00:00+05:30",
      "notes": "FarmAI V7.2 Initial Opening Balance"
    }
  ],
  "atomic": true,
  "reject_nonzero_existing": true
}
```
