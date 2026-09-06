from __future__ import annotations
from ..db import connection
from .activity_register import ActivityRegisterNotFound,ActivityRegisterValidation
def cycle_summary(crop_cycle_id):
    with connection() as c:
      cc=c.execute("""SELECT cc.*,p.code plot_code,p.name_en plot_name_en,p.name_mr plot_name_mr
       FROM public.crop_cycles cc JOIN public.plots p ON p.id=cc.plot_id WHERE cc.id=%s""",(crop_cycle_id,)).fetchone()
      if not cc:raise ActivityRegisterNotFound("Crop cycle not found.")
      metrics=[dict(x) for x in c.execute("""SELECT metric_code,metric_date,dap,value,unit,quality_status,source_reference
       FROM public.season_metric_series WHERE crop_cycle_id=%s ORDER BY metric_code,metric_date""",(crop_cycle_id,)).fetchall()]
    return {"crop_cycle":dict(cc),"metrics":metrics,"yield_prediction":None,
            "guardrail":"Phase 9 does not produce yield prediction without validated multi-season outcome data."}
def compare_cycles(current_id,baseline_id,metric="NDVI"):
    with connection() as c:
      a=c.execute("SELECT * FROM public.crop_cycles WHERE id=%s",(current_id,)).fetchone();b=c.execute("SELECT * FROM public.crop_cycles WHERE id=%s",(baseline_id,)).fetchone()
      if not a or not b:raise ActivityRegisterNotFound("Crop cycle not found.")
      if (a["crop_name_en"] or "").lower()!=(b["crop_name_en"] or "").lower():raise ActivityRegisterValidation("Comparison requires same crop.")
      rows=c.execute("""SELECT x.dap,x.value current_value,y.value baseline_value FROM public.season_metric_series x
       JOIN public.season_metric_series y ON y.crop_cycle_id=%s AND y.metric_code=x.metric_code AND y.dap=x.dap
       WHERE x.crop_cycle_id=%s AND x.metric_code=%s AND x.dap IS NOT NULL
       AND x.quality_status IN ('VALID','PARTIAL') AND y.quality_status IN ('VALID','PARTIAL') ORDER BY x.dap""",
       (baseline_id,current_id,metric)).fetchall()
    return {"metric_code":metric,"alignment":"DAP","matches":[{"dap":r["dap"],"current":float(r["current_value"]),
      "baseline":float(r["baseline_value"]),"delta":float(r["current_value"]-r["baseline_value"])} for r in rows],
      "confidence":"MEDIUM" if len(rows)>=3 else "INSUFFICIENT_DATA"}
