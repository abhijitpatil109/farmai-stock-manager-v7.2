BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name='postgis') THEN
    RAISE EXCEPTION 'POSTGIS_UNAVAILABLE: PostGIS is required for FarmAI Phase 9.';
  END IF;
END $$;

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS public.plot_geometries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plot_id uuid NOT NULL REFERENCES public.plots(id) ON DELETE RESTRICT,
  geometry_version integer NOT NULL CHECK (geometry_version > 0),
  source_type text NOT NULL CHECK (source_type IN ('KML_IMPORT','GEOJSON_IMPORT','MANUAL','API')),
  source_reference text NOT NULL,
  source_checksum text NOT NULL,
  geom geometry(MultiPolygon,4326) NOT NULL,
  interior_geom geometry(MultiPolygon,4326),
  centroid geometry(Point,4326) NOT NULL,
  area_m2 numeric(16,4) NOT NULL CHECK(area_m2 > 0),
  calculated_area_acres numeric(14,6) NOT NULL CHECK(calculated_area_acres > 0),
  geometry_hash text NOT NULL,
  edge_sensitivity text NOT NULL DEFAULT 'NORMAL'
    CHECK(edge_sensitivity IN ('NORMAL','HIGH','VERY_HIGH')),
  active boolean NOT NULL DEFAULT true,
  effective_from date NOT NULL DEFAULT CURRENT_DATE,
  effective_to date,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_plot_geometry_version UNIQUE(plot_id,geometry_version),
  CONSTRAINT uq_plot_geometry_hash UNIQUE(plot_id,geometry_hash),
  CONSTRAINT ck_plot_geometry_valid CHECK(ST_IsValid(geom)),
  CONSTRAINT ck_plot_geometry_srid CHECK(ST_SRID(geom)=4326),
  CONSTRAINT ck_plot_geometry_dates CHECK(effective_to IS NULL OR effective_to >= effective_from)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_plot_geometry_active
 ON public.plot_geometries(plot_id) WHERE active=true;
CREATE INDEX IF NOT EXISTS ix_plot_geometry_geom ON public.plot_geometries USING gist(geom);
CREATE INDEX IF NOT EXISTS ix_plot_geometry_interior ON public.plot_geometries USING gist(interior_geom);

CREATE TABLE IF NOT EXISTS public.remote_sensing_providers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_code text NOT NULL UNIQUE,
  provider_name text NOT NULL,
  provider_role text NOT NULL CHECK(provider_role IN ('CATALOG','PROCESSING','COMBINED')),
  base_url text NOT NULL,
  collection_code text,
  auth_scheme text NOT NULL CHECK(auth_scheme IN ('NONE','OAUTH2_CLIENT_CREDENTIALS','API_KEY')),
  licence_code text,
  attribution_text text,
  commercial_use_status text NOT NULL CHECK(commercial_use_status IN ('ALLOWED','REVIEW_REQUIRED','NOT_ALLOWED')),
  active boolean NOT NULL DEFAULT true,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.remote_sensing_providers(
 provider_code,provider_name,provider_role,base_url,collection_code,auth_scheme,
 licence_code,attribution_text,commercial_use_status,metadata
) VALUES
 ('CDSE_STAC','Copernicus Data Space STAC','CATALOG',
  'https://stac.dataspace.copernicus.eu/v1/','sentinel-2-l2a','NONE',
  'COPERNICUS_SENTINEL_DATA_TERMS','Contains modified Copernicus Sentinel data','ALLOWED',
  '{"stac_version":"1.1.0"}'::jsonb),
 ('CDSE_SENTINEL_HUB','Copernicus Data Space Sentinel Hub','PROCESSING',
  'https://sh.dataspace.copernicus.eu/','sentinel-2-l2a','OAUTH2_CLIENT_CREDENTIALS',
  'COPERNICUS_SENTINEL_DATA_TERMS','Contains modified Copernicus Sentinel data','ALLOWED',
  '{"api":"Statistical API"}'::jsonb)
