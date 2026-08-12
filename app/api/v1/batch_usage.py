"""FarmAI V7.2 B2: atomic multi-product usage endpoint."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from ...core.responses import error_response, success_response
from ...core.security import require_api_key
from ...db import connection
from ...quantity import QuantityNormalizationError, canonical_unit, normalize_quantity

router=APIRouter(prefix="/api/v1",tags=["Batch Transactions"],dependencies=[Depends(require_api_key)])

class BatchUsageItem(BaseModel):
    product_code:str=Field(min_length=1,max_length=100)
    quantity:Decimal=Field(gt=0)
    unit:str=Field(min_length=1,max_length=20)
    location_code:str=Field(default="MAIN",min_length=1,max_length=50)
    notes:str|None=Field(default=None,max_length=2000)

class BatchUsageRequest(BaseModel):
    idempotency_key:str=Field(min_length=8,max_length=200)
    items:list[BatchUsageItem]=Field(min_length=1,max_length=100)
    effective_at:datetime|None=None
    crop:str|None=Field(default=None,max_length=100)
    plot:str|None=Field(default=None,max_length=100)
    method:str|None=Field(default=None,max_length=100)
    water_volume:Decimal|None=Field(default=None,ge=0)
    water_unit:str|None=Field(default=None,max_length=20)
    dose:str|None=Field(default=None,max_length=200)
    external_task_id:str|None=Field(default=None,max_length=200)
    external_activity_id:str|None=Field(default=None,max_length=200)
    notes:str|None=Field(default=None,max_length=2000)

    @model_validator(mode="after")
    def unique_items(self):
        seen=set()
        for x in self.items:
            k=(x.product_code.lower().strip(),x.location_code.lower().strip())
            if k in seen: raise ValueError("Duplicate product/location; merge quantity first.")
            seen.add(k)
        return self

def _no(prefix):
    return f"{prefix}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid4().hex[:8].upper()}"

def _err(status,code,message,details=None):
    return JSONResponse(status_code=status,content=jsonable_encoder(error_response(code=code,message=message,details=details)))

def _product(c,code):
    return c.execute("select id,product_code,product_name,base_unit from products where lower(product_code)=lower(%s) and active=true",(code.strip(),)).fetchone()

def _location(c,code):
    return c.execute("select id,location_code from stock_locations where lower(location_code)=lower(%s) and active=true",(code.strip(),)).fetchone()

def _inv(c,p,l):
    return c.execute("select physical_stock,reserved_stock,available_stock,unit from current_inventory where lower(product_code)=lower(%s) and lower(location_code)=lower(%s)",(p,l)).fetchone()

def _existing(c,key):
    return c.execute("""select st.id,st.transaction_no,st.quantity_out,st.unit,st.status,
    p.product_code,p.product_name,sl.location_code from stock_transactions st
    join products p on p.id=st.product_id join stock_locations sl on sl.id=st.location_id
    where st.idempotency_key like %s order by st.created_at,st.id""",(f"{key}:%",)).fetchall()

def _notes(r,item,activity):
    a=[f"Activity: {activity}"]
    for label,val in [("Crop",r.crop),("Plot",r.plot),("Method",r.method),("Dose",r.dose),
                      ("Task",r.external_task_id),("External Activity",r.external_activity_id)]:
        if val: a.append(f"{label}: {val}")
    if r.water_volume is not None: a.append(f"Water: {r.water_volume} {r.water_unit or ''}".strip())
    if r.notes:a.append(r.notes)
    if item.notes:a.append(item.notes)
    return " | ".join(a)

@router.post("/inventory/issues/batch",operation_id="recordBatchStockUsage",
 summary="Record multiple stock usages as one completed activity")
def record_batch_stock_usage(req:BatchUsageRequest):
    with connection() as c:
        try:
            old=_existing(c,req.idempotency_key)
            if old:
                out=[]
                for x in old:
                    inv=_inv(c,x["product_code"],x["location_code"])
                    out.append({"transaction_id":x["id"],"transaction_no":x["transaction_no"],
                    "product_code":x["product_code"],"product_name":x["product_name"],
                    "quantity_out":x["quantity_out"],"unit":x["unit"],
                    "current_physical_stock":inv["physical_stock"] if inv else Decimal("0"),
                    "current_available_stock":inv["available_stock"] if inv else Decimal("0")})
                return success_response({"duplicate":True,"batch_idempotency_key":req.idempotency_key,"item_count":len(out),"items":out},
                                        meta={"source":"postgresql.stock_transactions"})

            prepared=[]; errors=[]
            for i,item in enumerate(req.items):
                p=_product(c,item.product_code); loc=_location(c,item.location_code)
                if not p:
                    errors.append({"index":i,"product_code":item.product_code,"code":"PRODUCT_NOT_FOUND"}); continue
                if not loc:
                    errors.append({"index":i,"product_code":p["product_code"],"code":"LOCATION_NOT_FOUND"}); continue
                try: q=normalize_quantity(item.quantity,item.unit,p["base_unit"])
                except QuantityNormalizationError as e:
                    errors.append({"index":i,"product_code":p["product_code"],"code":"INVALID_UNIT_CONVERSION","message":str(e)}); continue
                ik=f"{req.idempotency_key}:{i+1}"
                if c.execute("select id from stock_transactions where idempotency_key=%s",(ik,)).fetchone():
                    errors.append({"index":i,"product_code":p["product_code"],"code":"IDEMPOTENCY_CONFLICT"}); continue
                prepared.append({"index":i,"item":item,"p":p,"loc":loc,"q":q,"key":ik})
            if errors:
                c.rollback(); return _err(422,"BATCH_VALIDATION_FAILED","No usage recorded; batch validation failed.",{"errors":errors})

            for pid in sorted({x["p"]["id"] for x in prepared}):
                c.execute("select id from products where id=%s for update",(pid,))

            stock_errors=[]
            for x in prepared:
                inv=_inv(c,x["p"]["product_code"],x["loc"]["location_code"])
                x["before"]=inv
                avail=inv["available_stock"] if inv else Decimal("0")
                phys=inv["physical_stock"] if inv else Decimal("0")
                x["old_available"]=avail;x["old_physical"]=phys
                if x["q"]>avail:
                    stock_errors.append({"index":x["index"],"product_code":x["p"]["product_code"],
                    "required_quantity":x["q"],"available_quantity":avail,"unit":x["p"]["base_unit"],"code":"INSUFFICIENT_STOCK"})
            if stock_errors:
                c.rollback(); return _err(409,"BATCH_INSUFFICIENT_STOCK","No usage recorded; at least one item has insufficient stock.",{"errors":stock_errors})

            activity=_no("ACT"); results=[]
            for x in prepared:
                p=x["p"];loc=x["loc"];item=x["item"]
                tx=c.execute("""insert into stock_transactions(transaction_no,transaction_type,product_id,location_id,
                quantity_in,quantity_out,unit,effective_at,notes,idempotency_key,status)
                values(%s,'USAGE',%s,%s,0,%s,%s,coalesce(%s,now()),%s,%s,'CONFIRMED') returning *""",
                (_no("TXN"),p["id"],loc["id"],x["q"],p["base_unit"],req.effective_at,_notes(req,item,activity),x["key"])).fetchone()
                after=_inv(c,p["product_code"],loc["location_code"])
                results.append({"transaction_id":tx["id"],"transaction_no":tx["transaction_no"],
                "product_code":p["product_code"],"product_name":p["product_name"],"location_code":loc["location_code"],
                "submitted_quantity":item.quantity,"submitted_unit":canonical_unit(item.unit),
                "normalized_quantity":x["q"],"normalized_unit":p["base_unit"],
                "previous_physical_stock":x["old_physical"],"previous_available_stock":x["old_available"],
                "new_physical_stock":after["physical_stock"],"new_available_stock":after["available_stock"]})
            c.commit()
            return success_response({"duplicate":False,"activity_no":activity,"batch_idempotency_key":req.idempotency_key,
            "transaction_type":"USAGE","status":"COMPLETED","crop":req.crop,"plot":req.plot,"method":req.method,
            "item_count":len(results),"items":results},meta={"source":"postgresql.stock_transactions"})
        except Exception:
            c.rollback(); raise
