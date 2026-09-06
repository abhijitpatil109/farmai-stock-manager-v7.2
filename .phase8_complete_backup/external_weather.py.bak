from __future__ import annotations
import hashlib, json, math
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo
from ..db import connection
from .activity_register import ActivityRegisterNotFound, ActivityRegisterValidation

ENGINE_VERSION="8.1.0"
PROVIDER_CODE="OPEN_METEO"
MODEL_ENDPOINTS={
    "ECMWF_IFS":"https://api.open-meteo.com/v1/ecmwf",
    "GFS":"https://api.open-meteo.com/v1/gfs",
    "ICON":"https://api.open-meteo.com/v1/dwd-icon",
}
HOURLY="temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,wind_gusts_10m,weather_code"
RAIN_THRESHOLD_MM=0.1  # meteorological event threshold only; NOT an agronomic rainfast threshold

def _json_default(v):
    if isinstance(v,(datetime,)): return v.isoformat()
    return str(v)

def _get_json(url, timeout=12):
    req=Request(url,headers={"User-Agent":"FarmAI/8.0 ExternalIntelligence"})
    try:
        with urlopen(req,timeout=timeout) as r:
            return r.status,json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        raise ActivityRegisterValidation(f"Weather provider HTTP {e.code}") from e
    except (URLError,TimeoutError,json.JSONDecodeError) as e:
        raise ActivityRegisterValidation(f"Weather provider unavailable: {type(e).__name__}") from e

def upsert_location(req):
    with connection() as c:
        farm=c.execute("SELECT id FROM farms WHERE id=%s",(req.farm_id,)).fetchone()
        if not farm: raise ActivityRegisterNotFound("Farm not found. (शेत सापडले नाही.)")
        if req.plot_id:
            p=c.execute("SELECT id FROM plots WHERE id=%s AND farm_id=%s",(req.plot_id,req.farm_id)).fetchone()
            if not p: raise ActivityRegisterValidation("Plot does not belong to farm.")
        if req.plot_id:
            row=c.execute("""INSERT INTO weather_locations(farm_id,plot_id,latitude,longitude,timezone,elevation_m,source)
            VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(farm_id,plot_id) DO UPDATE SET latitude=EXCLUDED.latitude,longitude=EXCLUDED.longitude,
            timezone=EXCLUDED.timezone,elevation_m=EXCLUDED.elevation_m,source=EXCLUDED.source,active=true,updated_at=now() RETURNING *""",
            (req.farm_id,req.plot_id,req.latitude,req.longitude,req.timezone,req.elevation_m,req.source)).fetchone()
        else:
            row=c.execute("SELECT * FROM weather_locations WHERE farm_id=%s AND plot_id IS NULL AND active=true FOR UPDATE",(req.farm_id,)).fetchone()
            if row:
                row=c.execute("UPDATE weather_locations SET latitude=%s,longitude=%s,timezone=%s,elevation_m=%s,source=%s,updated_at=now() WHERE id=%s RETURNING *",
                (req.latitude,req.longitude,req.timezone,req.elevation_m,req.source,row['id'])).fetchone()
            else:
                row=c.execute("INSERT INTO weather_locations(farm_id,latitude,longitude,timezone,elevation_m,source) VALUES(%s,%s,%s,%s,%s,%s) RETURNING *",
                (req.farm_id,req.latitude,req.longitude,req.timezone,req.elevation_m,req.source)).fetchone()
        c.commit(); return dict(row)

def _location(c,farm_id,plot_id=None):
    if plot_id:
        row=c.execute("SELECT * FROM weather_locations WHERE farm_id=%s AND plot_id=%s AND active=true",(farm_id,plot_id)).fetchone()
        if row:return row
    row=c.execute("SELECT * FROM weather_locations WHERE farm_id=%s AND plot_id IS NULL AND active=true",(farm_id,)).fetchone()
    if not row: raise ActivityRegisterValidation("Weather location is not configured for this farm.")
    return row

