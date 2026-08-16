# FarmAI V7.2 — B6 Cleanup Steps

1. From repo root, confirm environment variables are still set:

   export BASE_URL="https://farmai-stock-manager-v7-2.vercel.app"
   export FARMAI_API_KEY="YOUR_API_KEY"

2. Preview the latest B6 run cleanup:

   python3 scripts/b6_certification/cleanup_execute.py

   Nothing is changed in preview mode.

3. Confirm the displayed products are only B6 certification products.

4. Execute stock neutralization:

   python3 scripts/b6_certification/cleanup_execute.py --confirm

   Expected final result:

   CLEANUP RESULT: PASS

5. Run `deactivate_b6_products.sql` in the PostgreSQL SQL console.

6. Verify:
   - every B6 CERT product has physical stock 0;
   - every B6 CERT product is inactive;
   - transaction history remains present;
   - genuine farm products were not changed.

Do not DELETE B6 ledger transactions. Cleanup must remain auditable.
