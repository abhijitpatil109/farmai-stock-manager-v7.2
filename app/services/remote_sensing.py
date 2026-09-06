from __future__ import annotations
import hashlib,json
from datetime import datetime
from ..db import connection
from .activity_register import ActivityRegisterNotFound,ActivityRegisterValidation
from .geospatial import get_active_geometry
from .sentinel2_provider import CdseStacClient,SentinelHubStatsClient,ProviderError,ALGORITHM_VERSION,fingerprint,canonical_json,parse_stats_response

def _j(v):return json.dumps(v,default=str,separators=(",",":"))
def _provider(c,code):
    r=c.execute("SELECT * FROM public.remote_sensing_providers WHERE provider_code=%s AND active=true",(code,)).fetchone()
    if not r: raise ActivityRegisterValidation(f"Remote sensing provider {code} unavailable.")
    return r
def _rule(c,code):
    r=c.execute("""SELECT * FROM public.remote_sensing_rule_packs WHERE rule_code=%s
      AND active=true AND verification_status='VERIFIED' ORDER BY version DESC LIMIT 1""",(code,)).fetchone()
    if not r: raise ActivityRegisterValidation(f"Verified active rule {code} unavailable.")
    return r
def _cycle(c,plot_id,d):
    """Resolve the most recent crop cycle whose operational baseline has started.

    Activity Register crop_cycles does not define an end_date column. Remote sensing
    evidence remains plot-level first; this resolver only supplies an optional crop
    cycle context using canonical baseline fields already present in the domain model.
    """
    return c.execute("""SELECT * FROM public.crop_cycles WHERE plot_id=%s
      AND COALESCE(dap_baseline_date,planting_date)<=%s
      ORDER BY COALESCE(dap_baseline_date,planting_date) DESC,created_at DESC LIMIT 1""",
      (plot_id,d)).fetchone()

def discover_scenes(plot_id,date_from,date_to,max_cloud_cover_pct=80,limit=20):
    geom=get_active_geometry(plot_id); client=CdseStacClient()
    with connection() as c:
      provider=_provider(c,"CDSE_STAC")
      fp=fingerprint({"op":"discover","plot":str(plot_id),"geometry":geom["geometry_hash"],"from":date_from,
                      "to":date_to,"cloud":max_cloud_cover_pct,"limit":limit})
      run=c.execute("""INSERT INTO public.remote_sensing_fetch_runs(
        provider_id,plot_id,operation,request_fingerprint,status,requested_from,requested_to)
        VALUES(%s,%s,'DISCOVER',%s,'STARTED',%s,%s) RETURNING id""",
        (provider["id"],plot_id,fp,date_from,date_to)).fetchone()
      try:
        _,features,_=client.discover(geom["geojson"],date_from,date_to,max_cloud_cover_pct,limit); out=[]
        for f in features:
            p=f.get("properties") or {}; dt=p.get("datetime") or p.get("start_datetime")
            if not dt: continue
            acquired=datetime.fromisoformat(dt.replace("Z","+00:00"))
            row=c.execute("""INSERT INTO public.remote_sensing_scenes(
              provider_id,provider_scene_id,collection_code,platform,acquired_at,source_created_at,
              processing_level,processing_version,cloud_cover_pct,bbox,scene_geometry,assets,raw_metadata)
              VALUES(%s,%s,%s,%s,%s,%s,'L2A',%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb)
              ON CONFLICT(provider_id,provider_scene_id) DO UPDATE SET
                cloud_cover_pct=excluded.cloud_cover_pct,raw_metadata=excluded.raw_metadata,retrieved_at=now()
              RETURNING *""",(provider["id"],f["id"],f.get("collection") or "sentinel-2-l2a",p.get("platform"),
              acquired,p.get("created"),str(p.get("processing:version") or ""),p.get("eo:cloud_cover"),
              _j(f.get("bbox")),_j(f.get("geometry")),_j(f.get("assets") or {}),_j(f))).fetchone()
            c.execute("""INSERT INTO public.remote_sensing_scene_plot_links(scene_id,plot_geometry_id)
              VALUES(%s,%s) ON CONFLICT DO NOTHING""",(row["id"],geom["id"]))
            out.append(dict(row))
        c.execute("""UPDATE public.remote_sensing_fetch_runs SET status='SUCCESS',records_received=%s,
          finished_at=now() WHERE id=%s""",(len(out),run["id"])); c.commit()
        return {"request_fingerprint":fp,"count":len(out),"scenes":out}
      except ProviderError as e:
        c.execute("""UPDATE public.remote_sensing_fetch_runs SET status='FAILED',error_code=%s,error_message=%s,
          http_status=%s,finished_at=now() WHERE id=%s""",(e.code,str(e),e.http_status,run["id"])); c.commit()
        raise ActivityRegisterValidation(str(e)) from e
      except Exception:c.rollback();raise

