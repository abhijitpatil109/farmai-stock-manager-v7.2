from __future__ import annotations
import hashlib, json, math, random, time
from datetime import datetime, timedelta, timezone
from statistics import median
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo
from ..db import connection
from .activity_register import ActivityRegisterNotFound, ActivityRegisterValidation

ENGINE_VERSION="8.4.0"
PROVIDER_CODE="OPEN_METEO"
DETERMINISTIC_ENDPOINTS={
 "ECMWF_IFS":"https://api.open-meteo.com/v1/ecmwf",
 "GFS":"https://api.open-meteo.com/v1/gfs",
 "ICON":"https://api.open-meteo.com/v1/dwd-icon",
}
ENSEMBLE_ENDPOINT="https://ensemble-api.open-meteo.com/v1/ensemble"
ENSEMBLE_MODELS={
 "ECMWF_ENS":{"api_model":"ecmwf_ifs025","family":"ECMWF_IFS","native_minutes":180},
 "GEFS":{"api_model":"gfs025","family":"NOAA_GEFS","native_minutes":180},
}
HOURLY="temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,wind_gusts_10m,weather_code"
ENSEMBLE_HOURLY="precipitation"
DEFAULT_EVENT_THRESHOLD_MM=0.1
LOCAL_RELIABILITY_MIN_SAMPLES=30

def _json_default(v):
 if isinstance(v,datetime): return v.isoformat()
 return str(v)

def _get_json(url,timeout=15,retries=3):
 last=None
 for attempt in range(retries):
  req=Request(url,headers={"User-Agent":"FarmAI/8.4 ExternalIntelligence"})
  try:
   with urlopen(req,timeout=timeout) as r:
    return r.status,json.loads(r.read().decode("utf-8"))
  except HTTPError as e:
   last=e
   if e.code not in (429,500,502,503,504): break
  except (URLError,TimeoutError,json.JSONDecodeError) as e: last=e
  if attempt+1<retries: time.sleep(min(4,0.5*(2**attempt))+random.random()*0.15)
 raise ActivityRegisterValidation(f"Weather provider unavailable after retries: {type(last).__name__}")

def _provider(c):
 p=c.execute("SELECT * FROM external_data_providers WHERE code=%s AND active=true",(PROVIDER_CODE,)).fetchone()
 if not p: raise ActivityRegisterValidation("OPEN_METEO provider is not configured.")
 return p

def _location(c,farm_id,plot_id=None):
 if plot_id:
  row=c.execute("SELECT * FROM weather_locations WHERE farm_id=%s AND plot_id=%s AND active=true",(farm_id,plot_id)).fetchone()
  if row:return row
 row=c.execute("SELECT * FROM weather_locations WHERE farm_id=%s AND plot_id IS NULL AND active=true",(farm_id,)).fetchone()
 if not row: raise ActivityRegisterValidation("Weather location is not configured for this farm.")
 return row

def upsert_location(req):
 with connection() as c:
  if not c.execute("SELECT id FROM farms WHERE id=%s",(req.farm_id,)).fetchone():
   raise ActivityRegisterNotFound("Farm not found. (शेत सापडले नाही.)")
  if req.plot_id and not c.execute("SELECT id FROM plots WHERE id=%s AND farm_id=%s",(req.plot_id,req.farm_id)).fetchone():
   raise ActivityRegisterValidation("Plot does not belong to farm.")
  if req.plot_id:
   row=c.execute("""INSERT INTO weather_locations(farm_id,plot_id,latitude,longitude,timezone,elevation_m,source)
    VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(farm_id,plot_id) DO UPDATE SET
    latitude=EXCLUDED.latitude,longitude=EXCLUDED.longitude,timezone=EXCLUDED.timezone,
    elevation_m=EXCLUDED.elevation_m,source=EXCLUDED.source,active=true,updated_at=now() RETURNING *""",
    (req.farm_id,req.plot_id,req.latitude,req.longitude,req.timezone,req.elevation_m,req.source)).fetchone()
  else:
   row=c.execute("SELECT * FROM weather_locations WHERE farm_id=%s AND plot_id IS NULL AND active=true FOR UPDATE",(req.farm_id,)).fetchone()
   if row:
    row=c.execute("""UPDATE weather_locations SET latitude=%s,longitude=%s,timezone=%s,elevation_m=%s,
     source=%s,updated_at=now() WHERE id=%s RETURNING *""",
     (req.latitude,req.longitude,req.timezone,req.elevation_m,req.source,row["id"])).fetchone()
   else:
    row=c.execute("""INSERT INTO weather_locations(farm_id,latitude,longitude,timezone,elevation_m,source)
     VALUES(%s,%s,%s,%s,%s,%s) RETURNING *""",
     (req.farm_id,req.latitude,req.longitude,req.timezone,req.elevation_m,req.source)).fetchone()
  c.commit(); return dict(row)

