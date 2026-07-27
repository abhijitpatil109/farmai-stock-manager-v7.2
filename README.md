# FarmAI Stock Manager V7.2.2

Production-ready FastAPI + PostgreSQL stock service with:

- immutable product base units;
- centralized quantity normalization;
- `kg ↔ g ↔ mg` and `l ↔ ml` conversions;
- atomic bulk opening-balance import;
- zero-stock rows reported as `SKIPPED_ZERO` without ledger entries;
- idempotent stock transactions and reservations;
- negative-stock prevention;
- Vercel deployment configuration.

## Deploy

1. Upload/replace the repository files on the `feature/bulk-import` branch.
2. No database migration is required for V7.2.2.
3. Allow Vercel to create a preview deployment.
4. Verify `/health` returns version `7.2.2`.
5. Run the normalization smoke tests in `docs/DEPLOY_V7.2.2.md`.
6. Merge into `main` only after the preview tests pass.

See `docs/QUANTITY_NORMALIZATION_STANDARD.md` and `docs/BULK_IMPORT_GUIDE.md`.
