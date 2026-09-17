# Deploy OI-1.3.1 Weather Routing Fix

## Scope

This release fixes repeated location questions and first-response spray-window
failures. It introduces one read-only consultation endpoint and does not change
stock, activities or database schema.

OI-1.3.1 additionally makes farm identity resolution resilient: `farm_id` takes
priority over a display name, unique normalized names such as `Bendri` and
`Bendri Farm` match safely, and a single active farm is an audited fallback.
Multiple active farms never use the fallback.

## 1. Pre-deployment validation

```bash
python3 -m pytest -q
python3 tools/build_focused_gpt_openapi.py
python3 tools/acceptance_oi13_weather.py
```

Expected: tests pass, focused schema contains 17 operations, and offline
acceptance reports `PASS`.

## 2. Database readiness check

No migration is required. Run the read-only SQL in
`scripts/OI13_WEATHER_READINESS_VALIDATION.sql` against production PostgreSQL.

Expected:

- Bendri is returned as one active farm;
- active Drumstick and other crop cycles resolve a plot or farm weather location;
- the final blocking-defect query returns zero rows.

If the deployed response reports that Bendri cannot be resolved even though an
active geotag exists, run the guarded canonical-name repair:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f scripts/OI13_1_FARM_IDENTITY_REPAIR.sql
```

The repair aborts unless exactly one active farm exists and that farm already
has an active weather location. It never creates or guesses coordinates.

## 3. Deploy backend

Deploy the repository through the existing Vercel workflow. Keep the existing
environment variables and `X-API-Key` configuration unchanged.

Verify that production OpenAPI exposes:

```text
POST /api/v1/operations/spray-window
operationId: getBestOperationalSprayWindow
```

## 4. Update the existing FarmAI GPT Action

Import `openapi/FarmAI_GPT_Focused_OpenAPI_OI1_3.json` into the existing FarmAI
Action. Do not create a second competing Action. Preserve authentication:

- Authentication type: API Key
- Header: `X-API-Key`
- Value: existing production `FARMAI_API_KEY`

Replace the older operational instruction delta with
`docs/gpt/OI13_GPT_INSTRUCTION.txt`, or append it if the GPT configuration keeps
the stock presentation instructions separately.

## 5. Live acceptance

```bash
export FARMAI_API_KEY='your-existing-key'
python3 tools/acceptance_oi13_weather.py --live
```

Expected: `PASS`, a resolved farm/crop/geotag, and either a primary window or an
explicit `INSUFFICIENT_DATA` decision.

## 6. GPT conversational acceptance

Ask these in a new FarmAI GPT conversation:

1. `Tomorrow I am planning a Drumstick spray. Give me the best spray window.`
2. `Check Drumstick spray window now.`
3. `Can we spray turmeric tomorrow morning?`
4. `Tomorrow I plan M45 + Tata Bahar in Drumstick. Rate it and give the window.`
5. `Give me today's stock availability.`

Pass criteria:

- Questions 1–4 call `getBestOperationalSprayWindow` on the first attempt.
- The GPT does not ask for coordinates or village before the Action call.
- It shows the backend-resolved farm/crop/plot and current evidence freshness.
- Product rainfastness is not invented.
- Question 5 still uses `getOperationalStock`; existing stock/activity/purchase
  behavior is unchanged.
