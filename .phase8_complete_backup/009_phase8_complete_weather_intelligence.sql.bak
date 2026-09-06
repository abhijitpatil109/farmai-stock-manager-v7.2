BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE weather_fetch_runs ADD COLUMN IF NOT EXISTS run_initialized_at timestamptz;
ALTER TABLE weather_fetch_runs ADD COLUMN IF NOT EXISTS issued_at timestamptz;
ALTER TABLE weather_fetch_runs ADD COLUMN IF NOT EXISTS delivered_temporal_resolution_minutes integer;
ALTER TABLE weather_fetch_runs ADD COLUMN IF NOT EXISTS derivation_status text NOT NULL DEFAULT 'UNKNOWN';
ALTER TABLE weather_fetch_runs ADD COLUMN IF NOT EXISTS evidence_class text NOT NULL DEFAULT 'FORECAST';
ALTER TABLE weather_fetch_runs ADD COLUMN IF NOT EXISTS provider_metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

DO $$ BEGIN
 ALTER TABLE weather_fetch_runs ADD CONSTRAINT ck_weather_fetch_runs_derivation
 CHECK(derivation_status IN ('NATIVE','INTERPOLATED','DERIVED','AGGREGATED','MIXED','UNKNOWN'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
 ALTER TABLE weather_fetch_runs ADD CONSTRAINT ck_weather_fetch_runs_evidence_class
 CHECK(evidence_class IN ('FORECAST','MODEL_ANALYSIS','REANALYSIS','OFFICIAL_STATION','RADAR','FARM_SENSOR','MANUAL_OBSERVATION'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS weather_rule_packs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 code text NOT NULL,
 version integer NOT NULL CHECK(version>0),
 name_en text NOT NULL,
 name_mr text,
 operation_type text NOT NULL CHECK(operation_type IN ('SPRAY','FERTIGATION','IRRIGATION','GENERAL')),
 rules jsonb NOT NULL,
 evidence_reference text,
 verification_status text NOT NULL DEFAULT 'UNVERIFIED'
   CHECK(verification_status IN ('UNVERIFIED','VERIFIED','REJECTED')),
 active boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(code,version)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_weather_rule_pack_active
 ON weather_rule_packs(code) WHERE active=true;

CREATE TABLE IF NOT EXISTS weather_ensemble_runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 provider_id uuid NOT NULL REFERENCES external_data_providers(id),
 weather_location_id uuid NOT NULL REFERENCES weather_locations(id),
 model_code text NOT NULL,
 model_family text NOT NULL,
 requested_at timestamptz NOT NULL DEFAULT now(),
 retrieved_at timestamptz,
 run_initialized_at timestamptz,
 valid_from timestamptz,
 valid_to timestamptz,
 native_temporal_resolution_minutes integer,
 delivered_temporal_resolution_minutes integer NOT NULL DEFAULT 60,
 derivation_status text NOT NULL DEFAULT 'INTERPOLATED'
   CHECK(derivation_status IN ('NATIVE','INTERPOLATED','DERIVED','AGGREGATED','MIXED','UNKNOWN')),
 member_count integer NOT NULL CHECK(member_count>0),
 status text NOT NULL CHECK(status IN ('PENDING','SUCCESS','PARTIAL','FAILED')),
 http_status integer,
 error_code text,
 error_message text,
 request_fingerprint text NOT NULL,
 response_hash text,
 raw_payload jsonb,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(provider_id,weather_location_id,model_code,request_fingerprint)
);
CREATE INDEX IF NOT EXISTS ix_weather_ensemble_runs_location_retrieved
 ON weather_ensemble_runs(weather_location_id,retrieved_at DESC);

CREATE TABLE IF NOT EXISTS weather_ensemble_points (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 ensemble_run_id uuid NOT NULL REFERENCES weather_ensemble_runs(id) ON DELETE CASCADE,
 valid_at timestamptz NOT NULL,
 member_count integer NOT NULL CHECK(member_count>0),
 wet_member_count integer NOT NULL CHECK(wet_member_count>=0 AND wet_member_count<=member_count),
 precipitation_probability_pct numeric(6,3) NOT NULL CHECK(precipitation_probability_pct BETWEEN 0 AND 100),
 precipitation_min_mm numeric(10,3),
 precipitation_p25_mm numeric(10,3),
 precipitation_median_mm numeric(10,3),
 precipitation_p75_mm numeric(10,3),
 precipitation_max_mm numeric(10,3),
 source_semantics jsonb NOT NULL DEFAULT '{}'::jsonb,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(ensemble_run_id,valid_at)
);
CREATE INDEX IF NOT EXISTS ix_weather_ensemble_points_run_valid
 ON weather_ensemble_points(ensemble_run_id,valid_at);

CREATE TABLE IF NOT EXISTS weather_observations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 weather_location_id uuid NOT NULL REFERENCES weather_locations(id),
 observed_at timestamptz NOT NULL,
 evidence_class text NOT NULL CHECK(evidence_class IN ('OFFICIAL_STATION','RADAR','FARM_SENSOR','MANUAL_OBSERVATION','MODEL_ANALYSIS','REANALYSIS')),
 source_code text NOT NULL,
 precipitation_mm numeric(10,3),
 temperature_c numeric(6,2),
 relative_humidity_pct numeric(6,2) CHECK(relative_humidity_pct BETWEEN 0 AND 100),
 wind_speed_kmh numeric(8,2),
 wind_gust_kmh numeric(8,2),
 quality_status text NOT NULL DEFAULT 'UNVERIFIED'
   CHECK(quality_status IN ('UNVERIFIED','VERIFIED','REJECTED')),
 source_reference text,
 raw_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(weather_location_id,observed_at,evidence_class,source_code)
);
CREATE INDEX IF NOT EXISTS ix_weather_observations_location_time
 ON weather_observations(weather_location_id,observed_at DESC);

CREATE TABLE IF NOT EXISTS weather_forecast_verifications (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 weather_location_id uuid NOT NULL REFERENCES weather_locations(id),
 model_code text NOT NULL,
 fetch_run_id uuid REFERENCES weather_fetch_runs(id) ON DELETE SET NULL,
 valid_at timestamptz NOT NULL,
 lead_hours numeric(8,2),
 forecast_precipitation_mm numeric(10,3),
 observed_precipitation_mm numeric(10,3),
 event_threshold_mm numeric(10,3) NOT NULL DEFAULT 0.1,
 event_forecast boolean,
 event_observed boolean,
 absolute_error_mm numeric(10,3),
 observation_id uuid REFERENCES weather_observations(id) ON DELETE SET NULL,
 verification_status text NOT NULL DEFAULT 'PENDING'
   CHECK(verification_status IN ('PENDING','VERIFIED','REJECTED')),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(fetch_run_id,valid_at,observation_id)
);
CREATE INDEX IF NOT EXISTS ix_weather_verifications_skill
 ON weather_forecast_verifications(weather_location_id,model_code,valid_at DESC);

CREATE TABLE IF NOT EXISTS weather_model_skill (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 weather_location_id uuid NOT NULL REFERENCES weather_locations(id),
 model_code text NOT NULL,
 lead_bucket text NOT NULL,
 metric_code text NOT NULL,
 sample_count integer NOT NULL CHECK(sample_count>=0),
 metric_value numeric(14,6),
 reliability_status text NOT NULL
   CHECK(reliability_status IN ('INSUFFICIENT_HISTORY','AVAILABLE')),
 calculated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(weather_location_id,model_code,lead_bucket,metric_code)
);

CREATE TABLE IF NOT EXISTS weather_refresh_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 weather_location_id uuid NOT NULL REFERENCES weather_locations(id),
 refresh_kind text NOT NULL CHECK(refresh_kind IN ('DETERMINISTIC','ENSEMBLE','OBSERVATION','ALL')),
 started_at timestamptz NOT NULL DEFAULT now(),
 completed_at timestamptz,
 successful_sources integer NOT NULL DEFAULT 0,
 failed_sources integer NOT NULL DEFAULT 0,
 status text NOT NULL CHECK(status IN ('RUNNING','SUCCESS','DEGRADED','FAILED')),
 details jsonb NOT NULL DEFAULT '{}'::jsonb
);

ALTER TABLE weather_consensus_assessments ADD COLUMN IF NOT EXISTS deterministic_rain_support_pct numeric(6,3);
ALTER TABLE weather_consensus_assessments ADD COLUMN IF NOT EXISTS ensemble_precipitation_probability_pct numeric(6,3);
ALTER TABLE weather_consensus_assessments ADD COLUMN IF NOT EXISTS confidence_class text;
ALTER TABLE weather_consensus_assessments ADD COLUMN IF NOT EXISTS freshness_status text;
ALTER TABLE weather_consensus_assessments ADD COLUMN IF NOT EXISTS local_reliability_status text NOT NULL DEFAULT 'INSUFFICIENT_HISTORY';
ALTER TABLE weather_consensus_assessments ADD COLUMN IF NOT EXISTS ensemble_evidence jsonb NOT NULL DEFAULT '[]'::jsonb;

DO $$ BEGIN
 ALTER TABLE weather_consensus_assessments ADD CONSTRAINT ck_weather_confidence_class
 CHECK(confidence_class IS NULL OR confidence_class IN ('HIGH','MEDIUM','LOW','INSUFFICIENT_DATA'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
 ALTER TABLE weather_consensus_assessments ADD CONSTRAINT ck_weather_freshness
 CHECK(freshness_status IS NULL OR freshness_status IN ('FRESH','AGING','STALE','INSUFFICIENT_DATA'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
 ALTER TABLE weather_consensus_assessments ADD CONSTRAINT ck_weather_local_reliability
 CHECK(local_reliability_status IN ('INSUFFICIENT_HISTORY','AVAILABLE'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- No agronomic spray/rainfast thresholds are activated here. Unknown remains unknown.
INSERT INTO weather_rule_packs(code,version,name_en,name_mr,operation_type,rules,evidence_reference,verification_status,active)
VALUES
 ('MET_EVENT_CLASSIFICATION',1,'Meteorological precipitation event classification','हवामान पर्जन्य घटना वर्गीकरण','GENERAL',
  '{"measurable_precipitation_mm_per_hour":0.1}'::jsonb,
  'Open-Meteo precipitation probability definition: >0.1 mm in preceding hour','VERIFIED',true),
 ('SPRAY_OPERATION_POLICY',1,'Spray operational weather policy','फवारणी कार्य हवामान धोरण','SPRAY',
  '{}'::jsonb,NULL,'UNVERIFIED',false)
ON CONFLICT(code,version) DO NOTHING;

COMMIT;
