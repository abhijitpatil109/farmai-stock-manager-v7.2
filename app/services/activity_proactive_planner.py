
"""FarmAI Phase 7 — Proactive Planner & Farm Operations.

Quality-gated V2 invariants:
1. Intelligence recommendation, farmer decision, Activity plan and execution remain distinct.
2. Recommendation -> proposed Activity lineage is one-to-one and replay safe.
3. Proposed Activity + lineage + planner control are created in one PostgreSQL transaction.
4. Planner controls never write Stock.
5. Existing Phase 3 Activity lifecycle remains authoritative for scheduling.
"""
from __future__ import annotations

import json
from datetime import date,timedelta
from psycopg.errors import UniqueViolation

from ..db import connection
from .activity_register import (
    ActivityRegisterNotFound,
    ActivityRegisterValidation,
    _active_ref,
    _product_by_code,
    _audit,
    _crop_cycle,
    _dap_for_date,
    get_activity,
)
from .activity_planner import planner_board, schedule_activity
from ..schemas.activity_planner import ScheduleCommand


TERMINAL={"COMPLETED","SKIPPED","CANCELLED"}


def _json(value):
    return None if value is None else json.dumps(value,default=str)


def _event(conn,activity_id,event_type,old_data=None,new_data=None,changed_by=None):
    conn.execute(
      """INSERT INTO public.planner_control_events(
           activity_id,event_type,old_data,new_data,changed_by
         ) VALUES(%s,%s,%s::jsonb,%s::jsonb,%s)""",
      (activity_id,event_type,_json(old_data),_json(new_data),changed_by)
    )


def _control(conn,activity_id):
    return conn.execute(
      "SELECT * FROM public.planner_activity_controls WHERE activity_id=%s",
      (activity_id,)
    ).fetchone()


def _require_activity(conn,activity_id,for_update=False):
    sql="SELECT * FROM public.activities WHERE id=%s"
    if for_update:
        sql+=" FOR UPDATE"
    row=conn.execute(sql,(activity_id,)).fetchone()
    if not row:
        raise ActivityRegisterNotFound("Activity not found. (क्रियाकलाप सापडला नाही.)")
    return row


def _existing_proposal(conn,recommendation_id):
    return conn.execute(
      """SELECT l.activity_id
         FROM public.planner_recommendation_links l
         WHERE l.recommendation_id=%s AND l.link_status='ACTIVE'""",
      (recommendation_id,)
    ).fetchone()


def _create_planned_activity_in_tx(conn,recommendation,req):
    cycle=_crop_cycle(conn,recommendation["crop_cycle_id"])
    atype=_active_ref(conn,"activity_types",req.activity_type_code,name="Activity Type")

    if req.application_method_code:
        _active_ref(
          conn,"application_methods",req.application_method_code,
          name="Application Method"
        )

    purposes=[
      _active_ref(conn,"activity_purposes",code,name="Activity Purpose")
      for code in req.purpose_codes
    ]

    dap_date=req.scheduled_date or req.planned_date
    planned_dap=_dap_for_date(cycle,dap_date) if dap_date else None

    status="SCHEDULED" if req.scheduled_date else "PLANNED"
    name_en=req.name_en or recommendation["title_en"]
    name_mr=req.name_mr or recommendation["title_mr"]
    description_en=req.description_en or recommendation["reason_en"]
    description_mr=req.description_mr or recommendation["reason_mr"]
    source_reference=f"INTELLIGENCE-RECOMMENDATION:{recommendation['id']}"

    row=conn.execute(
      """INSERT INTO public.activities(
           farm_id,crop_cycle_id,activity_type_id,application_method_code,status,
           planned_date,scheduled_date,planned_dap,
           planned_area,planned_area_unit_code,planned_pump_count,
           planned_water_volume,planned_water_unit_code,
           name_en,name_mr,description_en,description_mr,notes_en,notes_mr,
           source_type,source_reference,verification_status,source_confidence,
           created_by,updated_by
         )
         VALUES(
           %s,%s,%s,%s,%s,
           %s,%s,%s,
           %s,%s,%s,
           %s,%s,
           %s,%s,%s,%s,%s,%s,
           'RECOMMENDATION',%s,'CONFIRMED','CONFIRMED',
           %s,%s
         )
         RETURNING *""",
      (
        cycle["farm_id"],recommendation["crop_cycle_id"],atype["id"],
        req.application_method_code,status,
        req.planned_date,req.scheduled_date,planned_dap,
        req.planned_area,req.planned_area_unit_code,req.planned_pump_count,
        req.planned_water_volume,req.planned_water_unit_code,
        name_en,name_mr,description_en,description_mr,req.notes_en,req.notes_mr,
        source_reference,req.created_by,req.created_by,
      )
    ).fetchone()

    for p in purposes:
        conn.execute(
          """INSERT INTO public.activity_purpose_links(activity_id,activity_purpose_id)
             VALUES(%s,%s)""",
          (row["id"],p["id"])
        )

    _audit(
      conn,entity_type="ACTIVITY",entity_id=row["id"],action="CREATE",
      new_data=dict(row),changed_by=req.created_by
    )
    return row