def _event_threshold(c):
 r=c.execute("""SELECT rules FROM weather_rule_packs WHERE code='MET_EVENT_CLASSIFICATION'
  AND active=true AND verification_status='VERIFIED' ORDER BY version DESC LIMIT 1""").fetchone()
 return float((r["rules"] if r else {}).get("measurable_precipitation_mm_per_hour",DEFAULT_EVENT_THRESHOLD_MM))

def _parse_points(payload,tz_name):
 h=payload.get("hourly") or {}; times=h.get("time") or []; tz=ZoneInfo(tz_name); out=[]
 def val(k,i):
  a=h.get(k) or []; return a[i] if i<len(a) else None
 for i,t in enumerate(times):
  dt=datetime.fromisoformat(t)
  if dt.tzinfo is None:dt=dt.replace(tzinfo=tz)
  out.append({"valid_at":dt,"precipitation_mm":val("precipitation",i),"temperature_c":val("temperature_2m",i),
   "relative_humidity_pct":val("relative_humidity_2m",i),"wind_speed_kmh":val("wind_speed_10m",i),
   "wind_gust_kmh":val("wind_gusts_10m",i),"weather_code":val("weather_code",i)})
 return out

def refresh_weather(farm_id,plot_id=None,forecast_days=3):
 with connection() as c: loc=dict(_location(c,farm_id,plot_id)); provider=dict(_provider(c))
 results=[]; failures=[]
 for model,urlbase in DETERMINISTIC_ENDPOINTS.items():
  params={"latitude":float(loc["latitude"]),"longitude":float(loc["longitude"]),"hourly":HOURLY,
   "timezone":loc["timezone"],"forecast_days":forecast_days,"wind_speed_unit":"kmh","precipitation_unit":"mm"}
  url=urlbase+"?"+urlencode(params)
  try:
   status,payload=_get_json(url); points=_parse_points(payload,loc["timezone"])
   if not points: raise ActivityRegisterValidation("empty provider response")
   raw=json.dumps(payload,sort_keys=True,separators=(",",":")); rh=hashlib.sha256(raw.encode()).hexdigest()
   fp=hashlib.sha256((model+"|"+url+"|"+rh).encode()).hexdigest()
   with connection() as c:
    run=c.execute("""INSERT INTO weather_fetch_runs(provider_id,weather_location_id,model_code,model_family,retrieved_at,
     valid_from,valid_to,temporal_resolution_minutes,delivered_temporal_resolution_minutes,temporal_resolution_type,
     derivation_status,evidence_class,status,http_status,request_fingerprint,response_hash,raw_payload,provider_metadata)
     VALUES(%s,%s,%s,%s,now(),%s,%s,60,60,'NATIVE','NATIVE','FORECAST','SUCCESS',%s,%s,%s,%s::jsonb,%s::jsonb)
     ON CONFLICT(provider_id,weather_location_id,model_code,request_fingerprint) DO UPDATE SET retrieved_at=now()
     RETURNING id""",(provider["id"],loc["id"],model,model,points[0]["valid_at"],points[-1]["valid_at"],
      status,fp,rh,raw,json.dumps({"access_layer":"OPEN_METEO","original_model":model}))).fetchone()
    c.execute("DELETE FROM weather_data_points WHERE fetch_run_id=%s",(run["id"],))
    for p in points:
     c.execute("""INSERT INTO weather_data_points(fetch_run_id,valid_at,precipitation_mm,temperature_c,
      relative_humidity_pct,wind_speed_kmh,wind_gust_kmh,weather_code,source_semantics)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",(run["id"],p["valid_at"],p["precipitation_mm"],
      p["temperature_c"],p["relative_humidity_pct"],p["wind_speed_kmh"],p["wind_gust_kmh"],p["weather_code"],
      json.dumps({"precipitation":"preceding-hour sum","delivered_resolution":"hourly","provider":"OPEN_METEO","model":model})))
    c.commit()
   results.append({"model":model,"points":len(points),"response_hash":rh})
  except Exception as e:
   failures.append({"model":model,"error":str(e)})
 return {"provider":PROVIDER_CODE,"location_id":str(loc["id"]),"models":results,"failures":failures,
  "status":"SUCCESS" if len(results)==3 else "DEGRADED" if len(results)>=2 else "FAILED","engine_version":ENGINE_VERSION}

def _ensemble_members(payload):
 h=payload.get("hourly") or {}; times=h.get("time") or []
 keys=[k for k in h if k=="precipitation" or k.startswith("precipitation_member")]
 if "precipitation" in h and len(keys)==1: keys=[] # ensemble API should expose members; do not fake members from mean.
 members=[]
 for k in keys:
  vals=h.get(k) or []
  if len(vals)==len(times): members.append(vals)
 return times,members

def _quantile(vals,q):
 if not vals:return None
 s=sorted(vals); pos=(len(s)-1)*q; lo=int(math.floor(pos)); hi=int(math.ceil(pos))
 if lo==hi:return s[lo]
 return s[lo]*(hi-pos)+s[hi]*(pos-lo)

def refresh_ensembles(farm_id,plot_id=None,forecast_days=3):
 with connection() as c: loc=dict(_location(c,farm_id,plot_id)); provider=dict(_provider(c)); threshold=_event_threshold(c)
 results=[]; failures=[]
 for code,cfg in ENSEMBLE_MODELS.items():
  params={"latitude":float(loc["latitude"]),"longitude":float(loc["longitude"]),"hourly":ENSEMBLE_HOURLY,
   "models":cfg["api_model"],"timezone":loc["timezone"],"forecast_days":forecast_days,"precipitation_unit":"mm"}
  url=ENSEMBLE_ENDPOINT+"?"+urlencode(params)
  try:
   status,payload=_get_json(url); times,members=_ensemble_members(payload)
   if not times or len(members)<2: raise ActivityRegisterValidation(f"{code} ensemble members unavailable")
   raw=json.dumps(payload,sort_keys=True,separators=(",",":")); rh=hashlib.sha256(raw.encode()).hexdigest()
   fp=hashlib.sha256((code+"|"+url+"|"+rh).encode()).hexdigest(); tz=ZoneInfo(loc["timezone"])
   with connection() as c:
    run=c.execute("""INSERT INTO weather_ensemble_runs(provider_id,weather_location_id,model_code,model_family,
     retrieved_at,valid_from,valid_to,native_temporal_resolution_minutes,delivered_temporal_resolution_minutes,
     derivation_status,member_count,status,http_status,request_fingerprint,response_hash,raw_payload)
     VALUES(%s,%s,%s,%s,now(),%s,%s,%s,60,'INTERPOLATED',%s,'SUCCESS',%s,%s,%s,%s::jsonb)
     ON CONFLICT(provider_id,weather_location_id,model_code,request_fingerprint) DO UPDATE SET retrieved_at=now()
     RETURNING id""",(provider["id"],loc["id"],code,cfg["family"],datetime.fromisoformat(times[0]).replace(tzinfo=tz),
      datetime.fromisoformat(times[-1]).replace(tzinfo=tz),cfg["native_minutes"],len(members),status,fp,rh,raw)).fetchone()
    c.execute("DELETE FROM weather_ensemble_points WHERE ensemble_run_id=%s",(run["id"],))
    for i,t in enumerate(times):
     vals=[float(m[i] or 0) for m in members]; wet=sum(1 for v in vals if v>threshold)
     dt=datetime.fromisoformat(t); dt=dt if dt.tzinfo else dt.replace(tzinfo=tz)
     c.execute("""INSERT INTO weather_ensemble_points(ensemble_run_id,valid_at,member_count,wet_member_count,
      precipitation_probability_pct,precipitation_min_mm,precipitation_p25_mm,precipitation_median_mm,
      precipitation_p75_mm,precipitation_max_mm,source_semantics)
      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",(run["id"],dt,len(vals),wet,round(100*wet/len(vals),3),
       min(vals),_quantile(vals,.25),median(vals),_quantile(vals,.75),max(vals),
       json.dumps({"probability_definition":f"share of members > {threshold} mm/hour",
        "delivered_resolution":"hourly","native_resolution_minutes":cfg["native_minutes"],
        "derivation_status":"INTERPOLATED","model":code})))
    c.commit()
   results.append({"model":code,"members":len(members),"hours":len(times),"response_hash":rh})
  except Exception as e: failures.append({"model":code,"error":str(e)})
 return {"provider":PROVIDER_CODE,"location_id":str(loc["id"]),"ensembles":results,"failures":failures,
  "status":"SUCCESS" if len(results)==len(ENSEMBLE_MODELS) else "DEGRADED" if results else "FAILED","engine_version":ENGINE_VERSION}

