from __future__ import annotations
import hashlib,json,math
from ..db import connection
from .activity_register import ActivityRegisterNotFound,ActivityRegisterValidation
def _j(v):return json.dumps(v,default=str,separators=(",",":"))
def evaluate_anomaly(plot_id,observation_id=None):
    with connection() as c:
      rule=c.execute("""SELECT * FROM public.remote_sensing_rule_packs WHERE rule_code='TEMPORAL_ANOMALY_STATISTICAL'
        AND active=true AND verification_status='VERIFIED' ORDER BY version DESC LIMIT 1""").fetchone()
      if not rule:raise ActivityRegisterValidation("Verified anomaly rule unavailable.")
      p=rule["rule_payload"]; metric=p["metric"]
      sql="""SELECT o.*,i.mean_value FROM public.plot_remote_observations o JOIN public.plot_index_statistics i
             ON i.observation_id=o.id AND i.index_code=%s WHERE o.plot_id=%s"""
      params=[metric,plot_id]
      if observation_id: sql+=" AND o.id=%s";params.append(observation_id)
      else: sql+=" AND o.quality_status IN ('VALID','PARTIAL') ORDER BY o.acquired_at DESC LIMIT 1"
      cur=c.execute(sql,tuple(params)).fetchone()
      if not cur:raise ActivityRegisterNotFound("Usable remote observation not found.")
      if cur["quality_status"] not in ("VALID","PARTIAL"):return {"status":"INSUFFICIENT_EVIDENCE","reason":"CURRENT_OBSERVATION_NOT_USABLE"}
      need=int(p["baseline_observations"]); lookback=int(p["lookback_days"])
      rows=c.execute("""SELECT i.mean_value,o.acquired_at FROM public.plot_remote_observations o
        JOIN public.plot_index_statistics i ON i.observation_id=o.id AND i.index_code=%s
        WHERE o.plot_id=%s AND o.id<>%s AND o.quality_status IN ('VALID','PARTIAL')
          AND o.acquired_at >= %s-(%s||' days')::interval AND o.acquired_at<%s
        ORDER BY o.acquired_at DESC LIMIT %s""",(metric,plot_id,cur["id"],cur["acquired_at"],lookback,cur["acquired_at"],need)).fetchall()
      vals=[float(x["mean_value"]) for x in rows if x["mean_value"] is not None]
      if len(vals)<need:return {"status":"INSUFFICIENT_HISTORY","required":need,"available":len(vals)}
      mean=sum(vals)/len(vals);sd=math.sqrt(sum((x-mean)**2 for x in vals)/len(vals));value=float(cur["mean_value"])
      z=None if sd==0 else (value-mean)/sd; rel=None if mean==0 else (value-mean)/abs(mean)*100
      if not(z is not None and abs(z)>=float(p["z_threshold"]) and rel is not None and abs(rel)>=float(p["min_relative_change_pct"])):
          return {"status":"NO_ANOMALY","metric":metric,"current":value,"baseline_mean":mean,"z_score":z,"relative_change_pct":rel}
      kind="DECLINE" if value<mean else "INCREASE";severity="HIGH" if abs(z)>=3 else "MEDIUM"
      key=hashlib.sha256(f"{cur['id']}:{rule['id']}:{metric}:{kind}".encode()).hexdigest()
      ex=c.execute("SELECT * FROM public.remote_sensing_anomalies WHERE idempotency_key=%s",(key,)).fetchone()
      if ex:return {"status":"ANOMALY","duplicate":True,"anomaly":dict(ex)}
      a=c.execute("""INSERT INTO public.remote_sensing_anomalies(
        plot_id,crop_cycle_id,observation_id,rule_pack_id,metric_code,anomaly_type,severity,confidence,baseline_from,
        baseline_to,baseline_count,current_value,baseline_mean,baseline_stddev,z_score,relative_change_pct,evidence,idempotency_key)
        VALUES(%s,%s,%s,%s,%s,%s,%s,'MEDIUM',%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING *""",
        (plot_id,cur["crop_cycle_id"],cur["id"],rule["id"],metric,kind,severity,
         min(x["acquired_at"].date() for x in rows),max(x["acquired_at"].date() for x in rows),len(vals),
         value,mean,sd,z,rel,_j({"baseline_values":vals,"diagnostic":False}),key)).fetchone()
      taskkey=f"REMOTE-ANOMALY:{a['id']}"
      t=c.execute("""INSERT INTO public.scouting_tasks(
        farm_id,plot_id,crop_cycle_id,anomaly_id,source_type,title_en,title_mr,reason_en,reason_mr,priority,checklist,idempotency_key,created_by)
        SELECT p.farm_id,%s,%s,%s,'REMOTE_SENSING','Inspect remote-sensing anomaly','दूरसंवेदन विसंगतीची पाहणी करा',
        %s,%s,%s,%s::jsonb,%s,'phase9-anomaly-engine' FROM public.plots p WHERE p.id=%s
        ON CONFLICT(idempotency_key) DO UPDATE SET updated_at=now() RETURNING *""",
        (plot_id,cur["crop_cycle_id"],a["id"],f"{metric} change detected; satellite evidence is not diagnosis.",
         f"{metric} बदल आढळला; उपग्रह पुरावा निदान नाही.","HIGH" if severity=="HIGH" else "MEDIUM",
         _j(["leaf colour","wilting","pest signs","disease symptoms","soil moisture","drainage","photographs"]),taskkey,plot_id)).fetchone()
      c.execute("UPDATE public.remote_sensing_anomalies SET status='SCOUTING',updated_at=now() WHERE id=%s",(a["id"],));c.commit()
      return {"status":"ANOMALY","duplicate":False,"anomaly":dict(a),"scouting_task":dict(t)}
