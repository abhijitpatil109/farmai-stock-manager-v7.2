"""FarmAI Activity Planner — Phase 3 Operational MVP.
No Stock writes. Activity Register remains agronomic operational truth.
"""
from __future__ import annotations
from datetime import date, timedelta
from ..db import connection
from .activity_register import (
    ActivityRegisterNotFound, ActivityRegisterValidation,
    _activity_header, _crop_cycle, _dap_for_date, _active_ref,
    _product_by_code, _audit, get_activity
)

EDITABLE={"DRAFT","PLANNED","SCHEDULED"}
TERMINAL={"COMPLETED","SKIPPED","CANCELLED"}

def _d(r): return dict(r) if r else None
def _ds(rs): return [dict(x) for x in rs]

def _planner_date_sql():
    return "COALESCE(a.scheduled_date,a.planned_date,a.created_at::date)"

def planner_board(farm_id=None, crop_cycle_id=None, date_from=None, date_to=None):
    today=date.today()
    date_from=date_from or today
    date_to=date_to or (today+timedelta(days=7))
    clauses=["a.status NOT IN ('COMPLETED','SKIPPED','CANCELLED')"]
    params=[]
    if farm_id:
        clauses.append("a.farm_id=%s"); params.append(farm_id)
    if crop_cycle_id:
        clauses.append("a.crop_cycle_id=%s"); params.append(crop_cycle_id)
    sql=f"""
      SELECT a.id activity_id,a.status,a.planned_date,a.scheduled_date,a.planned_dap,
             a.planned_area,a.planned_area_unit_code,a.planned_pump_count,
             a.planned_water_volume,a.planned_water_unit_code,
             a.name_en,a.name_mr,a.description_en,a.description_mr,a.notes_en,a.notes_mr,
             at.code activity_type_code,at.name_en activity_type_name_en,at.name_mr activity_type_name_mr,
             am.name_en application_method_name_en,am.name_mr application_method_name_mr,
             cc.id crop_cycle_id,cc.cycle_code,cc.crop_name_en,cc.crop_name_mr,
             cc.dap_baseline_date,cc.dap_baseline_type,
             p.code plot_code,p.name_en plot_name_en,p.name_mr plot_name_mr,
             {_planner_date_sql()} effective_date,
             ({_planner_date_sql()}-cc.dap_baseline_date) effective_dap,
             (SELECT count(*) FROM public.activity_inputs ai WHERE ai.activity_id=a.id) planned_input_count
      FROM public.activities a
      JOIN public.activity_types at ON at.id=a.activity_type_id
      LEFT JOIN public.application_methods am ON am.code=a.application_method_code
      JOIN public.crop_cycles cc ON cc.id=a.crop_cycle_id
      JOIN public.plots p ON p.id=cc.plot_id
      WHERE {" AND ".join(clauses)}
      ORDER BY {_planner_date_sql()},cc.crop_name_en,at.sort_order,a.created_at
    """
    with connection() as conn:
        rows=_ds(conn.execute(sql,tuple(params)).fetchall())
        ids=[x["activity_id"] for x in rows]
        by={}
        if ids:
            for x in _ds(conn.execute("""
                SELECT ai.activity_id,ai.sequence_no,p.product_code,p.product_name,p.brand,p.base_unit,
                       ai.planned_dose,ai.planned_dose_unit_code,ai.dose_basis_code,
                       db.name_en dose_basis_name_en,db.name_mr dose_basis_name_mr,
                       ai.planned_total_quantity,ai.planned_total_unit_code
                FROM public.activity_inputs ai
                JOIN public.products p ON p.id=ai.product_id
                LEFT JOIN public.dose_basis_types db ON db.code=ai.dose_basis_code
                WHERE ai.activity_id=ANY(%s)
                ORDER BY ai.activity_id,ai.sequence_no,ai.created_at
            """,(ids,)).fetchall()):
                by.setdefault(x["activity_id"],[]).append(x)
        for x in rows:
            x["inputs"]=by.get(x["activity_id"],[])
            ed=x["effective_date"]
            if ed < today: bucket="OVERDUE"
            elif ed == today: bucket="TODAY"
            elif ed <= date_to: bucket="NEXT_7_DAYS"
            else: bucket="LATER"
            x["planner_bucket"]=bucket
        visible=[x for x in rows if x["effective_date"]<=date_to or x["planner_bucket"]=="OVERDUE"]
        return {
          "as_of_date":today,
          "window":{"from":date_from,"to":date_to},
          "summary":{
            "overdue":sum(x["planner_bucket"]=="OVERDUE" for x in visible),
            "today":sum(x["planner_bucket"]=="TODAY" for x in visible),
            "next_7_days":sum(x["planner_bucket"]=="NEXT_7_DAYS" for x in visible),
            "total":len(visible)
          },
          "activities":visible
        }

