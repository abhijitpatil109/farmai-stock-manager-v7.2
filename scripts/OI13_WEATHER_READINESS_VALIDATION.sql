-- OI-1.3 read-only validation. No database migration is required.

-- 1. Active farm and default farm-level geotag.
SELECT
    f.id AS farm_id,
    f.name_en AS farm_name_en,
    f.name_mr AS farm_name_mr,
    wl.id AS weather_location_id,
    wl.plot_id,
    wl.latitude,
    wl.longitude,
    wl.timezone,
    wl.source,
    wl.active AS weather_location_active
FROM public.farms f
LEFT JOIN public.weather_locations wl
  ON wl.farm_id=f.id
 AND wl.plot_id IS NULL
 AND wl.active=true
WHERE f.active=true
ORDER BY f.name_en;

-- 2. Active crop -> plot -> preferred plot geotag, with farm fallback visibility.
SELECT
    cc.id AS crop_cycle_id,
    cc.crop_name_en,
    cc.crop_name_mr,
    cc.status,
    p.id AS plot_id,
    p.code AS plot_code,
    p.name_en AS plot_name_en,
    p.name_mr AS plot_name_mr,
    pwl.id AS plot_weather_location_id,
    fwl.id AS fallback_farm_weather_location_id,
    COALESCE(pwl.timezone,fwl.timezone) AS resolved_timezone,
    COALESCE(pwl.source,fwl.source) AS resolved_geotag_source
FROM public.crop_cycles cc
JOIN public.plots p ON p.id=cc.plot_id
LEFT JOIN public.weather_locations pwl
  ON pwl.farm_id=cc.farm_id
 AND pwl.plot_id=cc.plot_id
 AND pwl.active=true
LEFT JOIN public.weather_locations fwl
  ON fwl.farm_id=cc.farm_id
 AND fwl.plot_id IS NULL
 AND fwl.active=true
WHERE cc.status='ACTIVE'
ORDER BY cc.crop_name_en,p.code;

-- 3. Blocking readiness defects: every active crop must resolve a geotag.
SELECT
    cc.id AS crop_cycle_id,
    cc.crop_name_en,
    p.code AS plot_code,
    'NO_ACTIVE_PLOT_OR_FARM_WEATHER_LOCATION' AS defect
FROM public.crop_cycles cc
JOIN public.plots p ON p.id=cc.plot_id
WHERE cc.status='ACTIVE'
  AND NOT EXISTS (
      SELECT 1
      FROM public.weather_locations wl
      WHERE wl.farm_id=cc.farm_id
        AND wl.active=true
        AND (wl.plot_id=cc.plot_id OR wl.plot_id IS NULL)
  )
ORDER BY cc.crop_name_en,p.code;
