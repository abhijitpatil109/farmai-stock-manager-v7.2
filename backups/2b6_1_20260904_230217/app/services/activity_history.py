"""
FarmAI Activity Register — Phase 2B.6 Authoritative History Read Model.
Read-only farmer/UI projection. No writes. No Stock mutation.
"""
from __future__ import annotations
from ..db import connection
from .activity_register import ActivityRegisterNotFound

def _d(row): return dict(row) if row is not None else None
def _ds(rows): return [dict(x) for x in rows]

def crop_history(crop_cycle_id):
    with connection() as conn:
        cycle=conn.execute("""
            SELECT cc.*,f.name_en farm_name_en,f.name_mr farm_name_mr,
                   p.code plot_code,p.name_en plot_name_en,p.name_mr plot_name_mr
            FROM public.crop_cycles cc
            JOIN public.farms f ON f.id=cc.farm_id
            JOIN public.plots p ON p.id=cc.plot_id
            WHERE cc.id=%s
        """,(crop_cycle_id,)).fetchone()
        if not cycle:
            raise ActivityRegisterNotFound("Crop Cycle not found. (पीक चक्र सापडले नाही.)")

        rows=conn.execute("""
            SELECT
              a.id activity_id,a.status activity_status,
              a.name_en activity_name_en,a.name_mr activity_name_mr,
              a.description_en activity_description_en,a.description_mr activity_description_mr,
              a.notes_en activity_notes_en,a.notes_mr activity_notes_mr,
              a.source_type,a.source_reference,a.verification_status,a.source_confidence,
              at.code activity_type_code,at.name_en activity_type_name_en,at.name_mr activity_type_name_mr,
              a.application_method_code,
              am.name_en application_method_name_en,am.name_mr application_method_name_mr,
              ae.id execution_id,ae.execution_no,ae.execution_date,ae.status execution_status,
              ae.dap_at_execution,ae.area_treated,ae.area_unit_code,ae.pump_count,
              ae.water_volume,ae.water_unit_code,ae.performed_by,
              ae.notes_en execution_notes_en,ae.notes_mr execution_notes_mr
            FROM public.activities a
            JOIN public.activity_types at ON at.id=a.activity_type_id
            LEFT JOIN public.application_methods am ON am.code=a.application_method_code
            LEFT JOIN public.activity_executions ae ON ae.activity_id=a.id
            WHERE a.crop_cycle_id=%s
            ORDER BY COALESCE(ae.execution_date,a.scheduled_date,a.planned_date,a.created_at::date),
                     a.created_at,ae.execution_no
        """,(crop_cycle_id,)).fetchall()

        out=[]
        for row in rows:
            item=dict(row)
            aid=item["activity_id"]; eid=item["execution_id"]
            item["purposes"]=_ds(conn.execute("""
                SELECT ap.code,ap.name_en,ap.name_mr
                FROM public.activity_purpose_links apl
                JOIN public.activity_purposes ap ON ap.id=apl.activity_purpose_id
                WHERE apl.activity_id=%s ORDER BY ap.sort_order,ap.code
            """,(aid,)).fetchall())

            item["inputs"]=_ds(conn.execute("""
                SELECT aei.id execution_input_id,
                       p.id product_id,p.product_code,p.product_name,p.brand,p.category,p.base_unit,
                       pdm.display_name_en product_display_name_en,pdm.display_name_mr product_display_name_mr,
                       aei.actual_dose,aei.actual_dose_unit_code,aei.dose_basis_code,
                       dbt.name_en dose_basis_name_en,dbt.name_mr dose_basis_name_mr,
                       aei.actual_total_quantity,aei.actual_total_unit_code,
                       aei.stock_sync_status,aei.notes_en input_notes_en,aei.notes_mr input_notes_mr
                FROM public.activity_execution_inputs aei
                JOIN public.products p ON p.id=aei.product_id
                LEFT JOIN public.product_display_metadata pdm ON pdm.product_id=p.id
                LEFT JOIN public.dose_basis_types dbt ON dbt.code=aei.dose_basis_code
                WHERE aei.execution_id=%s ORDER BY aei.created_at
            """,(eid,)).fetchall()) if eid else []
            out.append(item)

        completed=[x for x in out if x["execution_id"] and x["execution_status"]=="COMPLETED"]
        return {
            "crop_cycle":_d(cycle),
            "summary":{
                "activity_count":len({x["activity_id"] for x in out}),
                "execution_count":sum(1 for x in out if x["execution_id"]),
                "completed_execution_count":len(completed),
                "first_execution_date":min((x["execution_date"] for x in completed),default=None),
                "last_execution_date":max((x["execution_date"] for x in completed),default=None),
            },
            "history":out,
        }

def activity_history_detail(activity_id):
    with connection() as conn:
        row=conn.execute("SELECT crop_cycle_id FROM public.activities WHERE id=%s",(activity_id,)).fetchone()
        if not row:
            raise ActivityRegisterNotFound("Activity not found. (क्रियाकलाप सापडला नाही.)")
    h=crop_history(row["crop_cycle_id"])
    matches=[x for x in h["history"] if x["activity_id"]==activity_id]
    return {"crop_cycle":h["crop_cycle"],"activity_id":activity_id,"executions":matches}