def refresh_all(farm_id,plot_id=None,forecast_days=3):
 det=refresh_weather(farm_id,plot_id,forecast_days); ens=refresh_ensembles(farm_id,plot_id,forecast_days)
 return {"deterministic":det,"ensemble":ens,"engine_version":ENGINE_VERSION}

def _latest_model_points(c,loc_id,start,end,max_age_hours=8):
 rows=c.execute("""WITH latest AS (SELECT DISTINCT ON(model_code) id,model_code,retrieved_at FROM weather_fetch_runs
  WHERE weather_location_id=%s AND status='SUCCESS' AND retrieved_at>=now()-(%s||' hours')::interval
  ORDER BY model_code,retrieved_at DESC)
  SELECT l.model_code,l.retrieved_at,p.* FROM latest l JOIN weather_data_points p ON p.fetch_run_id=l.id
  WHERE p.valid_at BETWEEN %s AND %s ORDER BY p.valid_at,l.model_code""",(loc_id,max_age_hours,start,end)).fetchall()
 by={}
 for r in rows:by.setdefault(r["model_code"],[]).append(dict(r))
 return by

def _latest_ensemble(c,loc_id,start,end,max_age_hours=8):
 rows=c.execute("""WITH latest AS (SELECT DISTINCT ON(model_code) id,model_code,retrieved_at,member_count
  FROM weather_ensemble_runs WHERE weather_location_id=%s AND status='SUCCESS'
  AND retrieved_at>=now()-(%s||' hours')::interval ORDER BY model_code,retrieved_at DESC)
  SELECT l.model_code,l.retrieved_at,l.member_count,p.* FROM latest l JOIN weather_ensemble_points p
  ON p.ensemble_run_id=l.id WHERE p.valid_at BETWEEN %s AND %s ORDER BY p.valid_at,l.model_code""",
  (loc_id,max_age_hours,start,end)).fetchall()
 by={}
 for r in rows:by.setdefault(r["model_code"],[]).append(dict(r))
 return by