ON CONFLICT(provider_code) DO UPDATE SET
 provider_name=excluded.provider_name,
 provider_role=excluded.provider_role,
 base_url=excluded.base_url,
 collection_code=excluded.collection_code,
 auth_scheme=excluded.auth_scheme,
 licence_code=excluded.licence_code,
 attribution_text=excluded.attribution_text,
 commercial_use_status=excluded.commercial_use_status,
 metadata=excluded.metadata,
 updated_at=now();

CREATE TABLE IF NOT EXISTS public.remote_sensing_fetch_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id uuid NOT NULL REFERENCES public.remote_sensing_providers(id),
  plot_id uuid REFERENCES public.plots(id),
  operation text NOT NULL CHECK(operation IN ('DISCOVER','STATISTICS','REFRESH','HEALTH')),
  request_fingerprint text NOT NULL,
  status text NOT NULL CHECK(status IN ('STARTED','SUCCESS','DEGRADED','FAILED')),
  requested_from timestamptz,
  requested_to timestamptz,
  attempts integer NOT NULL DEFAULT 1 CHECK(attempts>=1),
  http_status integer,
  records_received integer NOT NULL DEFAULT 0 CHECK(records_received>=0),
  error_code text,
  error_message text,
  request_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  response_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_rs_fetch_plot_time ON public.remote_sensing_fetch_runs(plot_id,started_at DESC);

CREATE TABLE IF NOT EXISTS public.remote_sensing_scenes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id uuid NOT NULL REFERENCES public.remote_sensing_providers(id),
  provider_scene_id text NOT NULL,
  collection_code text NOT NULL,
  platform text,
  acquired_at timestamptz NOT NULL,
  source_created_at timestamptz,
  processing_level text,
  processing_version text,
  cloud_cover_pct numeric(7,3) CHECK(cloud_cover_pct IS NULL OR cloud_cover_pct BETWEEN 0 AND 100),
  bbox jsonb,
  scene_geometry jsonb,
  assets jsonb NOT NULL DEFAULT '{}'::jsonb,
  raw_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  retrieved_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_rs_scene UNIQUE(provider_id,provider_scene_id)
);
CREATE INDEX IF NOT EXISTS ix_rs_scene_acquired ON public.remote_sensing_scenes(acquired_at DESC);

