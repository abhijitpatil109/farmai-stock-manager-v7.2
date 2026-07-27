# FarmAI Stock Manager V7.2

Authoritative FarmAI stock capability.

Owns:
- products and active ingredients
- stock locations
- batches and expiry
- stock ledger and balances
- availability checks
- reservations
- actual consumption
- verification, reversal and audit

The Weekly Planner must use this capability through its API and must never
directly modify stock tables.


## Bulk opening-balance import (v7.2.1)

`POST /inventory/import-opening-balances` validates and imports up to 500 opening balances in one atomic request. It rejects non-zero existing stock by default to prevent accidental double loading and treats existing idempotency keys as safe duplicates.
