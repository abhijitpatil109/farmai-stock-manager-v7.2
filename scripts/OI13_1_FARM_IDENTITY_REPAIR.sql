-- OI-1.3.1 guarded Bendri farm-identity repair.
-- This script never creates or guesses a geotag.
-- It changes the farm display name only when exactly one active farm exists
-- and that same farm already owns at least one active weather location.

BEGIN;

DO $$
DECLARE
    active_farm_count integer;
    target_farm_id uuid;
    active_location_count integer;
BEGIN
    SELECT count(*)
      INTO active_farm_count
      FROM public.farms
     WHERE active=true;

    IF active_farm_count <> 1 THEN
        RAISE EXCEPTION
            'FarmAI repair aborted: expected exactly one active farm, found %.',
            active_farm_count;
    END IF;

    SELECT id
      INTO target_farm_id
      FROM public.farms
     WHERE active=true;

    SELECT count(*)
      INTO active_location_count
      FROM public.weather_locations
     WHERE farm_id=target_farm_id
       AND active=true;

    IF active_location_count = 0 THEN
        RAISE EXCEPTION
            'FarmAI repair aborted: the active farm has no active stored weather location.';
    END IF;

    UPDATE public.farms
       SET name_en='Bendri',
           name_mr='बेंद्री'
     WHERE id=target_farm_id
       AND active=true;
END $$;

COMMIT;

-- Verification: one active Bendri farm and at least one active geotag must appear.
SELECT
    f.id AS farm_id,
    f.name_en,
    f.name_mr,
    wl.id AS weather_location_id,
    wl.plot_id,
    wl.latitude,
    wl.longitude,
    wl.timezone,
    wl.source
FROM public.farms f
JOIN public.weather_locations wl
  ON wl.farm_id=f.id
 AND wl.active=true
WHERE f.active=true
ORDER BY wl.plot_id NULLS FIRST;