def recommendation_to_activity(req):
    """Atomically create the proposed Activity and its Intelligence lineage."""
    with connection() as conn:
      try:
        # Transaction-scoped advisory lock makes concurrent retries deterministic,
        # even before the lineage row exists.
        conn.execute(
          "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
          (f"phase7-recommendation:{req.recommendation_id}",)
        )

        recommendation=conn.execute(
          """SELECT * FROM public.intelligence_recommendations
             WHERE id=%s FOR UPDATE""",
          (req.recommendation_id,)
        ).fetchone()
        if not recommendation:
            raise ActivityRegisterNotFound(
              "Recommendation not found. (शिफारस सापडली नाही.)"
            )
        if recommendation["status"]!="ACCEPTED":
            raise ActivityRegisterValidation(
              "Only an ACCEPTED recommendation can become a proposed Activity. "
              "(फक्त स्वीकारलेली शिफारस नियोजित क्रियाकलापात रूपांतरित करता येते.)"
            )

        existing=_existing_proposal(conn,req.recommendation_id)
        if existing:
            activity_id=existing["activity_id"]
            conn.commit()
            return {
              "duplicate":True,
              "recommendation_id":str(req.recommendation_id),
              "activity":get_activity(activity_id),
            }

        activity=_create_planned_activity_in_tx(conn,recommendation,req)

        conn.execute(
          """INSERT INTO public.planner_recommendation_links(
               recommendation_id,activity_id,created_by
             ) VALUES(%s,%s,%s)""",
          (req.recommendation_id,activity["id"],req.created_by)
        )
        conn.execute(
          """INSERT INTO public.planner_activity_controls(
               activity_id,priority,control_status,updated_by
             ) VALUES(%s,%s,'ACTIVE',%s)""",
          (activity["id"],req.priority,req.created_by)
        )
        _event(
          conn,activity["id"],"PROPOSAL_CREATED",
          new_data={
            "recommendation_id":str(req.recommendation_id),
            "priority":req.priority,
            "status":activity["status"],
          },
          changed_by=req.created_by
        )
        conn.commit()
        return {
          "duplicate":False,
          "recommendation_id":str(req.recommendation_id),
          "activity":get_activity(activity["id"]),
        }
      except Exception:
        conn.rollback()
        raise


def set_priority(activity_id,req):
    with connection() as conn:
      try:
        _require_activity(conn,activity_id,for_update=True)
        old=_control(conn,activity_id)
        old_priority=old["priority"] if old else "MEDIUM"
        old_status=old["control_status"] if old else "ACTIVE"
        conn.execute(
          """INSERT INTO public.planner_activity_controls(
               activity_id,priority,control_status,updated_by
             ) VALUES(%s,%s,%s,%s)
             ON CONFLICT(activity_id) DO UPDATE SET
               priority=excluded.priority,
               updated_by=excluded.updated_by,
               updated_at=now()""",
          (activity_id,req.priority,old_status,req.changed_by)
        )
        _event(
          conn,activity_id,"PRIORITY_CHANGED",
          old_data={"priority":old_priority},
          new_data={"priority":req.priority},
          changed_by=req.changed_by
        )
        conn.commit()
        return {"activity_id":str(activity_id),"priority":req.priority}
      except Exception:
        conn.rollback()
        raise