CREATE TABLE IF NOT EXISTS public.remote_sensing_scene_plot_links (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scene_id uuid NOT NULL REFERENCES public.remote_sensing_scenes(id) ON DELETE CASCADE,
  plot_geometry_id uuid NOT NULL REFERENCES public.plot_geometries(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_rs_scene_plot UNIQUE(scene_id,plot_geometry_id)
);

CREATE TABLE IF NOT EXISTS public.remote_sensing_rule_packs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_code text NOT NULL,
  version integer NOT NULL CHECK(version>0),
  rule_type text NOT NULL CHECK(rule_type IN ('QUALITY','STATISTICAL_ANOMALY','INDEX_FORMULA')),
  name_en text NOT NULL,
  name_mr text,
  rule_payload jsonb NOT NULL,
  verification_status text NOT NULL CHECK(verification_status IN ('VERIFIED','UNVERIFIED')),
  evidence_reference text,
  active boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_rs_rule UNIQUE(rule_code,version)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rs_rule_active
 ON public.remote_sensing_rule_packs(rule_code) WHERE active=true;

INSERT INTO public.remote_sensing_rule_packs(
 rule_code,version,rule_type,name_en,name_mr,rule_payload,verification_status,evidence_reference,active
) VALUES
 ('S2_L2A_INDEX_FORMULAS',1,'INDEX_FORMULA','Sentinel-2 L2A index formulas',
  'Sentinel-2 L2A निर्देशांक सूत्रे',
  '{"NDVI":"(B08-B04)/(B08+B04)","NDRE":"(B08-B05)/(B08+B05)","NDMI":"(B08-B11)/(B08+B11)","diagnostic":false}'::jsonb,
  'VERIFIED','Standard normalized-difference spectral-index definitions; non-diagnostic.',true),
 ('S2_L2A_QUALITY_POLICY',1,'QUALITY','Sentinel-2 L2A quality policy',
  'Sentinel-2 L2A गुणवत्ता धोरण',
  '{"valid_min_pct":50,"partial_min_pct":30,"cloud_high_pct":50,"shadow_high_pct":30,"scl_excluded":[0,1,3,8,9,10,11]}'::jsonb,
  'VERIFIED','FarmAI engineering evidence-quality policy; not an agronomic threshold.',true),
 ('TEMPORAL_ANOMALY_STATISTICAL',1,'STATISTICAL_ANOMALY','Temporal statistical anomaly policy',
  'कालानुक्रमिक सांख्यिकीय विसंगती धोरण',
  '{"metric":"NDVI","baseline_observations":4,"lookback_days":45,"z_threshold":2.0,"min_relative_change_pct":10.0,"action":"SCOUT","diagnostic":false}'::jsonb,
  'VERIFIED','FarmAI statistical change-detection method; scouting-only, non-diagnostic.',true)
ON CONFLICT(rule_code,version) DO UPDATE SET
 rule_payload=excluded.rule_payload,
 verification_status=excluded.verification_status,
 evidence_reference=excluded.evidence_reference,
 active=excluded.active;

CREATE TABLE IF NOT EXISTS public.plot_remote_observations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plot_id uuid NOT NULL REFERENCES public.plots(id) ON DELETE RESTRICT,
  crop_cycle_id uuid REFERENCES public.crop_cycles(id) ON DELETE RESTRICT,
  plot_geometry_id uuid NOT NULL REFERENCES public.plot_geometries(id) ON DELETE RESTRICT,
  scene_id uuid REFERENCES public.remote_sensing_scenes(id) ON DELETE RESTRICT,
  processing_provider_id uuid NOT NULL REFERENCES public.remote_sensing_providers(id),
  acquired_at timestamptz NOT NULL,
  analysis_scope text NOT NULL CHECK(analysis_scope IN ('FULL_POLYGON','INTERIOR_POLYGON')),
  output_grid_resolution_m numeric(8,3) NOT NULL CHECK(output_grid_resolution_m>0),
  native_resolution_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  valid_pixel_pct numeric(7,3) CHECK(valid_pixel_pct IS NULL OR valid_pixel_pct BETWEEN 0 AND 100),
  cloud_pixel_pct numeric(7,3) CHECK(cloud_pixel_pct IS NULL OR cloud_pixel_pct BETWEEN 0 AND 100),
  shadow_pixel_pct numeric(7,3) CHECK(shadow_pixel_pct IS NULL OR shadow_pixel_pct BETWEEN 0 AND 100),
  vegetation_pixel_pct numeric(7,3) CHECK(vegetation_pixel_pct IS NULL OR vegetation_pixel_pct BETWEEN 0 AND 100),
  quality_status text NOT NULL CHECK(quality_status IN (
   'VALID','PARTIAL','CLOUD_CONTAMINATED','SHADOW_CONTAMINATED',
   'INSUFFICIENT_VALID_PIXELS','GEOMETRY_TOO_SMALL','DATA_UNAVAILABLE','PROCESSING_FAILED'
  )),
  quality_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
  algorithm_version text NOT NULL,
  request_fingerprint text NOT NULL UNIQUE,
  provider_payload_hash text,
  raw_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_plot_remote_plot_time ON public.plot_remote_observations(plot_id,acquired_at DESC);
CREATE INDEX IF NOT EXISTS ix_plot_remote_cycle_time ON public.plot_remote_observations(crop_cycle_id,acquired_at DESC);

CREATE TABLE IF NOT EXISTS public.plot_index_statistics (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  observation_id uuid NOT NULL REFERENCES public.plot_remote_observations(id) ON DELETE CASCADE,
  index_code text NOT NULL CHECK(index_code IN ('NDVI','NDRE','NDMI')),
  min_value numeric(14,8),
  max_value numeric(14,8),
  mean_value numeric(14,8),
  median_value numeric(14,8),
  stddev_value numeric(14,8),
  p10_value numeric(14,8),
  p90_value numeric(14,8),
  sample_count integer CHECK(sample_count IS NULL OR sample_count>=0),
  nodata_count integer CHECK(nodata_count IS NULL OR nodata_count>=0),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_plot_index UNIQUE(observation_id,index_code)
);

CREATE TABLE IF NOT EXISTS public.remote_sensing_anomalies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plot_id uuid NOT NULL REFERENCES public.plots(id) ON DELETE RESTRICT,
  crop_cycle_id uuid REFERENCES public.crop_cycles(id) ON DELETE RESTRICT,
  observation_id uuid NOT NULL REFERENCES public.plot_remote_observations(id) ON DELETE RESTRICT,
  rule_pack_id uuid NOT NULL REFERENCES public.remote_sensing_rule_packs(id) ON DELETE RESTRICT,
  metric_code text NOT NULL,
  anomaly_type text NOT NULL CHECK(anomaly_type IN ('DECLINE','INCREASE','SPATIAL_VARIATION')),
  severity text NOT NULL CHECK(severity IN ('LOW','MEDIUM','HIGH')),
  confidence text NOT NULL CHECK(confidence IN ('LOW','MEDIUM','HIGH','INSUFFICIENT_DATA')),
  baseline_from date,
  baseline_to date,
  baseline_count integer NOT NULL DEFAULT 0 CHECK(baseline_count>=0),
  current_value numeric(14,8),
  baseline_mean numeric(14,8),
  baseline_stddev numeric(14,8),
  z_score numeric(14,8),
  relative_change_pct numeric(14,6),
  diagnosis text,
  recommended_action text NOT NULL DEFAULT 'SCOUT',
  status text NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','SCOUTING','VERIFIED','DISMISSED','RESOLVED')),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_rs_anomaly_no_diagnosis CHECK(diagnosis IS NULL)
);
CREATE INDEX IF NOT EXISTS ix_rs_anomaly_open ON public.remote_sensing_anomalies(plot_id,status,created_at DESC);

