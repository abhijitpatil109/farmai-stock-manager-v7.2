from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from ..db import connection
from ..quantity import normalize_quantity, QuantityNormalizationError
from .activity_register import ActivityRegisterNotFound, ActivityRegisterValidation

def D(v): return Decimal(str(v or 0))
def _txn_no(): return f"TXN-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid4().hex[:8].upper()}"
def _loc(c,code):
    r=c.execute("SELECT * FROM public.stock_locations WHERE lower(location_code)=lower(%s) AND active=true",(code,)).fetchone()
    if not r: raise ActivityRegisterValidation("Stock location not found.")
    return r
def _prod(c,pid):
    r=c.execute("SELECT * FROM public.products WHERE id=%s AND active=true",(pid,)).fetchone()
    if not r: raise ActivityRegisterValidation("Product not found.")
    return r
def _physical(c,pid,lid):
    return D(c.execute("SELECT COALESCE(SUM(quantity_in-quantity_out),0) q FROM public.stock_transactions WHERE product_id=%s AND location_id=%s AND status='CONFIRMED'",(pid,lid)).fetchone()["q"])
def _reserved(c,pid,lid,exclude=None):
    sql="SELECT COALESCE(SUM(quantity_reserved-quantity_consumed-quantity_released),0) q FROM public.stock_reservations WHERE product_id=%s AND location_id=%s AND status='ACTIVE'"
    params=[pid,lid]
    if exclude: sql+=" AND id<>%s"; params.append(exclude)
    return D(c.execute(sql,tuple(params)).fetchone()["q"])
def _available(c,pid,lid,exclude=None): return _physical(c,pid,lid)-_reserved(c,pid,lid,exclude)
def _norm(q,u,base):
    try: return normalize_quantity(q,u,base)
    except QuantityNormalizationError as e: raise ActivityRegisterValidation(str(e))
def _planned(x,p):
    if x["planned_total_quantity"] is None or not x["planned_total_unit_code"]: return None
    return _norm(x["planned_total_quantity"],x["planned_total_unit_code"],p["base_unit"])
def _actual(x,ex,p):
    if x["actual_total_quantity"] is not None and x["actual_total_unit_code"]:
        return _norm(x["actual_total_quantity"],x["actual_total_unit_code"],p["base_unit"])
    if x["actual_dose"] is None or not x["actual_dose_unit_code"] or not x["dose_basis_code"]: return None
    m=None
    if x["dose_basis_code"]=="PER_PUMP" and ex["pump_count"] is not None: m=D(ex["pump_count"])
    elif x["dose_basis_code"]=="PER_LITRE_WATER" and ex["water_volume"] is not None and str(ex["water_unit_code"]).upper()=="L": m=D(ex["water_volume"])
    elif x["dose_basis_code"]=="TOTAL": m=Decimal("1")
    return None if m is None else _norm(D(x["actual_dose"])*m,x["actual_dose_unit_code"],p["base_unit"])

def stock_preview(activity_id,location_code="MAIN"):
    with connection() as c:
        a=c.execute("SELECT * FROM public.activities WHERE id=%s",(activity_id,)).fetchone()
        if not a: raise ActivityRegisterNotFound("Activity not found.")
        loc=_loc(c,location_code); out=[]
        rows=c.execute("SELECT ai.*,p.product_code,p.product_name,p.base_unit FROM public.activity_inputs ai JOIN public.products p ON p.id=ai.product_id WHERE ai.activity_id=%s ORDER BY ai.sequence_no,ai.created_at",(activity_id,)).fetchall()
        for x in rows:
            p=_prod(c,x["product_id"]); q=_planned(x,p); av=_available(c,p["id"],loc["id"],x["stock_reservation_id"])
            out.append({"activity_input_id":x["id"],"product_code":p["product_code"],"product_name":p["product_name"],"required_quantity":q,"unit":p["base_unit"],"available_quantity":av,"sufficiency":"UNKNOWN" if q is None else ("AVAILABLE" if av>=q else ("PARTIAL" if av>0 else "UNAVAILABLE")),"stock_reservation_id":x["stock_reservation_id"],"stock_reservation_status":x["stock_reservation_status"]})
        return {"activity_id":activity_id,"activity_status":a["status"],"location_code":loc["location_code"],"inputs":out}

