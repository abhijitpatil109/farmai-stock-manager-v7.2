from __future__ import annotations
from datetime import datetime,time,timezone
from ..db import connection
from ..schemas.activity_register import ObservationCreate
from .activity_register import create_observation

def record_farmer_outcome(req):
    return create_observation(req.crop_cycle_id,ObservationCreate(
      observation_type_code=req.observation_type_code,
      observed_at=datetime.combine(req.observed_date,time(12,0),tzinfo=timezone.utc),
      activity_id=req.activity_id,execution_id=req.execution_id,severity=req.severity,
      numeric_value=req.numeric_value,value_unit_code=req.value_unit_code,
      description_en=req.description_en,description_mr=req.description_mr,
      notes_en=req.notes_en,notes_mr=req.notes_mr,source_type="MANUAL",
      verification_status="CONFIRMED",created_by=req.created_by))

def search_activity_memory(crop_cycle_id=None,product_code=None,purpose_code=None,activity_type_code=None,date_from=None,date_to=None,dap_from=None,dap_to=None,limit=200):
    clauses=[];params=[]
    if crop_cycle_id:clauses.append("a.crop_cycle_id=%s");params.append(crop_cycle_id)
    if product_code:
        clauses.append("""EXISTS(SELECT 1 FROM public.activity_execution_inputs aei JOIN public.products px ON px.id=aei.product_id WHERE aei.execution_id=ae.id AND lower(px.product_code)=lower(%s))""");params.append(product_code)
    if purpose_code:
        clauses.append("""EXISTS(SELECT 1 FROM public.activity_purpose_links apl JOIN public.activity_purposes ap ON ap.id=apl.activity_purpose_id WHERE apl.activity_id=a.id AND ap.code=%s)""");params.append(purpose_code.upper())
    if activity_type_code:clauses.append("at.code=%s");params.append(activity_type_code.upper())
    if date_from:clauses.append("ae.execution_date>=%s");params.append(date_from)
    if date_to:clauses.append("ae.execution_date<=%s");params.append(date_to)
    if dap_from is not None:clauses.append("ae.dap_at_execution>=%s");params.append(dap_from)
    if dap_to is not None:clauses.append("ae.dap_at_execution<=%s");params.append(dap_to)
    sql="""SELECT a.id activity_id,ae.id execution_id,ae.execution_date,ae.dap_at_execution,ae.status execution_status,
      at.code activity_type_code,at.name_en activity_type_name_en,at.name_mr activity_type_name_mr,
      cc.cycle_code,cc.crop_name_en,cc.crop_name_mr,p.code plot_code,p.name_en plot_name_en,p.name_mr plot_name_mr,
      EXISTS(SELECT 1 FROM public.activity_execution_corrections cx WHERE cx.original_execution_id=ae.id) superseded_by_correction
      FROM public.activity_executions ae JOIN public.activities a ON a.id=ae.activity_id
      JOIN public.activity_types at ON at.id=a.activity_type_id JOIN public.crop_cycles cc ON cc.id=a.crop_cycle_id
      JOIN public.plots p ON p.id=cc.plot_id"""
    if clauses:sql+=" WHERE "+" AND ".join(clauses)
    sql+=" ORDER BY ae.execution_date DESC,ae.created_at DESC LIMIT %s";params.append(limit)
    with connection() as c:
      rows=[dict(x) for x in c.execute(sql,tuple(params)).fetchall()]
      for r in rows:
        r["purposes"]=[dict(x) for x in c.execute("""SELECT ap.code,ap.name_en,ap.name_mr FROM public.activity_purpose_links l JOIN public.activity_purposes ap ON ap.id=l.activity_purpose_id WHERE l.activity_id=%s ORDER BY ap.sort_order""",(r["activity_id"],)).fetchall()]
        r["products"]=[dict(x) for x in c.execute("""SELECT p.product_code,p.product_name product_name_en,pdm.product_name_mr,i.actual_dose,i.actual_dose_unit_code,i.dose_basis_code,i.actual_total_quantity,i.actual_total_unit_code,i.stock_sync_status FROM public.activity_execution_inputs i JOIN public.products p ON p.id=i.product_id LEFT JOIN public.product_display_metadata pdm ON pdm.product_id=p.id WHERE i.execution_id=%s ORDER BY i.created_at""",(r["execution_id"],)).fetchall()]
      return {"count":len(rows),"results":rows}
