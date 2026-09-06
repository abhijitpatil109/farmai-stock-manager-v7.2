import unittest
from datetime import datetime,timezone
from app.schemas.weather_intelligence import OperationalWeatherCheckRequest

class Phase8ContractTests(unittest.TestCase):
    def test_timezone_required(self):
        with self.assertRaises(Exception):
            OperationalWeatherCheckRequest(farm_id="00000000-0000-0000-0000-000000000001",operation_type="SPRAY",planned_start=datetime(2026,9,6,8),expected_duration_minutes=120)
    def test_aware_time_accepted(self):
        x=OperationalWeatherCheckRequest(farm_id="00000000-0000-0000-0000-000000000001",operation_type="SPRAY",planned_start=datetime(2026,9,6,8,tzinfo=timezone.utc),expected_duration_minutes=120)
        self.assertEqual(x.operation_type,"SPRAY")


class Phase8ScientificGuardrailTests(unittest.TestCase):
    def test_rain_threshold_is_amount_not_probability(self):
        from app.services.external_weather import RAIN_THRESHOLD_MM
        self.assertGreater(RAIN_THRESHOLD_MM, 0)
        self.assertLess(RAIN_THRESHOLD_MM, 1)

    def test_engine_version_is_phase8_1(self):
        from app.services.external_weather import ENGINE_VERSION
        self.assertEqual(ENGINE_VERSION, "8.1.0")

    def test_provider_models_are_independent_named_families(self):
        from app.services.external_weather import MODEL_ENDPOINTS
        self.assertEqual(set(MODEL_ENDPOINTS), {"ECMWF_IFS", "GFS", "ICON"})
        self.assertEqual(len(set(MODEL_ENDPOINTS.values())), 3)

    def test_hourly_contract_does_not_claim_subhour_precision(self):
        from app.services.external_weather import HOURLY
        self.assertIn("precipitation", HOURLY)
        self.assertNotIn("minutely", HOURLY.lower())

if __name__=="__main__": unittest.main()
