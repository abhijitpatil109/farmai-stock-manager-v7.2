"""
FarmAI Activity Register — Phase 2B.4 Pre-Promotion Hardening.
"""
from __future__ import annotations
import json
from ..db import connection
from . import activity_import as legacy

ImportNotFound=legacy.ImportNotFound
ImportConflict=legacy.ImportConflict
ImportValidation=legacy.ImportValidation

def _decision(conn,record_id):
    return conn.execute("""SELECT * FROM public.activity_import_duplicate_decisions
                           WHERE import_record_id=%s LIMIT 1""",(record_id,)).fetchone()

def _purposes(conn,record_id):
    return conn.execute("""SELECT rp.*,ap.code,ap.name_en,ap.name_mr
                           FROM public.activity_import_record_purposes rp
                           JOIN public.activity_purposes ap ON ap.id=rp.activity_purpose_id
                           WHERE rp.import_record_id=%s
                           ORDER BY ap.sort_order,ap.code""",(record_id,)).fetchall()

def _open_blockers(conn,record_id):
    return conn.execute("""SELECT count(*) n FROM public.activity_import_issues
                           WHERE import_record_id=%s AND status='OPEN' AND severity='BLOCKING'""",
                        (record_id,)).fetchone()["n"]

def _candidate_for_duplicate(conn,record_id):
    r=legacy._record(conn,record_id)
    if not (r["crop_cycle_id"] and r["activity_type_code"] and r["activity_date"]): return None
    return conn.execute("""SELECT DISTINCT a.id
                           FROM public.activities a
                           JOIN public.activity_types at ON at.id=a.activity_type_id
                           JOIN public.activity_executions ae ON ae.activity_id=a.id
                           WHERE a.crop_cycle_id=%s AND at.code=%s AND ae.execution_date=%s
                           ORDER BY a.id LIMIT 1""",
                        (r["crop_cycle_id"],r["activity_type_code"],r["activity_date"])).fetchone()

def _apply_duplicate_decision_after_legacy_reconcile(record_id):
    with connection() as conn:
        try:
            r=legacy._record(conn,record_id)
            decision=_decision(conn,record_id)
            issue=conn.execute("""SELECT * FROM public.activity_import_issues
                                  WHERE import_record_id=%s AND issue_code='POSSIBLE_DUPLICATE'
                                    AND status='OPEN' ORDER BY created_at DESC LIMIT 1""",
                               (record_id,)).fetchone()
            if not issue or not decision:
                conn.commit()
                return legacy.get_record(record_id)
            candidate=_candidate_for_duplicate(conn,record_id)
            if not candidate or candidate["id"]!=decision["candidate_activity_id"]:
                raise ImportValidation("Saved duplicate decision does not match the current duplicate candidate.")
            conn.execute("""UPDATE public.activity_import_issues
                           SET status='ACCEPTED',resolved_at=now(),resolved_by=%s,
                               resolution_en=%s,resolution_mr=%s WHERE id=%s""",
                        (decision["decided_by"],decision["resolution_en"],
                         decision["resolution_mr"],issue["id"]))
            if decision["decision"]=="REJECT_IMPORT":
                conn.execute("""UPDATE public.activity_import_records
                               SET status='REJECTED',reconciliation_status='REJECTED',
                                   reviewed_at=now(),reviewed_by=%s,updated_at=now()
                               WHERE id=%s""",(decision["decided_by"],record_id))
            else:
                refreshed=legacy._record(conn,record_id)
                fp=legacy._fingerprint(conn,refreshed)
                remaining=_open_blockers(conn,record_id)
                conn.execute("""UPDATE public.activity_import_records
                               SET status=%s,reconciliation_status=%s,
                                   duplicate_of_activity_id=%s,import_fingerprint=%s,
                                   reviewed_at=now(),reviewed_by=%s,updated_at=now()
                               WHERE id=%s""",
                            ("READY" if remaining==0 else "REVIEW_REQUIRED",
                             "READY" if remaining==0 else "CONFLICT",
                             decision["candidate_activity_id"],
                             fp if remaining==0 else None,
                             decision["decided_by"],record_id))
            legacy._refresh_batch(conn,r["batch_id"])
            conn.commit()
            return legacy.get_record(record_id)
        except Exception:
            conn.rollback(); raise

def reconcile_record(record_id):
    legacy.reconcile_record(record_id)
    return _apply_duplicate_decision_after_legacy_reconcile(record_id)

