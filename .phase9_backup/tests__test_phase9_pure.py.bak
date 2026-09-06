import unittest
from pathlib import Path
from app.services.geospatial import parse_kml,OVERLAP_TOLERANCE_M2
from app.services.sentinel2_provider import ALGORITHM_VERSION,COLLECTION,STAC_SEARCH_URL,STATS_URL,EVALSCRIPT,fingerprint,parse_stats_response,ProviderError

class GeometryTests(unittest.TestCase):
    def test_authoritative_kml(self):
        rows=parse_kml(Path("evidence/FarmAI_Bendri_Geometry_v1.kml").read_bytes())
        self.assertEqual({r["plot_code"] for r in rows},{"PLOT-001","PLOT-002","PLOT-003","PLOT-004","PLOT-005"})
        for r in rows:
            ring=r["geojson"]["coordinates"][0][0]
            self.assertEqual(ring[0],ring[-1])
            self.assertGreaterEqual(len(set(map(tuple,ring[:-1]))),3)
    def test_overlap_tolerance(self):
        self.assertGreater(OVERLAP_TOLERANCE_M2,16.9)
        self.assertLessEqual(OVERLAP_TOLERANCE_M2,25.0)

class ProviderTests(unittest.TestCase):
    def test_endpoints_and_version(self):
        self.assertEqual(ALGORITHM_VERSION,"9.0.0")
        self.assertEqual(COLLECTION,"sentinel-2-l2a")
        self.assertIn("stac.dataspace.copernicus.eu/v1/search",STAC_SEARCH_URL)
        self.assertIn("statistics/v1",STATS_URL)
    def test_fingerprint_stable(self):
        self.assertEqual(fingerprint({"a":1,"b":2}),fingerprint({"b":2,"a":1}))
    def test_evalscript_guardrails(self):
        for t in ("NDVI","NDRE","NDMI","SCL==3","SCL==8","SCL==9","SCL==10","denomOk","dataMask"):
            self.assertIn(t,EVALSCRIPT)
    def test_recorded_stats_fixture(self):
        body={"status":"OK","data":[{"interval":{"from":"x","to":"y"},"outputs":{
          "indices":{"bands":{
           "NDVI":{"stats":{"min":.1,"max":.8,"mean":.5,"stDev":.1,"sampleCount":10,"noDataCount":0,"percentiles":{"10.0":.2,"50.0":.5,"90.0":.7}}},
           "NDRE":{"stats":{"min":.1,"max":.6,"mean":.4,"stDev":.1,"sampleCount":10,"noDataCount":0,"percentiles":{"10.0":.2,"50.0":.4,"90.0":.5}}},
           "NDMI":{"stats":{"min":-.1,"max":.5,"mean":.2,"stDev":.1,"sampleCount":10,"noDataCount":0,"percentiles":{"10.0":0,"50.0":.2,"90.0":.4}}}}},
          "quality":{"bands":{"VALID":{"stats":{"mean":.8}},"CLOUD":{"stats":{"mean":.1}},"SHADOW":{"stats":{"mean":.05}},"VEGETATION":{"stats":{"mean":.7}}}}
        }}]}
        x=parse_stats_response(body)
        self.assertEqual(x["indices"]["NDVI"]["median"],.5)
        self.assertAlmostEqual(x["quality"]["valid_pixel_pct"],80)
    def test_missing_index_rejected(self):
        with self.assertRaises(ProviderError):
            parse_stats_response({"data":[{"outputs":{"indices":{"bands":{}}}}]})

class AuthorityBoundaryTests(unittest.TestCase):
    def test_no_stock_mutation(self):
        for f in ("remote_sensing.py","remote_anomaly.py","scouting.py","geospatial.py","season_intelligence.py"):
            s=(Path("app/services")/f).read_text().lower()
            self.assertNotIn("insert into public.stock_transactions",s)
            self.assertNotIn("update public.stock_transactions",s)
    def test_db_prevents_satellite_diagnosis(self):
        s=Path("database/010_phase9_remote_sensing.sql").read_text()
        self.assertIn("ck_rs_anomaly_no_diagnosis",s)
        self.assertIn("diagnosis IS NULL",s)
    def test_anomaly_thresholds_from_rulepack(self):
        s=Path("app/services/remote_anomaly.py").read_text()
        self.assertIn('p["z_threshold"]',s)
        self.assertIn('p["min_relative_change_pct"]',s)

if __name__=="__main__":unittest.main()