def _freshness(retrieved):
 if not retrieved:return "INSUFFICIENT_DATA"
 age=(datetime.now(timezone.utc)-min(x.astimezone(timezone.utc) for x in retrieved)).total_seconds()/3600
 return "FRESH" if age<=4 else "AGING" if age<=8 else "STALE"

def _local_reliability(c,loc_id):
 n=c.execute("""SELECT count(*) n FROM weather_forecast_verifications
  WHERE weather_location_id=%s AND verification_status='VERIFIED'""",(loc_id,)).fetchone()["n"]
 return "AVAILABLE" if n>=LOCAL_RELIABILITY_MIN_SAMPLES else "INSUFFICIENT_HISTORY"

def consensus(farm_id,plot_id,window_start,window_end,persist=True):
 with connection() as c:
  loc=dict(_location(c,farm_id,plot_id)); threshold=_event_threshold(c)
  by=_latest_model_points(c,loc["id"],window_start,window_end); ens=_latest_ensemble(c,loc["id"],window_start,window_end)
  reliability=_local_reliability(c,loc["id"])
 retrieved=[p[0]["retrieved_at"] for p in by.values() if p]+[p[0]["retrieved_at"] for p in ens.values() if p]
 freshness=_freshness(retrieved)
 evidence=[]; rainy=[]; totals=[]; firsts=[]; lasts=[]
 for model,pts in by.items():
  total=sum(float(p["precipitation_mm"] or 0) for p in pts); wet=[p for p in pts if float(p["precipitation_mm"] or 0)>threshold]
  rainy.append(bool(wet)); totals.append(total)
  if wet:firsts.append(wet[0]["valid_at"]);lasts.append(wet[-1]["valid_at"]+timedelta(hours=1))
  evidence.append({"model":model,"rain":bool(wet),"precipitation_total_mm":round(total,3),"retrieved_at":pts[0]["retrieved_at"].isoformat()})
 ensemble_evidence=[]; family_probs=[]
 for model,pts in ens.items():
  # Aggregate within each family first; never average raw member probabilities across families/time blindly.
  maxp=max(float(p["precipitation_probability_pct"]) for p in pts) if pts else None
  if maxp is not None:family_probs.append(maxp)
  ensemble_evidence.append({"ensemble_family":model,"max_hourly_event_probability_pct":maxp,
   "member_count":pts[0]["member_count"] if pts else 0,"retrieved_at":pts[0]["retrieved_at"].isoformat() if pts else None})
 if len(by)<2:
  agreement="INSUFFICIENT_DATA"; support=None; amount_min=amount_max=None; timing="INSUFFICIENT_DATA"
 else:
  fraction=sum(rainy)/len(rainy); strength=max(fraction,1-fraction)
  agreement="HIGH" if strength>=.85 else "MEDIUM_HIGH" if strength>=.70 else "MEDIUM" if strength>=.60 else "LOW"
  support=round(fraction*100,1); amount_min=round(min(totals),3);amount_max=round(max(totals),3)
  timing="MEDIUM" if len(firsts)>=2 else "LOW" if firsts else "INSUFFICIENT_DATA"
 ensemble_prob=max(family_probs) if family_probs else None # conservative cross-family support, not arithmetic averaging.
 confidence="INSUFFICIENT_DATA" if agreement=="INSUFFICIENT_DATA" or freshness=="STALE" else (
  "HIGH" if agreement=="HIGH" and len(ens)>=2 and freshness=="FRESH" else
  "MEDIUM" if agreement in ("HIGH","MEDIUM_HIGH") and freshness in ("FRESH","AGING") else "LOW")
 result={"model_count":len(by),"ensemble_family_count":len(ens),"model_agreement":agreement,
  "deterministic_rain_support_pct":support,"ensemble_precipitation_probability_pct":ensemble_prob,
  "expected_precipitation_min_mm":amount_min,"expected_precipitation_max_mm":amount_max,
  "most_likely_rain_start":min(firsts) if firsts else None,"most_likely_rain_end":max(lasts) if lasts else None,
  "timing_confidence":timing,"confidence_class":confidence,"freshness_status":freshness,
  "local_reliability_status":reliability,"evidence":evidence,"ensemble_evidence":ensemble_evidence,
  "engine_version":ENGINE_VERSION,
  "guardrail":"Deterministic support, ensemble probability, confidence, and local reliability are distinct metrics."}
 if persist:
  with connection() as c:
   row=c.execute("""INSERT INTO weather_consensus_assessments(weather_location_id,window_start,window_end,
    model_count,model_agreement,forecast_confidence_pct,precipitation_probability_pct,
    deterministic_rain_support_pct,ensemble_precipitation_probability_pct,expected_precipitation_min_mm,
    expected_precipitation_max_mm,most_likely_rain_start,most_likely_rain_end,timing_confidence,
    confidence_class,freshness_status,local_reliability_status,evidence,ensemble_evidence,engine_version)
    VALUES(%s,%s,%s,%s,%s,NULL,NULL,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING id""",
    (loc["id"],window_start,window_end,result["model_count"],agreement,support,ensemble_prob,amount_min,amount_max,
     result["most_likely_rain_start"],result["most_likely_rain_end"],timing,confidence,freshness,reliability,
     json.dumps(evidence,default=_json_default),json.dumps(ensemble_evidence,default=_json_default),ENGINE_VERSION)).fetchone()
   c.commit();result["assessment_id"]=str(row["id"])
 return result