def _parse_points(payload,tz_name):
    h=payload.get("hourly") or {}; times=h.get("time") or []
    tz=ZoneInfo(tz_name); out=[]
    def val(k,i):
        a=h.get(k) or []; return a[i] if i<len(a) else None
    for i,t in enumerate(times):
        dt=datetime.fromisoformat(t)
        if dt.tzinfo is None: dt=dt.replace(tzinfo=tz)
        out.append({"valid_at":dt,"precipitation_mm":val("precipitation",i),"temperature_c":val("temperature_2m",i),
          "relative_humidity_pct":val("relative_humidity_2m",i),"wind_speed_kmh":val("wind_speed_10m",i),"wind_gust_kmh":val("wind_gusts_10m",i),
          "weather_code":val("weather_code",i)})
    return out

def refresh_weather(farm_id,plot_id=None,forecast_days=3):
    with connection() as c:
        loc=dict(_location(c,farm_id,plot_id)); provider=c.execute("SELECT * FROM external_data_providers WHERE code=%s AND active=true",(PROVIDER_CODE,)).fetchone()
        if not provider: raise ActivityRegisterValidation("OPEN_METEO provider is not configured.")
    results=[]
    for model,urlbase in MODEL_ENDPOINTS.items():
        params={"latitude":float(loc["latitude"]),"longitude":float(loc["longitude"]),"hourly":HOURLY,"timezone":loc["timezone"],"forecast_days":forecast_days,"wind_speed_unit":"kmh","precipitation_unit":"mm"}
        url=urlbase+"?"+urlencode(params)
        status,payload=_get_json(url); points=_parse_points(payload,loc["timezone"])
        if not points: continue
        raw=json.dumps(payload,sort_keys=True,separators=(",",":")); rh=hashlib.sha256(raw.encode()).hexdigest()
        # Idempotency is based on the actual provider payload state, not only the
        # static request URL. If the provider forecast changes, FarmAI stores a
        # new immutable evidence run; an identical payload safely replays.
        fp=hashlib.sha256((model+"|"+url+"|"+rh).encode()).hexdigest()
        with connection() as c:
            run=c.execute("""INSERT INTO weather_fetch_runs(provider_id,weather_location_id,model_code,model_family,retrieved_at,valid_from,valid_to,
            temporal_resolution_minutes,temporal_resolution_type,status,http_status,request_fingerprint,response_hash,raw_payload)
            VALUES(%s,%s,%s,%s,now(),%s,%s,60,'NATIVE','SUCCESS',%s,%s,%s,%s::jsonb)
            ON CONFLICT(provider_id,weather_location_id,model_code,request_fingerprint) DO UPDATE SET retrieved_at=now(),valid_from=EXCLUDED.valid_from,valid_to=EXCLUDED.valid_to,
            status='SUCCESS',http_status=EXCLUDED.http_status,response_hash=EXCLUDED.response_hash,raw_payload=EXCLUDED.raw_payload RETURNING id""",
            (provider["id"],loc["id"],model,model,points[0]["valid_at"],points[-1]["valid_at"],status,fp,rh,raw)).fetchone()
            c.execute("DELETE FROM weather_data_points WHERE fetch_run_id=%s",(run["id"],))
            for p in points:
                c.execute("""INSERT INTO weather_data_points(fetch_run_id,valid_at,precipitation_mm,temperature_c,relative_humidity_pct,wind_speed_kmh,wind_gust_kmh,weather_code,source_semantics)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",(run["id"],p["valid_at"],p["precipitation_mm"],p["temperature_c"],p["relative_humidity_pct"],p["wind_speed_kmh"],p["wind_gust_kmh"],p["weather_code"],
                json.dumps({"precipitation":"preceding-hour sum","temporal_resolution":"native hourly","provider":"OPEN_METEO","model":model})))
            c.commit()
        results.append({"model":model,"points":len(points),"response_hash":rh})
    return {"provider":PROVIDER_CODE,"location_id":str(loc["id"]),"models":results,"engine_version":ENGINE_VERSION}

def _latest_model_points(c,loc_id,start,end,max_age_hours=8):
    rows=c.execute("""WITH latest AS (SELECT DISTINCT ON(model_code) id,model_code,retrieved_at FROM weather_fetch_runs
      WHERE weather_location_id=%s AND status='SUCCESS' AND retrieved_at>=now()-(%s||' hours')::interval ORDER BY model_code,retrieved_at DESC)
      SELECT l.model_code,l.retrieved_at,p.* FROM latest l JOIN weather_data_points p ON p.fetch_run_id=l.id
      WHERE p.valid_at BETWEEN %s AND %s ORDER BY p.valid_at,l.model_code""",(loc_id,max_age_hours,start,end)).fetchall()
    by={}
    for r in rows: by.setdefault(r["model_code"],[]).append(dict(r))
    return by

def consensus(farm_id,plot_id,window_start,window_end,persist=True):
    with connection() as c:
        loc=dict(_location(c,farm_id,plot_id)); by=_latest_model_points(c,loc["id"],window_start,window_end)
    if len(by)<2:
        result={"model_count":len(by),"model_agreement":"INSUFFICIENT_DATA","forecast_confidence_pct":None,"precipitation_probability_pct":None,
          "expected_precipitation_min_mm":None,"expected_precipitation_max_mm":None,"most_likely_rain_start":None,"most_likely_rain_end":None,
          "timing_confidence":"INSUFFICIENT_DATA","evidence":[],"engine_version":ENGINE_VERSION}
    else:
        evidence=[]; rainy=[]; totals=[]; firsts=[]; lasts=[]
        for model,pts in by.items():
            total=sum(float(p["precipitation_mm"] or 0) for p in pts); wet=[p for p in pts if float(p["precipitation_mm"] or 0)>=RAIN_THRESHOLD_MM]
            is_rain=bool(wet); rainy.append(is_rain); totals.append(total)
            if wet:firsts.append(wet[0]["valid_at"]); lasts.append(wet[-1]["valid_at"]+timedelta(hours=1))
            evidence.append({"model":model,"rain":is_rain,"precipitation_total_mm":round(total,3),"retrieved_at":pts[0]["retrieved_at"].isoformat()})
        fraction=sum(rainy)/len(rainy); agreement_strength=max(fraction,1-fraction)
        agreement="HIGH" if agreement_strength>=0.85 else "MEDIUM_HIGH" if agreement_strength>=0.70 else "MEDIUM" if agreement_strength>=0.60 else "LOW"
        # Deterministic multi-model vote is labelled consensus probability, not ensemble probability or local precision.
        prob=round(fraction*100,1); spread=(max(totals)-min(totals)) if totals else 0
        confidence=max(0,min(100,round(100*agreement_strength- min(35,spread*3),1)))
        result={"model_count":len(by),"model_agreement":agreement,"forecast_confidence_pct":confidence,"precipitation_probability_pct":prob,
          "expected_precipitation_min_mm":round(min(totals),3),"expected_precipitation_max_mm":round(max(totals),3),
          "most_likely_rain_start":min(firsts) if firsts else None,"most_likely_rain_end":max(lasts) if lasts else None,
          "timing_confidence":"MEDIUM" if len(firsts)>=2 else "LOW" if firsts else "INSUFFICIENT_DATA","evidence":evidence,"engine_version":ENGINE_VERSION}
    if persist:
        with connection() as c:
            row=c.execute("""INSERT INTO weather_consensus_assessments(weather_location_id,window_start,window_end,model_count,model_agreement,forecast_confidence_pct,
              precipitation_probability_pct,expected_precipitation_min_mm,expected_precipitation_max_mm,most_likely_rain_start,most_likely_rain_end,timing_confidence,evidence,engine_version)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING id""",
              (loc["id"],window_start,window_end,result["model_count"],result["model_agreement"],result["forecast_confidence_pct"],result["precipitation_probability_pct"],
               result["expected_precipitation_min_mm"],result["expected_precipitation_max_mm"],result["most_likely_rain_start"],result["most_likely_rain_end"],result["timing_confidence"],json.dumps(result["evidence"],default=_json_default),ENGINE_VERSION)).fetchone(); c.commit(); result["assessment_id"]=str(row["id"])
    return result

def operational_check(req):
    rainfast=req.rainfast_minutes
    required=req.planned_start+timedelta(minutes=req.expected_duration_minutes+(rainfast or 0)+req.safety_buffer_minutes)
    # Evaluate from start through required safe-until; unknown rainfast remains explicit and cannot produce SAFE for spray.
    con=consensus(req.farm_id,req.plot_id,req.planned_start,required,persist=req.persist)
    reasons=[]
    if con["model_agreement"]=="INSUFFICIENT_DATA": decision="INSUFFICIENT_DATA"; reasons=["INSUFFICIENT_WEATHER_MODELS"]
    elif req.operation_type=="SPRAY" and rainfast is None: decision="CAUTION"; reasons=["RAINFAST_REQUIREMENT_UNKNOWN"]
    elif (con["precipitation_probability_pct"] or 0)>=50: decision="HOLD" if req.operation_type=="SPRAY" else "CAUTION"; reasons=["RAIN_RISK_WITHIN_REQUIRED_WINDOW"]
    elif (con["expected_precipitation_max_mm"] or 0)>=RAIN_THRESHOLD_MM: decision="CAUTION"; reasons=["MODEL_RAIN_SIGNAL"]
    else: decision="SAFE"; reasons=[]
    out={"decision":decision,"reason_codes":reasons,"required_safe_until":required,"rainfast_minutes":rainfast,"consensus":con,"engine_version":ENGINE_VERSION,
         "guardrail":"Rain probability is percent; precipitation amount is mm. Deterministic consensus is not labelled ensemble probability or local forecast precision."}
    if req.persist:
        with connection() as c:
            loc=_location(c,req.farm_id,req.plot_id)
            c.execute("""INSERT INTO weather_operational_assessments(crop_cycle_id,activity_id,weather_location_id,operation_type,planned_start,expected_duration_minutes,rainfast_minutes,
              safety_buffer_minutes,required_safe_until,decision,reason_codes,consensus_assessment_id,evidence,engine_version)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s)""",
              (req.crop_cycle_id,req.activity_id,loc["id"],req.operation_type,req.planned_start,req.expected_duration_minutes,rainfast,req.safety_buffer_minutes,required,decision,
               json.dumps(reasons),con.get("assessment_id"),json.dumps(out,default=_json_default),ENGINE_VERSION)); c.commit()
    return out

def weather_context_for_crop_cycle(crop_cycle_id,as_of=None):
    as_of=as_of or datetime.now(timezone.utc)
    with connection() as c:
        cc=c.execute("SELECT farm_id,plot_id FROM crop_cycles WHERE id=%s",(crop_cycle_id,)).fetchone()
        if not cc:return {"status":"UNAVAILABLE","reason":"CROP_CYCLE_NOT_FOUND"}
        try:loc=_location(c,cc["farm_id"],cc["plot_id"])
        except ActivityRegisterValidation:return {"status":"UNAVAILABLE","reason":"WEATHER_LOCATION_NOT_CONFIGURED"}
        latest=c.execute("SELECT model_code,retrieved_at,valid_from,valid_to FROM weather_fetch_runs WHERE weather_location_id=%s AND status='SUCCESS' ORDER BY retrieved_at DESC LIMIT 5",(loc["id"],)).fetchall()
    return {"status":"AVAILABLE" if latest else "UNAVAILABLE","location_id":str(loc["id"]),"latest_runs":[dict(x) for x in latest],"engine_version":ENGINE_VERSION}
