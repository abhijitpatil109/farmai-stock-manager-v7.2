from __future__ import annotations
from uuid import UUID
from ..db import connection
from ..schemas.activity_stock_integration import StockReverseRequest
from .activity_register import ActivityRegisterNotFound,ActivityRegisterValidation,_audit
from .activity_stock_integration import reverse_execution_stock
from .activity_farmer_entry import complete_farmer_activity

def correct_execution(req):
    oid=UUID(req.original_execution_id)
    with connection() as c:
        ex=c.execute("SELECT * FROM public.activity_executions WHERE id=%s",(oid,)).fetchone()
        if not ex:raise ActivityRegisterNotFound("Original Execution not found. (मूळ अंमलबजावणी सापडली नाही.)")
        old=c.execute("SELECT * FROM public.activity_execution_corrections WHERE original_execution_id=%s",(oid,)).fetchone()
        if old:
            return {"duplicate":True,"correction":dict(old)}
    reverse_execution_stock(oid,StockReverseRequest(changed_by=req.corrected_by,reason_en=req.reason_en,reason_mr=req.reason_mr))
    replacement=complete_farmer_activity(req.replacement)
    rex=replacement["activity"]["executions"][-1]
    with connection() as c:
      try:
        row=c.execute("""INSERT INTO public.activity_execution_corrections(
          original_execution_id,replacement_execution_id,reason_en,reason_mr,corrected_by)
          VALUES(%s,%s,%s,%s,%s) ON CONFLICT(original_execution_id) DO UPDATE SET
          reason_en=EXCLUDED.reason_en,reason_mr=EXCLUDED.reason_mr
          RETURNING *""",(oid,rex["id"],req.reason_en,req.reason_mr,req.corrected_by)).fetchone()
        _audit(c,entity_type="EXECUTION",entity_id=oid,action="CORRECTION",
               old_data={"execution_id":str(oid)},new_data={"replacement_execution_id":str(rex["id"])},
               reason_en=req.reason_en,reason_mr=req.reason_mr,changed_by=req.corrected_by)
        c.commit();return {"duplicate":False,"correction":dict(row),"replacement":replacement}
      except Exception:c.rollback();raise

def correction_lineage(execution_id):
    with connection() as c:
        row=c.execute("""SELECT x.*,oe.activity_id original_activity_id,re.activity_id replacement_activity_id
        FROM public.activity_execution_corrections x
        JOIN public.activity_executions oe ON oe.id=x.original_execution_id
        JOIN public.activity_executions re ON re.id=x.replacement_execution_id
        WHERE x.original_execution_id=%s OR x.replacement_execution_id=%s""",(execution_id,execution_id)).fetchone()
        return dict(row) if row else None
