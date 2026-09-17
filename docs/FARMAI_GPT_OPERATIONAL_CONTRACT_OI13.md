# FarmAI GPT Operational Contract — OI-1.3.1

OI-1.3.1 preserves the OI-1.2 stock/activity contract and adds one mandatory
geotag-resolved weather workflow.

## New GPT-facing operation

`POST /api/v1/operations/spray-window`

Operation ID: `getBestOperationalSprayWindow`

The operation:

1. resolves an active stored farm by ID/name or the single-active-farm default;
2. resolves an active crop cycle and plot from crop/plot identity;
3. resolves the plot geotag, falling back to the farm geotag;
4. resolves TODAY/TOMORROW in the stored location timezone;
5. refreshes deterministic and ensemble forecast evidence;
6. evaluates candidate spray periods across the requested local-day window;
7. ranks non-overlapping primary and backup windows; and
8. returns evidence, thresholds, freshness and label guardrails.

Coordinates are intentionally not accepted in the GPT request. Geotags remain
authoritative backend master data.

## Decision semantics

- `SPRAY`: highest-ranked candidate passed the supplied weather constraints and
  product rainfastness was known.
- `CONDITIONAL`: a useful ranked window exists, but one or more cautions remain,
  commonly unknown product rainfastness.
- `AVOID`: every ranked candidate is held by material rain/wind/gust risk.
- `INSUFFICIENT_DATA`: fresh multi-model evidence was not available.

These are weather-operational decisions. They do not independently authorize a
pesticide, fungicide, fertilizer or tank mix.

## Resolution rules

- Missing IDs are normal. Prefer stored farm/crop names from the conversation.
- Ask the farmer for a location only after the API returns missing or ambiguous
  stored master data.
- Multiple active crop cycles with the same crop name require `plot_name` or
  `crop_cycle_id`.
- A supplied `farm_id` is authoritative even when an accompanying display name
  differs. Unique normalized names are accepted. The single-active-farm fallback
  is reported as `farm_identity_resolution` and is never used with multiple farms.
- Plot weather location is preferred. Farm default weather location is the
  defined fallback.

## Guardrails

- Forecast is refreshed by default.
- Product-specific rainfastness is never invented.
- Unknown rainfastness uses a conservative screening look-ahead but cannot
  produce an unconditional SAFE decision.
- Default wind, gust, temperature and humidity values are screening limits;
  label/manufacturer limits override them.
- Forecast freshness, deterministic model support, ensemble probability and
  local reliability remain separate evidence fields.

## Preserved OI-1.2 rules

- Current stock -> `getOperationalStock`.
- Activity history -> `getOperationalActivityHistory`.
- Agronomic recommendation -> `getOperationalCropDecisionContext` first.
- Crop-linked consumption -> `completeOperationalActivity`.
- New products and purchases use the canonical search/create/purchase workflow.
- Writes require stable idempotency and confirmed API success.
