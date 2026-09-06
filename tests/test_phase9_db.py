import os,unittest
from app.db import connection
@unittest.skipUnless(os.getenv("DATABASE_URL"),"DATABASE_URL required")
class DBTests(unittest.TestCase):
    def test_phase9_tables(self):
        required={"plot_geometries","remote_sensing_providers","remote_sensing_fetch_runs","remote_sensing_scenes",
        "remote_sensing_scene_plot_links","remote_sensing_rule_packs","plot_remote_observations","plot_index_statistics",
        "remote_sensing_anomalies","remote_sensing_anomaly_zones","scouting_tasks","scouting_observations","scouting_media",
        "season_metric_series","season_comparisons","intelligence_remote_evidence"}
        with connection() as c:
            self.assertTrue(c.execute("SELECT 1 FROM pg_extension WHERE extname='postgis'").fetchone())
            rows=c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name=ANY(%s)",(list(required),)).fetchall()
            self.assertEqual({x["table_name"] for x in rows},required)
    def test_rule_integrity(self):
        with connection() as c:
            n=c.execute("SELECT count(*) n FROM public.remote_sensing_rule_packs WHERE active=true AND verification_status<>'VERIFIED'").fetchone()["n"]
            self.assertEqual(n,0)
    def test_five_bendri_geometries(self):
        with connection() as c:
            rows=c.execute("""SELECT p.code,pg.calculated_area_acres,ST_IsValid(pg.geom) valid
              FROM public.plot_geometries pg JOIN public.plots p ON p.id=pg.plot_id
              WHERE pg.active=true AND p.code=ANY(%s)""",(["PLOT-001","PLOT-002","PLOT-003","PLOT-004","PLOT-005"],)).fetchall()
            self.assertEqual(len(rows),5)
            self.assertTrue(all(r["valid"] and float(r["calculated_area_acres"])>0 for r in rows))
if __name__=="__main__":unittest.main()
