from __future__ import annotations
from decimal import Decimal
from ..db import connection
from ..schemas.activity_register import ActivityCreate,PlannedInputCreate,ExecutionCreate,ExecutionInputCreate
from ..schemas.activity_stock_integration import StockSyncRequest
from .activity_register import create_activity,add_execution,get_activity,ActivityRegisterValidation
from .activity_stock_integration import sync_execution

D=lambda v: Decimal(str(v))

def _resolve_cycle(req):
    with connection() as c:
        if req.crop_cycle_id:
            r=c.execute("SELECT * FROM public.crop_cycles WHERE id=%s AND status='ACTIVE'",(req.crop_cycle_id,)).fetchone()
            if not r: raise ActivityRegisterValidation("Active Crop Cycle not found. (सक्रिय पीक चक्र सापडले नाही.)")
            return dict(r)
        rows=c.execute("""SELECT * FROM public.crop_cycles WHERE status='ACTIVE'
                          AND (lower(crop_name_en)=lower(%s) OR crop_name_mr=%s)
                          ORDER BY planting_date DESC""",(req.crop_name,req.crop_name)).fetchall()
        if len(rows)!=1:
            choices=[{"id":str(x["id"]),"cycle_code":x["cycle_code"],"crop_name_en":x["crop_name_en"],"crop_name_mr":x["crop_name_mr"]} for x in rows]
            raise ActivityRegisterValidation(f"Crop name must resolve to exactly one active Crop Cycle. Matches: {choices}")
        return dict(rows[0])

def _water(req):
    if req.water_volume_l is not None:return D(req.water_volume_l)
    if req.pump_count is not None and req.pump_volume_l is not None:return D(req.pump_count)*D(req.pump_volume_l)
    return None

def _multiplier(req,basis):
    if basis=="TOTAL": return Decimal("1")
    if basis=="PER_PUMP":
        if req.pump_count is None: raise ActivityRegisterValidation("pump_count required for PER_PUMP.")
        return D(req.pump_count)
    if basis=="PER_LITRE_WATER":
        w=_water(req)
        if w is None: raise ActivityRegisterValidation("water_volume_l or pump_count + pump_volume_l required for PER_LITRE_WATER.")
        return w
    if basis in ("PER_ACRE","PER_HECTARE"):
        want="ACRE" if basis=="PER_ACRE" else "HECTARE"
        if req.area is None or str(req.area_unit_code or "").upper()!=want:
            raise ActivityRegisterValidation(f"area in {want} required for {basis}; FarmAI will not guess area conversion.")
        return D(req.area)
    if basis=="PER_BED":
        if req.bed_count is None: raise ActivityRegisterValidation("bed_count required for PER_BED.")
        return D(req.bed_count)
    if basis=="PER_PLANT":
        if req.plant_count is None: raise ActivityRegisterValidation("plant_count required for PER_PLANT.")
        return D(req.plant_count)
    raise ActivityRegisterValidation(f"Unsupported dose basis {basis}.")

def preview_farmer_activity(req):
    cycle=_resolve_cycle(req); water=_water(req); items=[]
    with connection() as c:
        for i in req.inputs:
            p=c.execute("SELECT id,product_code,product_name,base_unit FROM public.products WHERE lower(product_code)=lower(%s) AND active=true",(i.product_code,)).fetchone()
            if not p: raise ActivityRegisterValidation(f"Product '{i.product_code}' not found.")
            total=D(i.dose)*_multiplier(req,i.dose_basis_code)
            items.append({"product_code":p["product_code"],"product_name":p["product_name"],"dose":i.dose,"dose_unit_code":i.dose_unit_code.upper(),"dose_basis_code":i.dose_basis_code,"calculated_total_quantity":total,"calculated_total_unit_code":i.dose_unit_code.upper(),"base_unit":p["base_unit"]})
    return {"crop_cycle":{"id":cycle["id"],"cycle_code":cycle["cycle_code"],"crop_name_en":cycle["crop_name_en"],"crop_name_mr":cycle["crop_name_mr"]},
            "execution_date":req.execution_date,"dap":(req.execution_date-cycle["dap_baseline_date"]).days,
            "pump_count":req.pump_count,"water_volume_l":water,"inputs":items,"stock_sync_requested":req.sync_stock}

def complete_farmer_activity(req):
    cycle=_resolve_cycle(req)
    source=f"FARMER-ENTRY:{req.idempotency_key}"
    with connection() as c:
        existing=c.execute("SELECT id FROM public.activities WHERE source_reference=%s",(source,)).fetchone()
    if existing:
        data=get_activity(existing["id"])
        ex=data["executions"][-1] if data["executions"] else None
        if req.sync_stock and ex:
            try: sync_execution(ex["id"],StockSyncRequest(location_code=req.stock_location_code,changed_by=req.created_by))
            except Exception: pass
        return {"duplicate":True,"activity":get_activity(existing["id"]),"preview":preview_farmer_activity(req)}

    pv=preview_farmer_activity(req)
    planned=[]; actual=[]
    for seq,(raw,calc) in enumerate(zip(req.inputs,pv["inputs"]),1):
        planned.append(PlannedInputCreate(product_code=raw.product_code,sequence_no=seq,
            planned_dose=raw.dose,planned_dose_unit_code=raw.dose_unit_code,dose_basis_code=raw.dose_basis_code,
            planned_total_quantity=calc["calculated_total_quantity"],planned_total_unit_code=calc["calculated_total_unit_code"],
            notes_en=raw.notes_en,notes_mr=raw.notes_mr))
        actual.append(ExecutionInputCreate(product_code=raw.product_code,
            actual_dose=raw.dose,actual_dose_unit_code=raw.dose_unit_code,dose_basis_code=raw.dose_basis_code,
            actual_total_quantity=calc["calculated_total_quantity"],actual_total_unit_code=calc["calculated_total_unit_code"],
            notes_en=raw.notes_en,notes_mr=raw.notes_mr))
    a=create_activity(ActivityCreate(crop_cycle_id=cycle["id"],activity_type_code=req.activity_type_code,
        application_method_code=req.application_method_code,status="PLANNED",planned_date=req.execution_date,
        planned_area=req.area,planned_area_unit_code=req.area_unit_code,planned_pump_count=req.pump_count,
        planned_water_volume=pv["water_volume_l"],planned_water_unit_code="L" if pv["water_volume_l"] else None,
        purpose_codes=req.purpose_codes,inputs=planned,source_type="MANUAL",source_reference=source,
        verification_status="CONFIRMED",source_confidence="CONFIRMED",notes_en=req.notes_en,notes_mr=req.notes_mr,created_by=req.created_by))
    aid=a["activity"]["id"]
    data=add_execution(aid,ExecutionCreate(execution_date=req.execution_date,status=req.execution_status,
        area_treated=req.area,area_unit_code=req.area_unit_code,pump_count=req.pump_count,
        water_volume=pv["water_volume_l"],water_unit_code="L" if pv["water_volume_l"] else None,
        performed_by=req.performed_by,notes_en=req.notes_en,notes_mr=req.notes_mr,inputs=actual,created_by=req.created_by))
    ex=data["executions"][-1]
    stock=None
    if req.sync_stock:
        stock=sync_execution(ex["id"],StockSyncRequest(location_code=req.stock_location_code,changed_by=req.created_by))
    return {"duplicate":False,"activity":get_activity(aid),"stock_sync":stock,"preview":pv}