CREATE TABLE IF NOT EXISTS public.remote_sensing_anomaly_zones (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  anomaly_id uuid NOT NULL REFERENCES public.remote_sensing_anomalies(id) ON DELETE CASCADE,
  zone_geometry geometry(MultiPolygon,4326),
  area_m2 numeric(16,4) CHECK(area_m2 IS NULL OR area_m2>0),
  area_pct numeric(7,3) CHECK(area_pct IS NULL OR area_pct BETWEEN 0 AND 100),
  metric_delta numeric(14,8),
  confidence text CHECK(confidence IN ('LOW','MEDIUM','HIGH','INSUFFICIENT_DATA')),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rs_anomaly_zone_geom ON public.remote_sensing_anomaly_zones USING gist(zone_geometry);

CREATE TABLE IF NOT EXISTS public.scouting_tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  farm_id uuid NOT NULL REFERENCES public.farms(id) ON DELETE RESTRICT,
  plot_id uuid NOT NULL REFERENCES public.plots(id) ON DELETE RESTRICT,
  crop_cycle_id uuid REFERENCES public.crop_cycles(id) ON DELETE RESTRICT,
  anomaly_id uuid UNIQUE REFERENCES public.remote_sensing_anomalies(id) ON DELETE RESTRICT,
  source_type text NOT NULL CHECK(source_type IN ('MANUAL','REMOTE_SENSING','WEATHER','INTELLIGENCE','PLANNER')),
  title_en text NOT NULL,
  title_mr text NOT NULL,
  reason_en text,
  reason_mr text,
  priority text NOT NULL DEFAULT 'MEDIUM' CHECK(priority IN ('LOW','MEDIUM','HIGH','URGENT')),
  checklist jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL DEFAULT 'PROPOSED'
    CHECK(status IN ('PROPOSED','ASSIGNED','IN_PROGRESS','COMPLETED','DISMISSED')),
  assigned_to text,
  due_date date,
  idempotency_key text NOT NULL UNIQUE,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_scout_status ON public.scouting_tasks(status,due_date,priority);

CREATE TABLE IF NOT EXISTS public.scouting_observations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id uuid NOT NULL REFERENCES public.scouting_tasks(id) ON DELETE RESTRICT,
  observed_at timestamptz NOT NULL,
  observer text NOT NULL,
  gps_location geometry(Point,4326),
  severity text CHECK(severity IN ('NONE','LOW','MEDIUM','HIGH','SEVERE')),
  affected_area_pct numeric(7,3) CHECK(affected_area_pct IS NULL OR affected_area_pct BETWEEN 0 AND 100),
  symptom_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  soil_moisture_condition text,
  waterlogging boolean,
  wilting boolean,
  yellowing boolean,
  pest_visible boolean,
  disease_symptom_visible boolean,
  notes_en text,
  notes_mr text,
  verification_status text NOT NULL DEFAULT 'FARMER_REPORTED'
    CHECK(verification_status IN ('FARMER_REPORTED','FIELD_VERIFIED','EXPERT_VERIFIED')),
  observation_hash text NOT NULL,
  is_current boolean NOT NULL DEFAULT true,
  supersedes_observation_id uuid REFERENCES public.scouting_observations(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_scout_observation_hash UNIQUE(task_id,observation_hash)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_scout_current_observation
 ON public.scouting_observations(task_id) WHERE is_current=true;

CREATE TABLE IF NOT EXISTS public.scouting_media (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  observation_id uuid NOT NULL REFERENCES public.scouting_observations(id) ON DELETE CASCADE,
  media_type text NOT NULL CHECK(media_type IN ('PHOTO','VIDEO','OTHER')),
  storage_reference text NOT NULL,
  checksum text,
  captured_at timestamptz,
  latitude numeric(10,7),
  longitude numeric(10,7),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_scout_media UNIQUE(observation_id,storage_reference)
);

CREATE TABLE IF NOT EXISTS public.season_metric_series (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  crop_cycle_id uuid NOT NULL REFERENCES public.crop_cycles(id) ON DELETE CASCADE,
  metric_code text NOT NULL,
  metric_date date NOT NULL,
  dap integer,
  value numeric(16,8),
  unit text,
  source_type text NOT NULL CHECK(source_type IN ('REMOTE_SENSING','WEATHER','ACTIVITY','OBSERVATION','HARVEST')),
  source_reference text NOT NULL,
  quality_status text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_season_metric UNIQUE(crop_cycle_id,metric_code,metric_date,source_type,source_reference)
);
CREATE INDEX IF NOT EXISTS ix_season_metric_cycle ON public.season_metric_series(crop_cycle_id,metric_code,dap,metric_date);

CREATE TABLE IF NOT EXISTS public.season_comparisons (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  current_crop_cycle_id uuid NOT NULL REFERENCES public.crop_cycles(id) ON DELETE CASCADE,
  baseline_crop_cycle_id uuid NOT NULL REFERENCES public.crop_cycles(id) ON DELETE CASCADE,
  metric_code text NOT NULL,
  alignment_type text NOT NULL CHECK(alignment_type IN ('DAP','STAGE')),
  alignment_value text NOT NULL,
  current_value numeric(16,8),
  baseline_value numeric(16,8),
  delta numeric(16,8),
  delta_pct numeric(16,6),
  confidence text NOT NULL CHECK(confidence IN ('LOW','MEDIUM','HIGH','INSUFFICIENT_DATA')),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_season_compare UNIQUE(
    current_crop_cycle_id,baseline_crop_cycle_id,metric_code,alignment_type,alignment_value
  )
);

CREATE TABLE IF NOT EXISTS public.intelligence_remote_evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  recommendation_id uuid REFERENCES public.intelligence_recommendations(id) ON DELETE CASCADE,
  crop_cycle_id uuid NOT NULL REFERENCES public.crop_cycles(id) ON DELETE CASCADE,
  evidence_type text NOT NULL CHECK(evidence_type IN ('REMOTE_OBSERVATION','REMOTE_ANOMALY','SCOUTING_TASK','SCOUTING_OBSERVATION')),
  evidence_id uuid NOT NULL,
  evidence_quality text,
  evidence_snapshot jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_intel_remote_evidence UNIQUE(recommendation_id,evidence_type,evidence_id)
);

COMMIT;
