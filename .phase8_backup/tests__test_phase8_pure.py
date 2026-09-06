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
if __name__=="__main__": unittest.main()