def hold_activity(activity_id,req):
    with connection() as conn:
      try:
        a=_require_activity(conn,activity_id,for_update=True)
        if a["status"] in TERMINAL:
            raise ActivityRegisterValidation(
              "Terminal Activity cannot be held. (पूर्ण/वगळलेला/रद्द क्रियाकलाप होल्ड करता येत नाही.)"
            )
        if req.hold_until and req.hold_until < date.today():
            raise ActivityRegisterValidation(
              "hold_until cannot be in the past. (होल्ड तारीख भूतकाळातील असू शकत नाही.)"
            )
        old=_control(conn,activity_id)
        priority=old["priority"] if old else "MEDIUM"
        conn.execute(
          """INSERT INTO public.planner_activity_controls(
               activity_id,priority,hold_until,hold_reason_en,hold_reason_mr,
               control_status,updated_by
             ) VALUES(%s,%s,%s,%s,%s,'HELD',%s)
             ON CONFLICT(activity_id) DO UPDATE SET
               hold_until=excluded.hold_until,
               hold_reason_en=excluded.hold_reason_en,
               hold_reason_mr=excluded.hold_reason_mr,
               control_status='HELD',
               updated_by=excluded.updated_by,
               updated_at=now()""",
          (
            activity_id,priority,req.hold_until,
            req.reason_en,req.reason_mr,req.changed_by
          )
        )
        _event(
          conn,activity_id,"HELD",
          old_data=dict(old) if old else None,
          new_data={
            "hold_until":req.hold_until,
            "reason_en":req.reason_en,
            "reason_mr":req.reason_mr,
          },
          changed_by=req.changed_by
        )
        conn.commit()
        return {
          "activity_id":str(activity_id),
          "control_status":"HELD",
          "hold_until":req.hold_until,
        }
      except Exception:
        conn.rollback()
        raise


def release_hold(activity_id,req):
    with connection() as conn:
      try:
        _require_activity(conn,activity_id,for_update=True)
        old=_control(conn,activity_id)
        if not old or old["control_status"]!="HELD":
            raise ActivityRegisterValidation(
              "Activity is not currently HELD. (क्रियाकलाप सध्या होल्डवर नाही.)"
            )
        conn.execute(
          """UPDATE public.planner_activity_controls SET
               hold_until=NULL,hold_reason_en=NULL,hold_reason_mr=NULL,
               control_status='ACTIVE',updated_by=%s,updated_at=now()
             WHERE activity_id=%s""",
          (req.changed_by,activity_id)
        )
        _event(
          conn,activity_id,"RELEASED",
          old_data=dict(old),
          new_data={"control_status":"ACTIVE"},
          changed_by=req.changed_by
        )
        conn.commit()
        return {"activity_id":str(activity_id),"control_status":"ACTIVE"}
      except Exception:
        conn.rollback()
        raise


def reschedule(activity_id,req):
    # Existing Phase 3 scheduler remains the lifecycle authority.
    before=get_activity(activity_id)["activity"]
    result=schedule_activity(
      activity_id,
      ScheduleCommand(
        scheduled_date=req.scheduled_date,
        changed_by=req.changed_by
      )
    )
    with connection() as conn:
      try:
        _event(
          conn,activity_id,"RESCHEDULED",
          old_data={"scheduled_date":before["scheduled_date"]},
          new_data={"scheduled_date":req.scheduled_date},
          changed_by=req.changed_by
        )
        conn.commit()
      except Exception:
        conn.rollback()
        raise
    return result


