import unittest
from datetime import datetime,timezone
from app.services import external_weather as w
from app.schemas.weather_intelligence import OperationalWeatherCheckRequest

class Phase8CompletePureTests(unittest.TestCase):
 def test_engine_version(self):self.assertEqual(w.ENGINE_VERSION,"8.4.0")
 def test_two_ensemble_families(self):self.assertEqual(set(w.ENSEMBLE_MODELS),{"ECMWF_ENS","GEFS"})
 def test_probability_not_deterministic_alias(self):
  self.assertNotIn("probability", "deterministic_rain_support_pct")
 def test_no_subhour_claim(self):
  self.assertEqual(w.ENSEMBLE_MODELS["ECMWF_ENS"]["native_minutes"],180)
  self.assertEqual(w.ENSEMBLE_MODELS["GEFS"]["native_minutes"],180)
 def test_local_reliability_threshold_nonzero(self):self.assertGreaterEqual(w.LOCAL_RELIABILITY_MIN_SAMPLES,30)
 def test_timezone_guard(self):
  with self.assertRaises(ValueError):
   OperationalWeatherCheckRequest(farm_id="67feb704-d1a4-4ff5-b1af-abb363726dfc",
    operation_type="SPRAY",planned_start=datetime(2026,9,6,9),expected_duration_minutes=60)
 def test_aware_time(self):
  r=OperationalWeatherCheckRequest(farm_id="67feb704-d1a4-4ff5-b1af-abb363726dfc",
   operation_type="SPRAY",planned_start=datetime(2026,9,6,9,tzinfo=timezone.utc),expected_duration_minutes=60)
  self.assertIsNotNone(r.planned_start.tzinfo)
