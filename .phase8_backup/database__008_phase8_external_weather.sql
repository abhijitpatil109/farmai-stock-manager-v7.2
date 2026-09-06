BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS external_data_providers (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL UNIQUE, name text NOT NULL,
 provider_type text NOT NULL CHECK(provider_type IN ('WEATHER_AGGREGATOR','WEATHER_AGENCY','RADAR','SATELLITE','SENSOR','ADVISORY','MARKET')),
 commercial_use_status text NOT NULL DEFAULT 'REVIEW_REQUIRED' CHECK(commercial_use_status IN ('NON_COMMERCIAL','COMMERCIAL','OPEN_DATA','REVIEW_REQUIRED')),
 attribution_text text, active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS weather_locations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), farm_id uuid NOT NULL REFERENCES farms(id), plot_id uuid NULL REFERENCES plots(id),
 latitude numeric(9,6) NOT NULL CHECK(latitude BETWEEN -90 AND 90), longitude numeric(9,6) NOT NULL CHECK(longitude BETWEEN -180 AND 180),
 timezone text NOT NULL DEFAULT 'Asia/Kolkata', elevation_m numeric(8,2), source text NOT NULL DEFAULT 'MANUAL' CHECK(source IN ('MANUAL','GPS','GEOCODED','IMPORT')),
 active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(farm_id,plot_id));
CREATE UNIQUE INDEX IF NOT EXISTS ux_weather_locations_farm_default ON weather_locations(farm_id) WHERE plot_id IS NULL AND active=true;

CREATE TABLE IF NOT EXISTS weather_fetch_runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), provider_id uuid NOT NULL REFERENCES external_data_providers(id), weather_location_id uuid NOT NULL REFERENCES weather_locations(id),
 model_code text NOT NULL, model_family text, run_reference text, requested_at timestamptz NOT NULL DEFAULT now(), retrieved_at timestamptz,
 valid_from timestamptz, valid_to timestamptz, temporal_resolution_minutes integer CHECK(temporal_resolution_minutes > 0),
 temporal_resolution_type text NOT NULL DEFAULT 'NATIVE' CHECK(temporal_resolution_type IN ('NATIVE','INTERPOLATED','MIXED','UNKNOWN')),
 status text NOT NULL CHECK(status IN ('PENDING','SUCCESS','PARTIAL','FAILED')), http_status integer, error_code text, error_message text,
 request_fingerprint text NOT NULL, response_hash text, raw_payload jsonb, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(provider_id,weather_location_id,model_code,request_fingerprint));
CREATE INDEX IF NOT EXISTS ix_weather_fetch_runs_location_retrieved ON weather_fetch_runs(weather_location_id,retrieved_at DESC);

CREATE TABLE IF NOT EXISTS weather_data_points (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), fetch_run_id uuid NOT NULL REFERENCES weather_fetch_runs(id) ON DELETE CASCADE,
 valid_at timestamptz NOT NULL, precipitation_mm numeric(10,3), precipitation_probability_pct numeric(6,3) CHECK(precipitation_probability_pct BETWEEN 0 AND 100),
 temperature_c numeric(6,2), relative_humidity_pct numeric(6,2) CHECK(relative_humidity_pct BETWEEN 0 AND 100), wind_speed_kmh numeric(8,2), wind_gust_kmh numeric(8,2),
 weather_code integer, source_semantics jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(fetch_run_id,valid_at));
CREATE INDEX IF NOT EXISTS ix_weather_points_run_valid ON weather_data_points(fetch_run_id,valid_at);

CREATE TABLE IF NOT EXISTS weather_consensus_assessments (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), weather_location_id uuid NOT NULL REFERENCES weather_locations(id), assessed_at timestamptz NOT NULL DEFAULT now(),
 window_start timestamptz NOT NULL, window_end timestamptz NOT NULL CHECK(window_end>window_start), model_count integer NOT NULL CHECK(model_count>=0),
 model_agreement text NOT NULL CHECK(model_agreement IN ('HIGH','MEDIUM_HIGH','MEDIUM','LOW','INSUFFICIENT_DATA')),
 forecast_confidence_pct numeric(6,3) CHECK(forecast_confidence_pct BETWEEN 0 AND 100), precipitation_probability_pct numeric(6,3) CHECK(precipitation_probability_pct BETWEEN 0 AND 100),
 expected_precipitation_min_mm numeric(10,3), expected_precipitation_max_mm numeric(10,3), most_likely_rain_start timestamptz, most_likely_rain_end timestamptz,
 timing_confidence text NOT NULL CHECK(timing_confidence IN ('HIGH','MEDIUM','LOW','INSUFFICIENT_DATA')), evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
 engine_version text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS ix_weather_consensus_location_window ON weather_consensus_assessments(weather_location_id,window_start,window_end);

CREATE TABLE IF NOT EXISTS weather_operational_assessments (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), crop_cycle_id uuid REFERENCES crop_cycles(id), activity_id uuid REFERENCES activities(id), weather_location_id uuid NOT NULL REFERENCES weather_locations(id),
 operation_type text NOT NULL CHECK(operation_type IN ('SPRAY','FERTIGATION','IRRIGATION','OTHER')), planned_start timestamptz NOT NULL,
 expected_duration_minutes integer NOT NULL CHECK(expected_duration_minutes>0), rainfast_minutes integer CHECK(rainfast_minutes>=0), safety_buffer_minutes integer NOT NULL DEFAULT 30 CHECK(safety_buffer_minutes>=0),
 required_safe_until timestamptz NOT NULL, decision text NOT NULL CHECK(decision IN ('SAFE','CAUTION','HOLD','INSUFFICIENT_DATA')),
 reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb, consensus_assessment_id uuid REFERENCES weather_consensus_assessments(id), evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
 engine_version text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS intelligence_external_evidence (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), recommendation_id uuid REFERENCES intelligence_recommendations(id) ON DELETE CASCADE,
 evidence_type text NOT NULL, external_entity_type text NOT NULL, external_entity_id uuid NOT NULL, evidence_snapshot jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(recommendation_id,evidence_type,external_entity_type,external_entity_id));

INSERT INTO external_data_providers(code,name,provider_type,commercial_use_status,attribution_text)
VALUES ('OPEN_METEO','Open-Meteo','WEATHER_AGGREGATOR','NON_COMMERCIAL','Weather data by Open-Meteo; underlying model attribution retained per source.')
ON CONFLICT(code) DO UPDATE SET name=EXCLUDED.name, active=true;
COMMIT;
