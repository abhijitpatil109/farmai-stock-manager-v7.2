-- FarmAI Activity Register V1
-- Backend Foundation validation SQL (read-only)
-- Run after deploying the Phase 1 backend.

-- 1. Foundation taxonomy counts.
SELECT
    (SELECT count(*) FROM public.measurement_units WHERE active=true) AS measurement_units,
    (SELECT count(*) FROM public.dose_basis_types WHERE active=true) AS dose_basis_types,
    (SELECT count(*) FROM public.application_methods WHERE active=true) AS application_methods,
    (SELECT count(*) FROM public.activity_types WHERE active=true) AS activity_types,
    (SELECT count(*) FROM public.activity_purposes WHERE active=true) AS activity_purposes,
    (SELECT count(*) FROM public.observation_types WHERE active=true) AS observation_types;
-- Expected: 12, 7, 9, 11, 11, 11.

-- 2. Confirm all taxonomy entries have bilingual farmer-visible labels.
SELECT 'activity_types' AS source, code, name_en, name_mr
FROM public.activity_types
WHERE active=true AND (btrim(name_en)='' OR btrim(name_mr)='')
UNION ALL
SELECT 'activity_purposes', code, name_en, name_mr
FROM public.activity_purposes
WHERE active=true AND (btrim(name_en)='' OR btrim(name_mr)='')
UNION ALL
SELECT 'observation_types', code, name_en, name_mr
FROM public.observation_types
WHERE active=true AND (btrim(name_en)='' OR btrim(name_mr)='')
ORDER BY source, code;
-- Expected: 0 rows.

-- 3. Operational master counts before creating real farm data.
SELECT
    (SELECT count(*) FROM public.farms) AS farms,
    (SELECT count(*) FROM public.plots) AS plots,
    (SELECT count(*) FROM public.crop_cycles) AS crop_cycles;
-- Expected before API creation: typically 0,0,0.

-- 4. Existing Stock Manager remains present and untouched.
SELECT table_name
FROM information_schema.tables
WHERE table_schema='public'
  AND table_name IN (
    'products','product_active_ingredients','product_display_metadata',
    'stock_batches','stock_locations','stock_reservations',
    'stock_transactions','reservation_events'
  )
ORDER BY table_name;
-- Expected: 8 rows.

-- 5. After API creation of masters, use this query to verify hierarchy.
SELECT
    f.id AS farm_id,
    f.name_en AS farm_name_en,
    f.name_mr AS farm_name_mr,
    p.id AS plot_id,
    p.name_en AS plot_name_en,
    p.name_mr AS plot_name_mr,
    cc.id AS crop_cycle_id,
    cc.crop_name_en,
    cc.crop_name_mr,
    cc.planting_date,
    cc.status,
    (CURRENT_DATE - cc.planting_date) AS current_dap
FROM public.crop_cycles cc
JOIN public.farms f ON f.id=cc.farm_id
JOIN public.plots p ON p.id=cc.plot_id
ORDER BY f.name_en, p.name_en, cc.planting_date;