def reconcile_batch(batch_id):
    with connection() as conn:
        legacy._batch(conn,batch_id)
        ids=[x["id"] for x in conn.execute("""SELECT id FROM public.activity_import_records
                    WHERE batch_id=%s AND status NOT IN ('IMPORTED','REJECTED')
                    ORDER BY source_sequence,created_at""",(batch_id,)).fetchall()]
    for rid in ids: reconcile_record(rid)
    return legacy.get_batch_preview(batch_id)

def set_purposes(record_id,req):
    with connection() as conn:
        try:
            r=legacy._record(conn,record_id)
            if r["status"] in ("APPROVED","IMPORTED","REJECTED"):
                raise ImportConflict("Reviewed/imported record cannot be edited.")
            rows=[]
            for code in req.purpose_codes:
                p=conn.execute("""SELECT id,code FROM public.activity_purposes
                                  WHERE code=%s AND active=TRUE""",(code,)).fetchone()
                if not p: raise ImportValidation(f"Activity Purpose '{code}' not found or inactive.")
                rows.append(p)
            conn.execute("DELETE FROM public.activity_import_record_purposes WHERE import_record_id=%s",(record_id,))
            for p in rows:
                conn.execute("""INSERT INTO public.activity_import_record_purposes(
                    import_record_id,activity_purpose_id,source_text,match_method,match_confidence,
                    created_by,updated_by) VALUES(%s,%s,%s,'MANUAL_PURPOSE_CODE',100,%s,%s)""",
                    (record_id,p["id"],req.source_text,req.reviewed_by,req.reviewed_by))
            conn.execute("""UPDATE public.activity_import_records
                            SET reviewed_at=now(),reviewed_by=%s,updated_at=now() WHERE id=%s""",
                         (req.reviewed_by,record_id))
            conn.commit()
            return get_hardening_state(record_id)
        except Exception:
            conn.rollback(); raise

def resolve_duplicate(record_id,req):
    with connection() as conn:
        try:
            r=legacy._record(conn,record_id)
            if r["status"] in ("APPROVED","IMPORTED","REJECTED"):
                raise ImportConflict("Reviewed/imported record cannot be edited.")
            candidate=_candidate_for_duplicate(conn,record_id)
            if not candidate: raise ImportValidation("No current authoritative duplicate candidate exists.")
            if candidate["id"]!=req.candidate_activity_id:
                raise ImportValidation("candidate_activity_id does not match current duplicate candidate.")
            conn.execute("""INSERT INTO public.activity_import_duplicate_decisions(
                import_record_id,candidate_activity_id,decision,resolution_en,resolution_mr,decided_by,decided_at
                ) VALUES(%s,%s,%s,%s,%s,%s,now())
                ON CONFLICT(import_record_id) DO UPDATE SET
                  candidate_activity_id=excluded.candidate_activity_id,decision=excluded.decision,
                  resolution_en=excluded.resolution_en,resolution_mr=excluded.resolution_mr,
                  decided_by=excluded.decided_by,decided_at=now()""",
                (record_id,req.candidate_activity_id,req.decision,req.resolution_en,
                 req.resolution_mr,req.reviewed_by))
            conn.commit()
        except Exception:
            conn.rollback(); raise
    return reconcile_record(record_id)

def _validate_approval_gate(conn,record_id):
    r=legacy._record(conn,record_id)
    if r["status"]!="READY" or r["reconciliation_status"]!="READY":
        raise ImportValidation("Record must be READY with READY reconciliation before approval.")
    if _open_blockers(conn,record_id):
        raise ImportValidation("Blocking reconciliation issues remain.")
    if not (r["farm_id"] and r["plot_id"] and r["crop_cycle_id"] and r["activity_date"]):
        raise ImportValidation("Farm, Plot, Crop Cycle and Activity date are required.")
    if not r["activity_type_code"]: raise ImportValidation("Activity Type is required.")
    if not r["import_fingerprint"]: raise ImportValidation("READY record is missing import fingerprint.")
    unmatched=conn.execute("""SELECT count(*) n FROM public.activity_import_record_inputs
                              WHERE import_record_id=%s
                                AND (product_id IS NULL OR match_status<>'MATCHED')""",
                           (record_id,)).fetchone()["n"]
    if unmatched: raise ImportValidation("All historical Product inputs must be MATCHED before approval.")
    if r["duplicate_of_activity_id"]:
        d=_decision(conn,record_id)
        if not d or d["candidate_activity_id"]!=r["duplicate_of_activity_id"]:
            raise ImportValidation("Possible duplicate requires an explicit current duplicate decision.")
        if d["decision"]=="REJECT_IMPORT":
            raise ImportValidation("Duplicate decision is REJECT_IMPORT; record cannot be approved.")
    invalid=conn.execute("""SELECT count(*) n
                            FROM public.activity_import_record_purposes rp
                            LEFT JOIN public.activity_purposes ap
                              ON ap.id=rp.activity_purpose_id AND ap.active=TRUE
                            WHERE rp.import_record_id=%s AND ap.id IS NULL""",
                         (record_id,)).fetchone()["n"]
    if invalid: raise ImportValidation("One or more staged Activity Purposes are invalid/inactive.")
    return r