def dismiss(activity_id,req):
    with connection() as conn:
      try:
        a=_require_activity(conn,activity_id,for_update=True)
        if a["status"] in TERMINAL:
            raise ActivityRegisterValidation(
              "Terminal Activity cannot be dismissed from planner."
            )
        old=_control(conn,activity_id)
        priority=old["priority"] if old else "MEDIUM"
        conn.execute(
          """INSERT INTO public.planner_activity_controls(
               activity_id,priority,hold_reason_en,hold_reason_mr,
               control_status,updated_by
             ) VALUES(%s,%s,%s,%s,'DISMISSED',%s)
             ON CONFLICT(activity_id) DO UPDATE SET
               control_status='DISMISSED',
               hold_until=NULL,
               hold_reason_en=excluded.hold_reason_en,
               hold_reason_mr=excluded.hold_reason_mr,
               updated_by=excluded.updated_by,
               updated_at=now()""",
          (
            activity_id,priority,req.reason_en,req.reason_mr,req.changed_by
          )
        )
        _event(
          conn,activity_id,"DISMISSED",
          old_data=dict(old) if old else None,
          new_data={
            "control_status":"DISMISSED",
            "reason_en":req.reason_en,
            "reason_mr":req.reason_mr,
          },
          changed_by=req.changed_by
        )
        conn.commit()
        return {"activity_id":str(activity_id),"control_status":"DISMISSED"}
      except Exception:
        conn.rollback()
        raise


def proactive_board(farm_id=None,crop_cycle_id=None,date_from=None,date_to=None):
    today=date.today()
    date_from=date_from or today
    date_to=date_to or today+timedelta(days=7)
    if date_to < date_from:
        raise ActivityRegisterValidation("date_to cannot be before date_from.")

    base=planner_board(farm_id,crop_cycle_id,date_from,date_to)
    ids=[x["activity_id"] for x in base["activities"]]
    controls={}
    links={}

    with connection() as conn:
      if ids:
        for r in conn.execute(
          """SELECT * FROM public.planner_activity_controls
             WHERE activity_id=ANY(%s)""",(ids,)
        ).fetchall():
            controls[r["activity_id"]]=dict(r)

        for r in conn.execute(
          """SELECT
               l.activity_id,l.recommendation_id,
               r.recommendation_type,r.action_code,
               r.title_en recommendation_title_en,
               r.title_mr recommendation_title_mr,
               r.confidence,r.status recommendation_status
             FROM public.planner_recommendation_links l
             JOIN public.intelligence_recommendations r
               ON r.id=l.recommendation_id
             WHERE l.activity_id=ANY(%s)
               AND l.link_status='ACTIVE'""",(ids,)
        ).fetchall():
            links[r["activity_id"]]=dict(r)

    visible=[]
    for item in base["activities"]:
        ctl=controls.get(item["activity_id"])
        if ctl and ctl["control_status"]=="DISMISSED":
            continue

        item["planner_control"]=ctl or {
          "priority":"MEDIUM",
          "control_status":"ACTIVE",
          "hold_until":None,
          "hold_reason_en":None,
          "hold_reason_mr":None,
        }
        item["intelligence_source"]=links.get(item["activity_id"])

        if item["planner_control"]["control_status"]=="HELD":
            item["planner_bucket"]="HELD"
        visible.append(item)

    priority_order={"CRITICAL":0,"HIGH":1,"MEDIUM":2,"LOW":3}
    bucket_order={
      "OVERDUE":0,"TODAY":1,"NEXT_7_DAYS":2,"HELD":3,"LATER":4
    }
    visible.sort(
      key=lambda x:(
        bucket_order.get(x["planner_bucket"],9),
        priority_order.get(x["planner_control"]["priority"],2),
        x["effective_date"],
        str(x["activity_id"]),
      )
    )

    return {
      "as_of_date":today,
      "window":base["window"],
      "summary":{
        "overdue":sum(x["planner_bucket"]=="OVERDUE" for x in visible),
        "today":sum(x["planner_bucket"]=="TODAY" for x in visible),
        "upcoming":sum(x["planner_bucket"]=="NEXT_7_DAYS" for x in visible),
        "held":sum(x["planner_bucket"]=="HELD" for x in visible),
        "critical":sum(
          x["planner_control"]["priority"]=="CRITICAL" for x in visible
        ),
        "total":len(visible),
      },
      "activities":visible,
      "contract":{
        "recommendation_is_not_execution":True,
        "farmer_approval_required":True,
        "stock_mutation":"NONE",
        "weather_dependency":"PHASE_8",
      },
    }