def reserve_activity(activity_id,req):
    with connection() as c:
      try:
        a=c.execute("SELECT * FROM public.activities WHERE id=%s FOR UPDATE",(activity_id,)).fetchone()
        if not a: raise ActivityRegisterNotFound("Activity not found.")
        if a["status"] not in ("PLANNED","SCHEDULED"): raise ActivityRegisterValidation("Reservation requires PLANNED/SCHEDULED Activity.")
        loc=_loc(c,req.location_code); result=[]
        for x in c.execute("SELECT * FROM public.activity_inputs WHERE activity_id=%s ORDER BY sequence_no,created_at FOR UPDATE",(activity_id,)).fetchall():
            p=_prod(c,x["product_id"]); q=_planned(x,p)
            if q is None: raise ActivityRegisterValidation(f"{p['product_code']}: planned total quantity/unit required.")
            if x["stock_reservation_id"]:
                sr=c.execute("SELECT * FROM public.stock_reservations WHERE id=%s",(x["stock_reservation_id"],)).fetchone()
                if sr and sr["status"]=="ACTIVE": result.append({"product_code":p["product_code"],"reservation_id":sr["id"],"duplicate":True}); continue
            c.execute("SELECT id FROM public.products WHERE id=%s FOR UPDATE",(p["id"],))
            av=_available(c,p["id"],loc["id"])
            if q>av: raise ActivityRegisterValidation(f"Insufficient stock for {p['product_code']}: required {q}, available {av} {p['base_unit']}.")
            key=f"activity:{activity_id}:input:{x['id']}:reserve"
            sr=c.execute("SELECT * FROM public.stock_reservations WHERE idempotency_key=%s",(key,)).fetchone()
            if not sr: sr=c.execute("INSERT INTO public.stock_reservations(external_task_id,product_id,location_id,quantity_reserved,unit,required_date,status,idempotency_key) VALUES(%s,%s,%s,%s,%s,%s,'ACTIVE',%s) RETURNING *",(str(activity_id),p["id"],loc["id"],q,p["base_unit"],req.required_date or a["scheduled_date"] or a["planned_date"],key)).fetchone()
            c.execute("UPDATE public.activity_inputs SET stock_reservation_id=%s,stock_reservation_status='RESERVED' WHERE id=%s",(sr["id"],x["id"]))
            result.append({"product_code":p["product_code"],"reservation_id":sr["id"],"quantity_reserved":q,"unit":p["base_unit"],"duplicate":False})
        c.commit(); return {"activity_id":activity_id,"status":"RESERVED","reservations":result}
      except Exception: c.rollback(); raise

def release_activity(activity_id,req):
    with connection() as c:
      try:
        out=[]
        rows=c.execute("SELECT * FROM public.activity_inputs WHERE activity_id=%s FOR UPDATE",(activity_id,)).fetchall()
        for x in rows:
            if not x["stock_reservation_id"]: continue
            sr=c.execute("SELECT * FROM public.stock_reservations WHERE id=%s FOR UPDATE",(x["stock_reservation_id"],)).fetchone()
            if not sr or sr["status"]!="ACTIVE": continue
            rem=D(sr["quantity_reserved"])-D(sr["quantity_consumed"])-D(sr["quantity_released"])
            if rem>0:
                key=f"activity:{activity_id}:reservation:{sr['id']}:release"
                if not c.execute("SELECT 1 FROM public.reservation_events WHERE idempotency_key=%s",(key,)).fetchone():
                    c.execute("INSERT INTO public.reservation_events(reservation_id,event_type,idempotency_key) VALUES(%s,'RELEASED',%s)",(sr["id"],key))
                c.execute("UPDATE public.stock_reservations SET quantity_released=quantity_released+%s,status='RELEASED' WHERE id=%s",(rem,sr["id"]))
                c.execute("UPDATE public.activity_inputs SET stock_reservation_status='RELEASED' WHERE id=%s",(x["id"],))
                out.append({"reservation_id":sr["id"],"released_quantity":rem,"unit":sr["unit"]})
        c.commit(); return {"activity_id":activity_id,"released":out}
      except Exception: c.rollback(); raise