def _quality(q,policy):
    valid=q.get("valid_pixel_pct"); cloud=q.get("cloud_pixel_pct"); shadow=q.get("shadow_pixel_pct")
    if valid is None:return "DATA_UNAVAILABLE",["VALID_PIXEL_PERCENT_UNKNOWN"]
    if valid<float(policy["partial_min_pct"]):return "INSUFFICIENT_VALID_PIXELS",["LOW_VALID_PIXEL_PERCENT"]
    if cloud is not None and cloud>=float(policy["cloud_high_pct"]):return "CLOUD_CONTAMINATED",["HIGH_CLOUD_PIXEL_PERCENT"]
    if shadow is not None and shadow>=float(policy["shadow_high_pct"]):return "SHADOW_CONTAMINATED",["HIGH_SHADOW_PIXEL_PERCENT"]
    if valid<float(policy["valid_min_pct"]):return "PARTIAL",["PARTIAL_VALID_PIXEL_COVERAGE"]
    return "VALID",[]

def process_scene_for_plot(plot_id,scene_id,analysis_scope="AUTO"):
    geom=get_active_geometry(plot_id)
    with connection() as c:
      scene=c.execute("SELECT * FROM public.remote_sensing_scenes WHERE id=%s",(scene_id,)).fetchone()
      if not scene:raise ActivityRegisterNotFound("Remote sensing scene not found.")
      provider=_provider(c,"CDSE_SENTINEL_HUB"); qrule=_rule(c,"S2_L2A_QUALITY_POLICY")
      scope=("INTERIOR_POLYGON" if geom.get("interior_geojson") else "FULL_POLYGON") if analysis_scope=="AUTO" else analysis_scope
      gj=geom.get("interior_geojson") if scope=="INTERIOR_POLYGON" else geom["geojson"]
      if not gj:raise ActivityRegisterValidation("Requested interior geometry unavailable.")
      fp=fingerprint({"scene":scene["provider_scene_id"],"plot":str(plot_id),"geometry":geom["geometry_hash"],
                      "scope":scope,"algorithm":ALGORITHM_VERSION})
      ex=c.execute("SELECT * FROM public.plot_remote_observations WHERE request_fingerprint=%s",(fp,)).fetchone()
      if ex:return {"duplicate":True,"observation_id":str(ex["id"]),"quality_status":ex["quality_status"]}
      run=c.execute("""INSERT INTO public.remote_sensing_fetch_runs(provider_id,plot_id,operation,request_fingerprint,
        status,requested_from,requested_to) VALUES(%s,%s,'STATISTICS',%s,'STARTED',%s,%s) RETURNING id""",
        (provider["id"],plot_id,fp,scene["acquired_at"],scene["acquired_at"])).fetchone()
      try:
        _,raw=SentinelHubStatsClient().stats(gj,scene["acquired_at"]); parsed=parse_stats_response(raw)
        qs,reasons=_quality(parsed["quality"],qrule["rule_payload"]); cycle=_cycle(c,plot_id,scene["acquired_at"].date())
        obs=c.execute("""INSERT INTO public.plot_remote_observations(
          plot_id,crop_cycle_id,plot_geometry_id,scene_id,processing_provider_id,acquired_at,analysis_scope,
          output_grid_resolution_m,native_resolution_metadata,valid_pixel_pct,cloud_pixel_pct,shadow_pixel_pct,
          vegetation_pixel_pct,quality_status,quality_reasons,algorithm_version,request_fingerprint,
          provider_payload_hash,raw_summary)
          VALUES(%s,%s,%s,%s,%s,%s,%s,10,%s::jsonb,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb) RETURNING *""",
          (plot_id,cycle["id"] if cycle else None,geom["id"],scene["id"],provider["id"],scene["acquired_at"],scope,
           _j({"B04":10,"B08":10,"B05":20,"B11":20,"derived_output_grid_m":10}),
           parsed["quality"].get("valid_pixel_pct"),parsed["quality"].get("cloud_pixel_pct"),
           parsed["quality"].get("shadow_pixel_pct"),parsed["quality"].get("vegetation_pixel_pct"),
           qs,_j(reasons),ALGORITHM_VERSION,fp,hashlib.sha256(canonical_json(raw).encode()).hexdigest(),
           _j({"interval":parsed.get("interval")}))).fetchone()
        for code,st in parsed["indices"].items():
            c.execute("""INSERT INTO public.plot_index_statistics(
              observation_id,index_code,min_value,max_value,mean_value,median_value,stddev_value,p10_value,p90_value,sample_count,nodata_count)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
              (obs["id"],code,st["min"],st["max"],st["mean"],st["median"],st["stddev"],st["p10"],st["p90"],st["sample_count"],st["nodata_count"]))
            if cycle and qs in ("VALID","PARTIAL") and st["mean"] is not None:
                baseline=cycle["dap_baseline_date"] or cycle["planting_date"]; dap=(scene["acquired_at"].date()-baseline).days if baseline else None
                c.execute("""INSERT INTO public.season_metric_series(
                 crop_cycle_id,metric_code,metric_date,dap,value,unit,source_type,source_reference,quality_status,metadata)
                 VALUES(%s,%s,%s,%s,%s,'INDEX','REMOTE_SENSING',%s,%s,%s::jsonb) ON CONFLICT DO NOTHING""",
                 (cycle["id"],code,scene["acquired_at"].date(),dap,st["mean"],str(obs["id"]),qs,_j({"algorithm":ALGORITHM_VERSION})))
        c.execute("UPDATE public.remote_sensing_fetch_runs SET status='SUCCESS',records_received=1,finished_at=now() WHERE id=%s",(run["id"],));c.commit()
        return {"duplicate":False,"observation_id":str(obs["id"]),"quality_status":qs,"quality":parsed["quality"],"indices":parsed["indices"],"analysis_scope":scope}
      except ProviderError as e:
        c.execute("""UPDATE public.remote_sensing_fetch_runs SET status='FAILED',error_code=%s,error_message=%s,
          http_status=%s,finished_at=now() WHERE id=%s""",(e.code,str(e),e.http_status,run["id"]));c.commit()
        raise ActivityRegisterValidation(str(e)) from e
      except Exception:c.rollback();raise

def refresh_plot(plot_id,date_from,date_to,max_cloud_cover_pct=80,max_scenes=3,analysis_scope="AUTO"):
    d=discover_scenes(plot_id,date_from,date_to,max_cloud_cover_pct,max_scenes); results=[]
    for s in d["scenes"][:max_scenes]:
        try:results.append(process_scene_for_plot(plot_id,s["id"],analysis_scope))
        except ActivityRegisterValidation as e:results.append({"scene_id":str(s["id"]),"status":"FAILED","error":str(e)})
    return {"plot_id":str(plot_id),"discovery_count":d["count"],"processed":results}

def latest(plot_id):
    with connection() as c:
      r=c.execute("""SELECT o.*,s.provider_scene_id,s.platform,
        COALESCE(jsonb_object_agg(i.index_code,jsonb_build_object('mean',i.mean_value,'median',i.median_value,
        'stddev',i.stddev_value,'p10',i.p10_value,'p90',i.p90_value)) FILTER(WHERE i.id IS NOT NULL),'{}'::jsonb) indices
        FROM public.plot_remote_observations o LEFT JOIN public.remote_sensing_scenes s ON s.id=o.scene_id
        LEFT JOIN public.plot_index_statistics i ON i.observation_id=o.id WHERE o.plot_id=%s
        GROUP BY o.id,s.provider_scene_id,s.platform ORDER BY o.acquired_at DESC LIMIT 1""",(plot_id,)).fetchone()
    return dict(r) if r else None

def timeline(plot_id,limit=50):
    with connection() as c:
      return [dict(x) for x in c.execute("""SELECT o.id,o.acquired_at,o.analysis_scope,o.quality_status,
        o.valid_pixel_pct,o.cloud_pixel_pct,o.shadow_pixel_pct,o.vegetation_pixel_pct,
        jsonb_object_agg(i.index_code,jsonb_build_object('mean',i.mean_value,'median',i.median_value))
          FILTER(WHERE i.id IS NOT NULL) indices
        FROM public.plot_remote_observations o LEFT JOIN public.plot_index_statistics i ON i.observation_id=o.id
        WHERE o.plot_id=%s GROUP BY o.id ORDER BY o.acquired_at DESC LIMIT %s""",(plot_id,limit)).fetchall()]

def remote_sensing_context_for_crop_cycle(crop_cycle_id):
    with connection() as c:
      latest_row=c.execute("""SELECT o.id,o.acquired_at,o.quality_status,
        jsonb_object_agg(i.index_code,jsonb_build_object('mean',i.mean_value,'median',i.median_value)) indices
        FROM public.plot_remote_observations o LEFT JOIN public.plot_index_statistics i ON i.observation_id=o.id
        WHERE o.crop_cycle_id=%s GROUP BY o.id ORDER BY o.acquired_at DESC LIMIT 1""",(crop_cycle_id,)).fetchone()
      anomalies=[dict(x) for x in c.execute("""SELECT id,metric_code,anomaly_type,severity,confidence,status,created_at
        FROM public.remote_sensing_anomalies WHERE crop_cycle_id=%s AND status IN ('OPEN','SCOUTING','VERIFIED')
        ORDER BY created_at DESC LIMIT 10""",(crop_cycle_id,)).fetchall()]
      scouting=[dict(x) for x in c.execute("""SELECT id,status,priority,title_en,title_mr,due_date,anomaly_id
        FROM public.scouting_tasks WHERE crop_cycle_id=%s AND status<>'DISMISSED' ORDER BY created_at DESC LIMIT 10""",(crop_cycle_id,)).fetchall()]
    return {"status":"AVAILABLE" if latest_row else "NO_REMOTE_OBSERVATION","latest":dict(latest_row) if latest_row else None,
            "active_anomalies":anomalies,"scouting":scouting,
            "guardrail":"Remote sensing is evidence, not diagnosis or execution authority."}