def operational_check(req):
 required=req.planned_start+timedelta(minutes=req.expected_duration_minutes+(req.rainfast_minutes or 0)+req.safety_buffer_minutes)
 con=consensus(req.farm_id,req.plot_id,req.planned_start,required,persist=req.persist); reasons=[]
 if con["freshness_status"]=="STALE":decision="INSUFFICIENT_DATA";reasons=["STALE_WEATHER_DATA"]
 elif con["model_agreement"]=="INSUFFICIENT_DATA":decision="INSUFFICIENT_DATA";reasons=["INSUFFICIENT_WEATHER_MODELS"]
 elif req.operation_type=="SPRAY" and req.rainfast_minutes is None:decision="CAUTION";reasons=["RAINFAST_REQUIREMENT_UNKNOWN"]
 elif (con["ensemble_precipitation_probability_pct"] is not None and con["ensemble_precipitation_probability_pct"]>=50):
  decision="HOLD" if req.operation_type=="SPRAY" else "CAUTION";reasons=["ENSEMBLE_RAIN_RISK_WITHIN_REQUIRED_WINDOW"]
 elif (con["deterministic_rain_support_pct"] or 0)>=50:
  decision="HOLD" if req.operation_type=="SPRAY" else "CAUTION";reasons=["DETERMINISTIC_RAIN_SUPPORT_WITHIN_REQUIRED_WINDOW"]
 elif (con["expected_precipitation_max_mm"] or 0)>DEFAULT_EVENT_THRESHOLD_MM:decision="CAUTION";reasons=["MODEL_RAIN_SIGNAL"]
 else:decision="SAFE"
 out={"decision":decision,"reason_codes":reasons,"required_safe_until":required,"rainfast_minutes":req.rainfast_minutes,
  "consensus":con,"engine_version":ENGINE_VERSION,
  "guardrail":"No unverified product-specific rainfast interval is invented. Unknown rainfast prevents a SAFE spray decision."}
 if req.persist:
  with connection() as c:
   loc=_location(c,req.farm_id,req.plot_id)
   c.execute("""INSERT INTO weather_operational_assessments(crop_cycle_id,activity_id,weather_location_id,
    operation_type,planned_start,expected_duration_minutes,rainfast_minutes,safety_buffer_minutes,
    required_safe_until,decision,reason_codes,consensus_assessment_id,evidence,engine_version)
    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s)""",
    (req.crop_cycle_id,req.activity_id,loc["id"],req.operation_type,req.planned_start,req.expected_duration_minutes,
     req.rainfast_minutes,req.safety_buffer_minutes,required,decision,json.dumps(reasons),con.get("assessment_id"),
     json.dumps(out,default=_json_default),ENGINE_VERSION));c.commit()
 return out

