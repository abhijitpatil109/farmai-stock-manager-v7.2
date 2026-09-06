from __future__ import annotations
import hashlib,json
from ..db import connection
from .activity_register import ActivityRegisterNotFound,ActivityRegisterValidation
def _j(v):return json.dumps(v,default=str,separators=(",",":"))
def create_task(req):
    with connection() as c:
      try:
        ex=c.execute("SELECT * FROM public.scouting_tasks WHERE idempotency_key=%s",(req.idempotency_key,)).fetchone()
        if ex:return {"duplicate":True,"task":dict(ex)}
        p=c.execute("SELECT * FROM public.plots WHERE id=%s",(req.plot_id,)).fetchone()
        if not p:raise ActivityRegisterNotFound("Plot not found.")
        if p["farm_id"]!=req.farm_id:raise ActivityRegisterValidation("Plot does not belong to farm.")
        row=c.execute("""INSERT INTO public.scouting_tasks(
         farm_id,plot_id,crop_cycle_id,anomaly_id,source_type,title_en,title_mr,reason_en,reason_mr,priority,checklist,due_date,idempotency_key,created_by)
         VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s) RETURNING *""",
         (req.farm_id,req.plot_id,req.crop_cycle_id,req.anomaly_id,req.source_type,req.title_en,req.title_mr,
          req.reason_en,req.reason_mr,req.priority,_j(req.checklist),req.due_date,req.idempotency_key,req.created_by)).fetchone()
        c.commit();return {"duplicate":False,"task":dict(row)}
      except Exception:c.rollback();raise
def list_tasks(farm_id=None,plot_id=None,status=None,limit=100):
    with connection() as c:
      return [dict(x) for x in c.execute("""SELECT st.*,p.code plot_code,p.name_en plot_name_en,p.name_mr plot_name_mr
       FROM public.scouting_tasks st JOIN public.plots p ON p.id=st.plot_id
       WHERE (%s::uuid IS NULL OR st.farm_id=%s) AND (%s::uuid IS NULL OR st.plot_id=%s)
       AND (%s::text IS NULL OR st.status=%s) ORDER BY st.created_at DESC LIMIT %s""",
       (farm_id,farm_id,plot_id,plot_id,status,status,limit)).fetchall()]
def complete_task(task_id,req):
    h=hashlib.sha256(_j(req.model_dump(mode="json")).encode()).hexdigest()
    with connection() as c:
      try:
        task=c.execute("SELECT * FROM public.scouting_tasks WHERE id=%s FOR UPDATE",(task_id,)).fetchone()
        if not task:raise ActivityRegisterNotFound("Scouting task not found.")
        ex=c.execute("SELECT * FROM public.scouting_observations WHERE task_id=%s AND observation_hash=%s",(task_id,h)).fetchone()
        if ex:return {"duplicate":True,"observation":dict(ex)}
        old=c.execute("SELECT * FROM public.scouting_observations WHERE task_id=%s AND is_current=true FOR UPDATE",(task_id,)).fetchone()
        if old:c.execute("UPDATE public.scouting_observations SET is_current=false WHERE id=%s",(old["id"],))
        gps="NULL";args=[task_id,req.observed_at,req.observer]
        if req.latitude is not None and req.longitude is not None:gps="ST_SetSRID(ST_MakePoint(%s,%s),4326)";args += [req.longitude,req.latitude]
        elif req.latitude is not None or req.longitude is not None:raise ActivityRegisterValidation("Latitude and longitude must be supplied together.")
        sql=f"""INSERT INTO public.scouting_observations(
         task_id,observed_at,observer,gps_location,severity,affected_area_pct,symptom_codes,soil_moisture_condition,
         waterlogging,wilting,yellowing,pest_visible,disease_symptom_visible,notes_en,notes_mr,verification_status,
         observation_hash,supersedes_observation_id) VALUES(%s,%s,%s,{gps},%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *"""
        args += [req.severity,req.affected_area_pct,_j(req.symptom_codes),req.soil_moisture_condition,req.waterlogging,
                 req.wilting,req.yellowing,req.pest_visible,req.disease_symptom_visible,req.notes_en,req.notes_mr,
                 req.verification_status,h,old["id"] if old else None]
        obs=c.execute(sql,tuple(args)).fetchone();c.execute("UPDATE public.scouting_tasks SET status='COMPLETED',updated_at=now() WHERE id=%s",(task_id,))
        if task["anomaly_id"]:c.execute("UPDATE public.remote_sensing_anomalies SET status='VERIFIED',updated_at=now() WHERE id=%s",(task["anomaly_id"],))
        c.commit();return {"duplicate":False,"observation":dict(obs)}
      except Exception:c.rollback();raise