def sync_execution(execution_id,req):
    with connection() as c:
      try:
        ex=c.execute("SELECT * FROM public.activity_executions WHERE id=%s FOR UPDATE",(execution_id,)).fetchone()
        if not ex: raise ActivityRegisterNotFound("Execution not found.")
        if ex["status"] not in ("PARTIALLY_COMPLETED","COMPLETED"): raise ActivityRegisterValidation("Execution must be PARTIALLY_COMPLETED/COMPLETED.")
        loc=_loc(c,req.location_code); out=[]
        rows=c.execute("SELECT aei.*,ai.stock_reservation_id,ai.id planned_input_id FROM public.activity_execution_inputs aei LEFT JOIN public.activity_inputs ai ON ai.id=aei.activity_input_id WHERE aei.execution_id=%s ORDER BY aei.created_at FOR UPDATE",(execution_id,)).fetchall()
        for x in rows:
            p=_prod(c,x["product_id"])
            if x["stock_transaction_id"]: out.append({"execution_input_id":x["id"],"product_code":p["product_code"],"transaction_id":x["stock_transaction_id"],"duplicate":True}); continue
            q=_actual(x,ex,p)
            if q is None or q<=0: raise ActivityRegisterValidation(f"{p['product_code']}: actual total cannot be derived for Stock sync.")
            c.execute("SELECT id FROM public.products WHERE id=%s FOR UPDATE",(p["id"],))
            sr=c.execute("SELECT * FROM public.stock_reservations WHERE id=%s FOR UPDATE",(x["stock_reservation_id"],)).fetchone() if x["stock_reservation_id"] else None
            if sr and sr["status"]=="ACTIVE":
                if q>_physical(c,p["id"],loc["id"]): raise ActivityRegisterValidation(f"Insufficient physical stock for {p['product_code']}.")
            elif q>_available(c,p["id"],loc["id"]): raise ActivityRegisterValidation(f"Insufficient available stock for {p['product_code']}.")
            key=f"activity-execution-input:{x['id']}:usage"
            tx=c.execute("SELECT * FROM public.stock_transactions WHERE idempotency_key=%s",(key,)).fetchone()
            if not tx: tx=c.execute("INSERT INTO public.stock_transactions(transaction_no,transaction_type,product_id,location_id,quantity_in,quantity_out,unit,effective_at,notes,idempotency_key,external_task_id,external_activity_id) VALUES(%s,'USAGE',%s,%s,0,%s,%s,%s,%s,%s,%s,%s) RETURNING *",(_txn_no(),p["id"],loc["id"],q,p["base_unit"],ex["execution_date"],f"Activity Register execution {execution_id}",key,str(execution_id),str(ex["activity_id"]))).fetchone()
            c.execute("UPDATE public.activity_execution_inputs SET stock_transaction_id=%s,stock_sync_status='SYNCED' WHERE id=%s",(tx["id"],x["id"]))
            if sr and sr["status"]=="ACTIVE":
                rem=D(sr["quantity_reserved"])-D(sr["quantity_consumed"])-D(sr["quantity_released"]); used=min(q,rem)
                if used>0: c.execute("UPDATE public.stock_reservations SET quantity_consumed=quantity_consumed+%s WHERE id=%s",(used,sr["id"]))
                sr2=c.execute("SELECT * FROM public.stock_reservations WHERE id=%s",(sr["id"],)).fetchone(); left=D(sr2["quantity_reserved"])-D(sr2["quantity_consumed"])-D(sr2["quantity_released"])
                if left<=0:
                    c.execute("UPDATE public.stock_reservations SET status='CONSUMED' WHERE id=%s",(sr["id"],))
                    if x["planned_input_id"]: c.execute("UPDATE public.activity_inputs SET stock_reservation_status='CONSUMED' WHERE id=%s",(x["planned_input_id"],))
                elif x["planned_input_id"]: c.execute("UPDATE public.activity_inputs SET stock_reservation_status='PARTIALLY_CONSUMED' WHERE id=%s",(x["planned_input_id"],))
            out.append({"execution_input_id":x["id"],"product_code":p["product_code"],"transaction_id":tx["id"],"quantity_consumed":q,"unit":p["base_unit"],"duplicate":False})
        c.commit(); return {"execution_id":execution_id,"activity_id":ex["activity_id"],"status":"SYNCED","inputs":out}
      except Exception: c.rollback(); raise

def reverse_execution_stock(execution_id,req):
    with connection() as c:
      try:
        ex=c.execute("SELECT * FROM public.activity_executions WHERE id=%s",(execution_id,)).fetchone()
        if not ex: raise ActivityRegisterNotFound("Execution not found.")
        out=[]
        rows=c.execute("SELECT aei.*,st.product_id,st.location_id,st.batch_id,st.quantity_in,st.quantity_out,st.unit FROM public.activity_execution_inputs aei JOIN public.stock_transactions st ON st.id=aei.stock_transaction_id WHERE aei.execution_id=%s FOR UPDATE",(execution_id,)).fetchall()
        for x in rows:
            rev=c.execute("SELECT * FROM public.stock_transactions WHERE reversal_of=%s",(x["stock_transaction_id"],)).fetchone()
            if not rev:
                key=f"activity-execution-input:{x['id']}:reversal"
                rev=c.execute("INSERT INTO public.stock_transactions(transaction_no,transaction_type,product_id,location_id,batch_id,quantity_in,quantity_out,unit,effective_at,notes,idempotency_key,reversal_of,external_task_id,external_activity_id) VALUES(%s,'REVERSAL',%s,%s,%s,%s,%s,%s,now(),%s,%s,%s,%s,%s) RETURNING *",(_txn_no(),x["product_id"],x["location_id"],x["batch_id"],x["quantity_out"],x["quantity_in"],x["unit"],req.reason_en,key,x["stock_transaction_id"],str(execution_id),str(ex["activity_id"]))).fetchone()
            c.execute("UPDATE public.activity_execution_inputs SET stock_sync_status='REVERSED' WHERE id=%s",(x["id"],))
            out.append({"execution_input_id":x["id"],"original_transaction_id":x["stock_transaction_id"],"reversal_transaction_id":rev["id"]})
        c.commit(); return {"execution_id":execution_id,"status":"REVERSED","reversals":out}
      except Exception: c.rollback(); raise