def record_observation(req):
 with connection() as c:
  loc=_location(c,req.farm_id,req.plot_id)
  row=c.execute("""INSERT INTO weather_observations(weather_location_id,observed_at,evidence_class,source_code,
   precipitation_mm,temperature_c,relative_humidity_pct,wind_speed_kmh,wind_gust_kmh,quality_status,
   source_reference,raw_evidence) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
   ON CONFLICT(weather_location_id,observed_at,evidence_class,source_code) DO UPDATE SET
   precipitation_mm=EXCLUDED.precipitation_mm,temperature_c=EXCLUDED.temperature_c,
   relative_humidity_pct=EXCLUDED.relative_humidity_pct,wind_speed_kmh=EXCLUDED.wind_speed_kmh,
   wind_gust_kmh=EXCLUDED.wind_gust_kmh,quality_status=EXCLUDED.quality_status,
   source_reference=EXCLUDED.source_reference,raw_evidence=EXCLUDED.raw_evidence RETURNING *""",
   (loc["id"],req.observed_at,req.evidence_class,req.source_code,req.precipitation_mm,req.temperature_c,
    req.relative_humidity_pct,req.wind_speed_kmh,req.wind_gust_kmh,req.quality_status,req.source_reference,
    json.dumps(req.raw_evidence))).fetchone();c.commit();return dict(row)