def update_plan(activity_id, req):
    with connection() as conn:
        try:
            a=_activity_header(conn,activity_id)
            if a["status"] not in EDITABLE:
                raise ActivityRegisterValidation("Only Draft/Planned/Scheduled Activities can be edited. (फक्त मसुदा/नियोजित क्रियाकलाप बदलता येतात.)")
            cycle=_crop_cycle(conn,a["crop_cycle_id"])
            values=req.model_dump(exclude_unset=True)
            purpose_codes=values.pop("purpose_codes",None)
            inputs=values.pop("inputs",None)
            updated_by=values.pop("updated_by",None)
            old=dict(a)
            if values:
                allowed={"planned_date","scheduled_date","planned_area","planned_area_unit_code","planned_pump_count",
                         "planned_water_volume","planned_water_unit_code","name_en","name_mr","description_en",
                         "description_mr","notes_en","notes_mr"}
                bad=set(values)-allowed
                if bad: raise ActivityRegisterValidation(f"Unsupported plan fields: {sorted(bad)}")
                if "scheduled_date" in values and values["scheduled_date"] is not None:
                    values["planned_dap"]=_dap_for_date(cycle,values["scheduled_date"])
                elif "planned_date" in values and values["planned_date"] is not None:
                    values["planned_dap"]=_dap_for_date(cycle,values["planned_date"])
                sets=[f"{k}=%s" for k in values]
                params=list(values.values())
                sets += ["updated_at=now()","updated_by=%s"]; params += [updated_by,activity_id]
                conn.execute(f"UPDATE public.activities SET {','.join(sets)} WHERE id=%s",tuple(params))
            if purpose_codes is not None:
                conn.execute("DELETE FROM public.activity_purpose_links WHERE activity_id=%s",(activity_id,))
                for code in purpose_codes:
                    p=_active_ref(conn,"activity_purposes",code,name="Activity Purpose")
                    conn.execute("INSERT INTO public.activity_purpose_links(activity_id,activity_purpose_id) VALUES(%s,%s)",(activity_id,p["id"]))
            if inputs is not None:
                conn.execute("DELETE FROM public.activity_inputs WHERE activity_id=%s",(activity_id,))
                for item in inputs:
                    p=_product_by_code(conn,item.product_code)
                    if item.planned_dose_unit_code:
                        _active_ref(conn,"measurement_units",item.planned_dose_unit_code.upper(),name="Unit")
                        _active_ref(conn,"dose_basis_types",item.dose_basis_code.upper(),name="Dose Basis")
                    if item.planned_total_unit_code:
                        _active_ref(conn,"measurement_units",item.planned_total_unit_code.upper(),name="Unit")
                    conn.execute("""
                      INSERT INTO public.activity_inputs(activity_id,product_id,sequence_no,planned_dose,
                      planned_dose_unit_code,dose_basis_code,planned_total_quantity,planned_total_unit_code,notes_en,notes_mr)
                      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,(activity_id,p["id"],item.sequence_no,item.planned_dose,
                         item.planned_dose_unit_code.upper() if item.planned_dose_unit_code else None,
                         item.dose_basis_code.upper() if item.dose_basis_code else None,
                         item.planned_total_quantity,
                         item.planned_total_unit_code.upper() if item.planned_total_unit_code else None,
                         item.notes_en,item.notes_mr))
            new=conn.execute("SELECT * FROM public.activities WHERE id=%s",(activity_id,)).fetchone()
            _audit(conn,entity_type="ACTIVITY",entity_id=activity_id,action="PLAN_UPDATE",old_data=old,new_data=dict(new),changed_by=updated_by)
            conn.commit()
            return get_activity(activity_id)
        except Exception:
            conn.rollback(); raise

def schedule_activity(activity_id, req):
    with connection() as conn:
        try:
            a=_activity_header(conn,activity_id)
            if a["status"] not in {"DRAFT","PLANNED","SCHEDULED"}:
                raise ActivityRegisterValidation("Only Draft/Planned/Scheduled Activities can be scheduled.")
            cycle=_crop_cycle(conn,a["crop_cycle_id"])
            dap=_dap_for_date(cycle,req.scheduled_date)
            old={"status":a["status"],"scheduled_date":a["scheduled_date"],"planned_dap":a["planned_dap"]}
            conn.execute("""UPDATE public.activities SET status='SCHEDULED',scheduled_date=%s,planned_dap=%s,
                         updated_at=now(),updated_by=%s WHERE id=%s""",(req.scheduled_date,dap,req.changed_by,activity_id))
            _audit(conn,entity_type="ACTIVITY",entity_id=activity_id,action="SCHEDULE",old_data=old,
                   new_data={"status":"SCHEDULED","scheduled_date":req.scheduled_date,"planned_dap":dap},
                   changed_by=req.changed_by)
            conn.commit(); return get_activity(activity_id)
        except Exception:
            conn.rollback(); raise

def start_activity(activity_id, req):
    with connection() as conn:
        try:
            a=_activity_header(conn,activity_id)
            if a["status"] not in {"PLANNED","SCHEDULED"}:
                raise ActivityRegisterValidation("Only Planned/Scheduled Activities can be started.")
            conn.execute("UPDATE public.activities SET status='IN_PROGRESS',updated_at=now(),updated_by=%s WHERE id=%s",(req.changed_by,activity_id))
            _audit(conn,entity_type="ACTIVITY",entity_id=activity_id,action="STATUS_CHANGE",
                   old_data={"status":a["status"]},new_data={"status":"IN_PROGRESS"},changed_by=req.changed_by)
            conn.commit(); return get_activity(activity_id)
        except Exception:
            conn.rollback(); raise

def plan_vs_actual(activity_id):
    with connection() as conn:
        a=_activity_header(conn,activity_id)
        planned=_ds(conn.execute("""
          SELECT ai.id,p.id product_id,p.product_code,p.product_name,
                 ai.planned_dose,ai.planned_dose_unit_code,ai.dose_basis_code,
                 ai.planned_total_quantity,ai.planned_total_unit_code
          FROM public.activity_inputs ai JOIN public.products p ON p.id=ai.product_id
          WHERE ai.activity_id=%s ORDER BY ai.sequence_no,ai.created_at
        """,(activity_id,)).fetchall())
        actual=_ds(conn.execute("""
          SELECT p.id product_id,p.product_code,p.product_name,
                 sum(aei.actual_total_quantity) actual_total_quantity,
                 max(aei.actual_total_unit_code) actual_total_unit_code,
                 max(aei.actual_dose) actual_dose,max(aei.actual_dose_unit_code) actual_dose_unit_code,
                 max(aei.dose_basis_code) dose_basis_code
          FROM public.activity_execution_inputs aei JOIN public.products p ON p.id=aei.product_id
          WHERE aei.activity_id=%s GROUP BY p.id,p.product_code,p.product_name ORDER BY p.product_name
        """,(activity_id,)).fetchall())
        amap={x["product_id"]:x for x in actual}; pmap={x["product_id"]:x for x in planned}
        products=[]
        for pid in list(dict.fromkeys(list(pmap)+list(amap))):
            p=pmap.get(pid); ac=amap.get(pid)
            kind="MATCHED"
            if p and not ac: kind="PLANNED_NOT_USED"
            elif ac and not p: kind="SUBSTITUTED_OR_ADDED"
            elif p and ac:
                if p["planned_total_quantity"] is not None and ac["actual_total_quantity"] is not None:
                    if p["planned_total_unit_code"]==ac["actual_total_unit_code"] and p["planned_total_quantity"]!=ac["actual_total_quantity"]:
                        kind="QUANTITY_DEVIATION"
            products.append({"product_id":pid,"product_code":(p or ac)["product_code"],
                             "product_name":(p or ac)["product_name"],"comparison":kind,
                             "planned":p,"actual":ac})
        return {"activity":dict(a),"products":products,
                "has_deviation":any(x["comparison"]!="MATCHED" for x in products)}
