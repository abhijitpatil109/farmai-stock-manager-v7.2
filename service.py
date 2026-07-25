from datetime import datetime,timezone
from decimal import Decimal
from uuid import uuid4
from fastapi import HTTPException
def _n(v): return Decimal(str(v or 0))
def _txno(): return f"TXN-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid4().hex[:8].upper()}"
def resolve_product(conn,req):
    if req.product_id: row=conn.execute("select * from products where id=%s and active=true",(req.product_id,)).fetchone()
    elif req.product_code: row=conn.execute("select * from products where lower(product_code)=lower(%s) and active=true",(req.product_code,)).fetchone()
    else: row=conn.execute("select * from products where lower(product_name)=lower(%s) and active=true",(req.product_name,)).fetchone()
    if not row: raise HTTPException(404,detail={'code':'PRODUCT_NOT_FOUND','message':'Product not found or inactive.'})
    return row
def get_inventory(conn): return conn.execute("select product_id,product_code,product_name,category,stock,unit,reorder_level,minimum_stock,stock_status status from current_inventory where active=true order by category,product_name").fetchall()
def get_history(conn,product):
    p=conn.execute("select id from products where lower(product_code)=lower(%s) or lower(product_name)=lower(%s)",(product,product)).fetchone()
    if not p: raise HTTPException(404,detail={'code':'PRODUCT_NOT_FOUND','message':'Product not found.'})
    return conn.execute("select st.*,p.product_code,p.product_name from stock_transactions st join products p on p.id=st.product_id where st.product_id=%s order by st.effective_at desc,st.created_at desc",(p['id'],)).fetchall()
def balance(conn,pid):
    conn.execute("select id from products where id=%s for update",(pid,))
    return _n(conn.execute("select coalesce(sum(quantity_in-quantity_out),0) stock from stock_transactions where product_id=%s and status='CONFIRMED'",(pid,)).fetchone()['stock'])
def record_movement(conn,req,typ,incoming):
    dup=conn.execute("select * from stock_transactions where idempotency_key=%s",(req.idempotency_key,)).fetchone()
    if dup:return {'duplicate':True,'transaction':dup}
    p=resolve_product(conn,req)
    if req.unit and req.unit.lower()!=p['base_unit'].lower(): raise HTTPException(422,detail={'code':'UNIT_MISMATCH','message':f"Expected unit {p['base_unit']}."})
    b=balance(conn,p['id']); q=_n(req.quantity)
    if not incoming and q>b: raise HTTPException(409,detail={'code':'INSUFFICIENT_STOCK','message':f"Available stock is {b} {p['base_unit']}."})
    row=conn.execute("insert into stock_transactions(transaction_no,transaction_type,product_id,quantity_in,quantity_out,unit,effective_at,batch_no,expiry_date,reference,notes,recorded_by,idempotency_key) values(%s,%s,%s,%s,%s,%s,coalesce(%s,now()),%s,%s,%s,%s,%s,%s) returning *",(_txno(),typ,p['id'],q if incoming else 0,0 if incoming else q,p['base_unit'],req.effective_at,req.batch_no,req.expiry_date,req.reference,req.notes,req.recorded_by or 'FarmAI GPT',req.idempotency_key)).fetchone()
    return {'duplicate':False,'transaction':row}
def record_verification(conn,req):
    p=resolve_product(conn,req); sys=balance(conn,p['id']); ver=_n(req.verified_quantity); var=ver-sys; adj=None
    if var!=0: adj=conn.execute("insert into stock_transactions(transaction_no,transaction_type,product_id,quantity_in,quantity_out,unit,effective_at,notes,recorded_by,idempotency_key) values(%s,'VERIFICATION_ADJUSTMENT',%s,%s,%s,%s,coalesce(%s,now()),%s,%s,%s) returning *",(_txno(),p['id'],var if var>0 else 0,abs(var) if var<0 else 0,p['base_unit'],req.effective_at,req.notes,req.verified_by or 'FarmAI GPT',req.idempotency_key+':adjustment')).fetchone()
    vno='VER-'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')+'-'+uuid4().hex[:8].upper()
    vr=conn.execute("insert into physical_verifications(verification_no,product_id,system_quantity,verified_quantity,variance,unit,verified_at,verified_by,notes,adjustment_transaction_id,idempotency_key) values(%s,%s,%s,%s,%s,%s,coalesce(%s,now()),%s,%s,%s,%s) returning *",(vno,p['id'],sys,ver,var,p['base_unit'],req.effective_at,req.verified_by or 'FarmAI GPT',req.notes,adj['id'] if adj else None,req.idempotency_key)).fetchone()
    return {'duplicate':False,'verification':vr,'adjustment':adj}
def reverse_transaction(conn,req):
    orig=conn.execute("select * from stock_transactions where id=%s for update",(req.transaction_id,)).fetchone()
    if not orig: raise HTTPException(404,detail={'code':'TRANSACTION_NOT_FOUND','message':'Transaction not found.'})
    if conn.execute("select id from stock_transactions where reversal_of=%s",(orig['id'],)).fetchone(): raise HTTPException(409,detail={'code':'ALREADY_REVERSED','message':'Transaction already reversed.'})
    if balance(conn,orig['product_id'])+_n(orig['quantity_out'])-_n(orig['quantity_in'])<0: raise HTTPException(409,detail={'code':'REVERSAL_CAUSES_NEGATIVE_STOCK','message':'Reversal would create negative stock.'})
    row=conn.execute("insert into stock_transactions(transaction_no,transaction_type,product_id,quantity_in,quantity_out,unit,effective_at,notes,recorded_by,idempotency_key,reversal_of) values(%s,'REVERSAL',%s,%s,%s,%s,coalesce(%s,now()),%s,%s,%s,%s) returning *",(_txno(),orig['product_id'],orig['quantity_out'],orig['quantity_in'],orig['unit'],req.effective_at,req.reason or req.notes or 'Reversal',req.recorded_by or 'FarmAI GPT',req.idempotency_key,orig['id'])).fetchone()
    return {'duplicate':False,'transaction':row}