def approve_record(record_id,req):
    with connection() as conn:
        try:
            r=_validate_approval_gate(conn,record_id)
            conn.execute("""UPDATE public.activity_import_records
                            SET status='APPROVED',reconciliation_status='READY',
                                approved_at=now(),approved_by=%s,
                                reviewed_at=now(),reviewed_by=%s,updated_at=now(),
                                notes_en=COALESCE(%s,notes_en),notes_mr=COALESCE(%s,notes_mr)
                            WHERE id=%s""",
                         (req.reviewed_by,req.reviewed_by,req.notes_en,req.notes_mr,record_id))
            legacy._refresh_batch(conn,r["batch_id"])
            conn.commit()
            return get_hardening_state(record_id)
        except Exception:
            conn.rollback(); raise

def promote_record(record_id,req):
    with connection() as conn:
        try:
            r=conn.execute("SELECT * FROM public.activity_import_records WHERE id=%s FOR UPDATE",
                           (record_id,)).fetchone()
            if not r: raise ImportNotFound("Import Record not found. (आयात नोंद सापडली नाही.)")
            if r["status"]=="IMPORTED" and r["imported_activity_id"]:
                return {"idempotent":True,"activity_id":r["imported_activity_id"],"record":dict(r)}
            if r["status"]!="APPROVED": raise ImportValidation("Only APPROVED records can be promoted.")
            if _open_blockers(conn,record_id): raise ImportValidation("Blocking issues reappeared after approval.")
            if not r["import_fingerprint"]: raise ImportValidation("Approved record is missing import fingerprint.")
            inputs=conn.execute("""SELECT * FROM public.activity_import_record_inputs
                                   WHERE import_record_id=%s ORDER BY source_sequence""",
                                (record_id,)).fetchall()
            for x in inputs:
                if not x["product_id"] or x["match_status"]!="MATCHED":
                    raise ImportValidation("All Products must be MATCHED before promotion.")
            batch=legacy._batch(conn,r["batch_id"])
            decision=_decision(conn,record_id)
            if decision and decision["decision"]=="LINK_EXISTING":
                if decision["candidate_activity_id"]!=r["duplicate_of_activity_id"]:
                    raise ImportValidation("Duplicate LINK_EXISTING decision is stale.")
                target=conn.execute("SELECT id FROM public.activities WHERE id=%s",
                                    (decision["candidate_activity_id"],)).fetchone()
                if not target: raise ImportValidation("LINK_EXISTING target Activity no longer exists.")
                conn.execute("""UPDATE public.activity_import_records
                                SET status='IMPORTED',reconciliation_status='IMPORTED',
                                    imported_activity_id=%s,imported_at=now(),updated_at=now()
                                WHERE id=%s""",(target["id"],record_id))
                legacy._refresh_batch(conn,r["batch_id"]); conn.commit()
                return {"idempotent":True,"linked_existing":True,"activity_id":target["id"],"record_id":record_id}
            cycle=conn.execute("SELECT * FROM public.crop_cycles WHERE id=%s",(r["crop_cycle_id"],)).fetchone()
            at=conn.execute("SELECT id FROM public.activity_types WHERE code=%s AND active=TRUE",
                            (r["activity_type_code"],)).fetchone()
            if not cycle or not at: raise ImportValidation("Crop Cycle or Activity Type became invalid.")
            baseline=cycle["dap_baseline_date"] or cycle["planting_date"]
            dap=(r["activity_date"]-baseline).days
            if dap<0: raise ImportValidation("Activity date is earlier than Crop Cycle DAP baseline.")
            source_ref=f"activity-import:{batch['batch_code']}:{r['source_record_key']}"
            existing=conn.execute("""SELECT id FROM public.activities
                                     WHERE source_type='IMPORT' AND source_reference=%s LIMIT 1""",
                                  (source_ref,)).fetchone()
            if existing:
                conn.execute("""UPDATE public.activity_import_records
                                SET status='IMPORTED',reconciliation_status='IMPORTED',
                                    imported_activity_id=%s,imported_at=now(),updated_at=now()
                                WHERE id=%s""",(existing["id"],record_id))
                legacy._refresh_batch(conn,r["batch_id"]); conn.commit()
                return {"idempotent":True,"activity_id":existing["id"],"record_id":record_id}
            activity=conn.execute("""INSERT INTO public.activities(
                farm_id,crop_cycle_id,activity_type_id,application_method_code,status,
                name_en,name_mr,description_en,description_mr,notes_en,notes_mr,
                source_type,source_reference,verification_status,source_confidence,created_by,updated_by
                ) VALUES(%s,%s,%s,%s,'COMPLETED',%s,%s,%s,%s,%s,%s,'IMPORT',%s,%s,%s,%s,%s)
                RETURNING *""",
                (r["farm_id"],r["crop_cycle_id"],at["id"],r["application_method_code"],
                 r["name_en"],r["name_mr"],r["description_en"],r["description_mr"],r["notes_en"],r["notes_mr"],
                 source_ref,r["verification_status"],r["source_confidence"],req.reviewed_by,req.reviewed_by)).fetchone()
            purpose_rows=_purposes(conn,record_id)
            for p in purpose_rows:
                conn.execute("""INSERT INTO public.activity_purpose_links(activity_id,activity_purpose_id)
                                VALUES(%s,%s) ON CONFLICT DO NOTHING""",
                             (activity["id"],p["activity_purpose_id"]))
            execution=conn.execute("""INSERT INTO public.activity_executions(
                activity_id,execution_no,execution_date,status,dap_at_execution,
                area_treated,area_unit_code,pump_count,water_volume,water_unit_code,
                notes_en,notes_mr,created_by,updated_by
                ) VALUES(%s,1,%s,'COMPLETED',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (activity["id"],r["activity_date"],dap,r["area"],r["area_unit_code"],r["pump_count"],
                 r["water_volume"],r["water_unit_code"],r["notes_en"],r["notes_mr"],req.reviewed_by,req.reviewed_by)).fetchone()
            for x in inputs:
                ei=conn.execute("""INSERT INTO public.activity_execution_inputs(
                    activity_id,execution_id,product_id,actual_dose,actual_dose_unit_code,dose_basis_code,
                    actual_total_quantity,actual_total_unit_code,stock_sync_status,notes_en,notes_mr
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'NOT_REQUESTED',%s,%s) RETURNING *""",
                    (activity["id"],execution["id"],x["product_id"],x["dose"],x["dose_unit_code"],x["dose_basis_code"],
                     x["total_quantity"],x["total_unit_code"],x["notes_en"],x["notes_mr"])).fetchone()
                conn.execute("""INSERT INTO public.activity_audit_log(
                    entity_type,entity_id,action,new_data,reason_en,reason_mr,changed_by,correlation_id
                    ) VALUES('EXECUTION_INPUT',%s,'IMPORT',%s::jsonb,%s,%s,%s,%s)""",
                    (ei["id"],json.dumps(dict(ei),default=str),"Imported from approved historical evidence.",
                     "मंजूर ऐतिहासिक पुराव्यातून आयात केले.",req.reviewed_by,str(record_id)))
            conn.execute("""INSERT INTO public.activity_audit_log(
                entity_type,entity_id,action,new_data,reason_en,reason_mr,changed_by,correlation_id
                ) VALUES('ACTIVITY',%s,'IMPORT',%s::jsonb,%s,%s,%s,%s)""",
                (activity["id"],json.dumps(dict(activity),default=str),
                 "Promoted from approved historical migration staging with 2B.4 promotion hardening.",
                 "२B.४ प्रमोशन हार्डनिंगसह मंजूर ऐतिहासिक स्थलांतर स्टेजिंगमधून अधिकृत नोंद तयार केली.",
                 req.reviewed_by,str(record_id)))
            conn.execute("""UPDATE public.activity_import_records
                            SET status='IMPORTED',reconciliation_status='IMPORTED',
                                imported_activity_id=%s,imported_at=now(),updated_at=now()
                            WHERE id=%s""",(activity["id"],record_id))
            legacy._refresh_batch(conn,r["batch_id"]); conn.commit()
            return {"idempotent":False,"activity_id":activity["id"],"execution_id":execution["id"],
                    "record_id":record_id,"purpose_count":len(purpose_rows)}
        except Exception:
            conn.rollback(); raise

def get_hardening_state(record_id):
    base=legacy.get_record(record_id)
    with connection() as conn:
        purposes=[dict(x) for x in _purposes(conn,record_id)]
        decision=_decision(conn,record_id)
    base["purposes"]=purposes
    base["duplicate_decision"]=dict(decision) if decision else None
    return base
