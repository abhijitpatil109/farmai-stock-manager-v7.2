# FarmAI Activity Register — Backend Foundation V1

This package is the next implementation step after `002_activity_register_foundation_v1.sql`.

## Scope

This phase exposes the agricultural context required before Activity CRUD:

- Reference Data (संदर्भ डेटा)
- Farm (शेत)
- Plot (प्लॉट)
- Crop Cycle (पीक चक्र)

It does **not** alter or deduct Stock Manager inventory and does not yet create Activity (क्रियाकलाप) records.

## Files

- `app/schemas/activity_register.py` — NEW
- `app/services/activity_register.py` — NEW
- `app/api/v1/activity_register.py` — NEW
- `tools/install_activity_register_backend_v1.py` — installer/registration helper
- `database/003_activity_register_backend_v1_validate.sql` — read-only validation

## Install

Copy/extract this package into a temporary folder or repository root and run:

```bash
python tools/install_activity_register_backend_v1.py
```

The installer:
1. copies all new files,
2. backs up `app/main.py`,
3. adds the Activity Register router import,
4. registers the router,
5. leaves all Stock Manager routes intact.

## Start locally

Use the same command you already use for the FarmAI backend. If using Uvicorn directly:

```bash
uvicorn app.main:app --reload
```

## API validation

With your existing API key:

```bash
curl -H "X-API-Key: $FARMAI_API_KEY" \
  http://127.0.0.1:8000/api/v1/activity-register/reference-data
```

Expected: `ok=true` and bilingual seeded reference arrays.

Then check OpenAPI:

```bash
curl http://127.0.0.1:8000/openapi.json
```

Expected new operations:
- `getActivityRegisterReferenceData`
- `createFarm`
- `listFarms`
- `createPlot`
- `listPlots`
- `createCropCycle`
- `listCropCycles`
- `getCropCycle`

## Database validation

Run:

`database/003_activity_register_backend_v1_validate.sql`

No database migration is required for this phase because the required schema was already created by migration 002.

## Rollback / recovery

If application deployment must be reverted:

1. restore the timestamped `app/main.py.backup_activity_*` created by the installer;
2. remove:
   - `app/api/v1/activity_register.py`
   - `app/services/activity_register.py`
   - `app/schemas/activity_register.py`
3. restart/redeploy.

Do **not** run the database 002 rollback merely to undo this API deployment.