def verify_forecasts(farm_id,plot_id=None,start=None,end=None):
 start=start or datetime.now(timezone.utc)-timedelta(days=7);end=end or datetime.now(timezone.utc)
 with connection() as c:
  loc=_location(c,farm_id,plot_id);threshold=_event_threshold(c)
  obs=c.execute("""SELECT * FROM weather_observations WHERE weather_location_id=%s AND quality_status='VERIFIED'
   AND observed_at BETWEEN %s AND %s ORDER BY observed_at""",(loc["id"],start,end)).fetchall()
  made=0
  for o in obs:
   forecasts=c.execute("""SELECT r.id fetch_run_id,r.model_code,r.retrieved_at,p.valid_at,p.precipitation_mm
    FROM weather_fetch_runs r JOIN weather_data_points p ON p.fetch_run_id=r.id
    WHERE r.weather_location_id=%s AND r.status='SUCCESS' AND p.valid_at=%s AND r.retrieved_at<=%s""",
    (loc["id"],o["observed_at"],o["observed_at"])).fetchall()
   for f in forecasts:
    fv=float(f["precipitation_mm"] or 0);ov=float(o["precipitation_mm"] or 0)
    lead=(f["valid_at"]-f["retrieved_at"]).total_seconds()/3600
    c.execute("""INSERT INTO weather_forecast_verifications(weather_location_id,model_code,fetch_run_id,valid_at,
     lead_hours,forecast_precipitation_mm,observed_precipitation_mm,event_threshold_mm,event_forecast,event_observed,
     absolute_error_mm,observation_id,verification_status)
     VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'VERIFIED')
     ON CONFLICT(fetch_run_id,valid_at,observation_id) DO NOTHING""",(loc["id"],f["model_code"],f["fetch_run_id"],
      f["valid_at"],lead,fv,ov,threshold,fv>threshold,ov>threshold,abs(fv-ov),o["id"]));made+=1
  c.commit()
 return {"verification_rows_attempted":made,"local_reliability_min_samples":LOCAL_RELIABILITY_MIN_SAMPLES,"engine_version":ENGINE_VERSION}

def weather_context_for_crop_cycle(crop_cycle_id,as_of=None):
 as_of=as_of or datetime.now(timezone.utc)
 with connection() as c:
  cc=c.execute("SELECT farm_id,plot_id FROM crop_cycles WHERE id=%s",(crop_cycle_id,)).fetchone()
  if not cc:return {"status":"UNAVAILABLE","reason":"CROP_CYCLE_NOT_FOUND"}
  try:loc=_location(c,cc["farm_id"],cc["plot_id"])
  except ActivityRegisterValidation:return {"status":"UNAVAILABLE","reason":"WEATHER_LOCATION_NOT_CONFIGURED"}
  latest=c.execute("""SELECT model_code,retrieved_at,valid_from,valid_to FROM weather_fetch_runs
   WHERE weather_location_id=%s AND status='SUCCESS' ORDER BY retrieved_at DESC LIMIT 6""",(loc["id"],)).fetchall()
  reliability=_local_reliability(c,loc["id"])
 return {"status":"AVAILABLE" if latest else "UNAVAILABLE","location_id":str(loc["id"]),
  "latest_runs":[dict(x) for x in latest],"local_reliability_status":reliability,"engine_version":ENGINE_VERSION}
