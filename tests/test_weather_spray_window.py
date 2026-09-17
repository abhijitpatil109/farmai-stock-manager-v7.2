import unittest
from datetime import datetime, time, timezone

from app.main import app
from app.schemas.weather_intelligence import SprayWindowConsultRequest
from app.services.external_weather import (
    _evaluate_spray_candidate,
    _non_overlapping_ranked,
    _select_active_farm,
)


class SprayWindowSchemaTests(unittest.TestCase):
    def test_natural_request_does_not_require_ids_or_coordinates(self):
        req = SprayWindowConsultRequest(
            farm_name="Bendri",
            crop_name="Drumstick",
            target_day="TOMORROW",
        )
        self.assertIsNone(req.farm_id)
        self.assertIsNone(req.crop_cycle_id)
        self.assertEqual(req.target_day, "TOMORROW")
        self.assertTrue(req.refresh_before_assessment)

    def test_invalid_local_window_is_rejected(self):
        with self.assertRaises(ValueError):
            SprayWindowConsultRequest(
                earliest_local_time=time(18, 0),
                latest_local_time=time(6, 0),
            )

    def test_gpt_operation_is_exposed_with_mandatory_routing_description(self):
        operation = app.openapi()["paths"]["/api/v1/operations/spray-window"]["post"]
        self.assertEqual(operation["operationId"], "getBestOperationalSprayWindow")
        self.assertIn("MANDATORY", operation["description"])
        self.assertIn("Do not ask for coordinates first", operation["description"])


class SprayWindowRankingTests(unittest.TestCase):
    def request(self, **values):
        return SprayWindowConsultRequest(**values)

    def consensus(self, **values):
        base = {
            "freshness_status": "FRESH",
            "model_agreement": "HIGH",
            "ensemble_precipitation_probability_pct": 5,
            "deterministic_rain_support_pct": 0,
            "expected_precipitation_max_mm": 0,
        }
        base.update(values)
        return base

    def metrics(self, **values):
        base = {
            "weather_model_count": 3,
            "max_wind_kmh": 8,
            "max_gust_kmh": 14,
            "max_temperature_c": 28,
            "min_relative_humidity_pct": 55,
        }
        base.update(values)
        return base

    def test_unknown_rainfast_keeps_window_conditional(self):
        decision, rating, reasons = _evaluate_spray_candidate(
            self.consensus(), self.metrics(), self.request()
        )
        self.assertEqual(decision, "CAUTION")
        self.assertGreater(rating, 5)
        self.assertIn("PRODUCT_RAINFAST_UNKNOWN", reasons)

    def test_rain_or_excess_wind_holds_window(self):
        decision, _, reasons = _evaluate_spray_candidate(
            self.consensus(ensemble_precipitation_probability_pct=70),
            self.metrics(max_wind_kmh=20),
            self.request(rainfast_minutes=120),
        )
        self.assertEqual(decision, "HOLD")
        self.assertIn("ENSEMBLE_RAIN_RISK", reasons)
        self.assertIn("WIND_ABOVE_LIMIT", reasons)

    def test_ranker_returns_non_overlapping_windows(self):
        def candidate(hour, decision, rating):
            start = datetime(2026, 9, 18, hour, tzinfo=timezone.utc)
            return {
                "start": start,
                "end": start.replace(hour=hour + 2),
                "decision": decision,
                "rating_10": rating,
            }

        ranked = _non_overlapping_ranked([
            candidate(6, "CAUTION", 8.0),
            candidate(7, "SAFE", 8.5),
            candidate(9, "SAFE", 8.0),
        ])
        self.assertEqual([x["start"].hour for x in ranked], [7, 9])


class FarmIdentityResolutionTests(unittest.TestCase):
    def farms(self):
        return [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name_en": "Bendri Farm",
                "name_mr": "बेंद्री",
                "active": True,
            }
        ]

    def test_farm_id_takes_priority_over_display_name(self):
        farm, mode = _select_active_farm(
            self.farms(),
            farm_id="11111111-1111-1111-1111-111111111111",
            farm_name="Bendri",
        )
        self.assertEqual(farm["name_en"], "Bendri Farm")
        self.assertEqual(mode, "FARM_ID")

    def test_unique_normalized_name_accepts_bendri_alias(self):
        farm, mode = _select_active_farm(self.farms(), farm_name=" Bendri ")
        self.assertEqual(farm["name_mr"], "बेंद्री")
        self.assertEqual(mode, "UNIQUE_NORMALIZED_NAME")

    def test_single_active_farm_is_safe_fallback(self):
        farm, mode = _select_active_farm(self.farms(), farm_name="Our farm")
        self.assertEqual(farm["id"], "11111111-1111-1111-1111-111111111111")
        self.assertEqual(mode, "SINGLE_ACTIVE_FARM_FALLBACK")

    def test_multiple_active_farms_never_use_unsafe_fallback(self):
        farms = self.farms() + [{
            "id": "22222222-2222-2222-2222-222222222222",
            "name_en": "Other Farm",
            "name_mr": "दुसरे शेत",
            "active": True,
        }]
        with self.assertRaises(Exception):
            _select_active_farm(farms, farm_name="Unknown")


if __name__ == "__main__":
    unittest.main()
