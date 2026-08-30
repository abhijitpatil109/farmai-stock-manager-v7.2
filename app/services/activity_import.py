
from __future__ import annotations

import hashlib
import json
from datetime import date
from uuid import UUID

from ..db import connection


class ImportDomainError(Exception): pass
class ImportNotFound(ImportDomainError): pass
class ImportConflict(ImportDomainError): pass
class ImportValidation(ImportDomainError): pass


def _d(row): return dict(row) if row is not None else None
def _ds(rows): return [dict(r) for r in rows]


def _batch(conn, batch_id):
    row = conn.execute("SELECT * FROM public.activity_import_batches WHERE id=%s",(batch_id,)).fetchone()
    if not row: raise ImportNotFound("Import Batch not found. (आयात बॅच सापडली नाही.)")
    return row


def _record(conn, record_id):
    row = conn.execute("SELECT * FROM public.activity_import_records WHERE id=%s",(record_id,)).fetchone()
    if not row: raise ImportNotFound("Import Record not found. (आयात नोंद सापडली नाही.)")
    return row


def _issue(conn, *, batch_id, record_id=None, input_id=None, code, severity,
           field_name=None, message_en, message_mr, detected=None, suggested=None):
    existing = conn.execute(
        """SELECT id FROM public.activity_import_issues
           WHERE batch_id=%s AND import_record_id IS NOT DISTINCT FROM %s
             AND import_input_id IS NOT DISTINCT FROM %s
             AND issue_code=%s AND status='OPEN' LIMIT 1""",
        (batch_id,record_id,input_id,code),
    ).fetchone()
    if existing: return existing["id"]
    return conn.execute(
        """INSERT INTO public.activity_import_issues(
             batch_id,import_record_id,import_input_id,issue_code,severity,field_name,
             message_en,message_mr,detected_value,suggested_value
           ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (batch_id,record_id,input_id,code,severity,field_name,message_en,message_mr,
         None if detected is None else str(detected),
         None if suggested is None else str(suggested)),
    ).fetchone()["id"]


def _close_auto_issues(conn, record_id):
    conn.execute(
        """UPDATE public.activity_import_issues
           SET status='RESOLVED', resolved_at=now(), resolved_by='SYSTEM_RECONCILIATION',
               resolution_en='Automatically resolved by a later successful reconciliation.',
               resolution_mr='नंतरच्या यशस्वी पुनर्मिलनामुळे समस्या स्वयंचलितपणे सोडवली.'
           WHERE import_record_id=%s AND status='OPEN'
             AND issue_code IN (
               'MISSING_FARM','MISSING_PLOT','MISSING_CROP_CYCLE','CONTEXT_MISMATCH',
               'MISSING_ACTIVITY_DATE','INVALID_DAP_DATE','INVALID_ACTIVITY_TYPE',
               'INVALID_APPLICATION_METHOD','MISSING_PRODUCT','AMBIGUOUS_PRODUCT',
               'INVALID_DOSE_UNIT','INVALID_TOTAL_UNIT','INVALID_DOSE_BASIS',
               'POSSIBLE_DUPLICATE','SOURCE_CONFLICT'
             )""",
        (record_id,),
    )


def _raw_payload_as_dict(raw_payload):
    """Return raw_payload as a dict without inventing or normalizing evidence."""
    if raw_payload is None:
        return {}
    if isinstance(raw_payload, dict):
        return raw_payload
    if isinstance(raw_payload, str):
        try:
            value=json.loads(raw_payload)
            return value if isinstance(value,dict) else {}
        except Exception:
            return {}
    try:
        return dict(raw_payload)
    except Exception:
        return {}


def _source_conflict_evidence(raw_payload):
    """
    Detect explicit source-evidence conflicts already retained by staging.

    Deliberately conservative:
    - any non-empty key beginning with `conflicting_`
    - explicit `source_conflict` / `source_conflicts`
    - explicit `conflict` / `conflicts`

    This does NOT infer a conflict from vague notes or differing confidence.
    """
    payload=_raw_payload_as_dict(raw_payload)
    hits=[]

    def walk(value,path=""):
        if isinstance(value,dict):
            for key,val in value.items():
                p=f"{path}.{key}" if path else str(key)
                key_l=str(key).lower()
                explicit = (
                    key_l.startswith("conflicting_")
                    or key_l in ("source_conflict","source_conflicts","conflict","conflicts")
                )
                if explicit and val not in (None,"",[],{}):
                    hits.append({"path":p,"value":val})
                walk(val,p)
        elif isinstance(value,list):
            for i,val in enumerate(value):
                walk(val,f"{path}[{i}]")
    walk(payload)
    return hits


def _has_accepted_source_conflict(conn, record_id):
    """A manually accepted SOURCE_CONFLICT remains accepted across reconciliation runs."""
    row=conn.execute(
        """SELECT id FROM public.activity_import_issues
           WHERE import_record_id=%s
             AND issue_code='SOURCE_CONFLICT'
             AND status='ACCEPTED'
           ORDER BY resolved_at DESC NULLS LAST, created_at DESC
           LIMIT 1""",
        (record_id,),
    ).fetchone()
    return bool(row)


def resolve_source_conflict(record_id, req):
    """
    Explicit human resolution gate for SOURCE_CONFLICT only.

    It does not edit raw evidence. It records why the normalized value is accepted.
    Reconciliation will continue to retain the raw conflicting evidence while
    respecting this explicit accepted resolution.
    """
    with connection() as conn:
        try:
            r=_record(conn,record_id)
            if r["status"] in ("APPROVED","IMPORTED","REJECTED"):
                raise ImportConflict("Reviewed/imported record cannot be edited.")
            issue=conn.execute(
                """SELECT * FROM public.activity_import_issues
                   WHERE id=%s AND import_record_id=%s
                     AND issue_code='SOURCE_CONFLICT' AND status='OPEN'""",
                (req.issue_id,record_id),
            ).fetchone()
            if not issue:
                raise ImportNotFound("Open SOURCE_CONFLICT issue not found for this record.")

            conn.execute(
                """UPDATE public.activity_import_issues
                   SET status='ACCEPTED',
                       resolution_en=%s,resolution_mr=%s,
                       resolved_at=now(),resolved_by=%s
                   WHERE id=%s""",
                (req.resolution_en,req.resolution_mr,req.reviewed_by,req.issue_id),
            )
            conn.execute(
                """UPDATE public.activity_import_records
                   SET status='STAGED',reconciliation_status='PENDING',
                       reviewed_at=now(),reviewed_by=%s,updated_at=now()
                   WHERE id=%s""",
                (req.reviewed_by,record_id),
            )
            conn.commit()
            return reconcile_record(record_id)
        except Exception:
            conn.rollback(); raise


def create_batch(req):
    with connection() as conn:
        try:
            if not conn.execute("SELECT 1 FROM public.farms WHERE id=%s AND active=TRUE",(req.farm_id,)).fetchone():
                raise ImportValidation("Farm not found or inactive. (शेत सापडले नाही किंवा निष्क्रिय आहे.)")
            row = conn.execute(
                """INSERT INTO public.activity_import_batches(
                     batch_code,farm_id,source_type,source_name,source_reference,
                     notes_en,notes_mr,created_by,updated_by
                   ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (req.batch_code,req.farm_id,req.source_type,req.source_name,req.source_reference,
                 req.notes_en,req.notes_mr,req.created_by,req.created_by),
            ).fetchone()
            conn.commit(); return _d(row)
        except Exception:
            conn.rollback(); raise


def list_batches(farm_id=None, status=None):
    sql="SELECT * FROM public.activity_import_batches WHERE 1=1"; p=[]
    if farm_id: sql+=" AND farm_id=%s"; p.append(farm_id)
    if status: sql+=" AND status=%s"; p.append(status)
    sql+=" ORDER BY created_at DESC"
    with connection() as conn: return _ds(conn.execute(sql,tuple(p)).fetchall())


def stage_record(batch_id, req):
    with connection() as conn:
        try:
            batch=_batch(conn,batch_id)
            farm_id=req.farm_id or batch["farm_id"]
            if farm_id != batch["farm_id"]:
                raise ImportValidation("Record Farm must match Batch Farm. (नोंदीचे शेत बॅचच्या शेताशी जुळले पाहिजे.)")
            row=conn.execute(
                """INSERT INTO public.activity_import_records(
                    batch_id,source_record_key,source_sequence,raw_payload,
                    farm_id,plot_id,crop_cycle_id,activity_date,activity_type_code,
                    application_method_code,name_en,name_mr,description_en,description_mr,
                    notes_en,notes_mr,pump_count,water_volume,water_unit_code,area,area_unit_code,
                    source_confidence,verification_status
                ) VALUES(
                    %s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                ) RETURNING *""",
                (batch_id,req.source_record_key,req.source_sequence,json.dumps(req.raw_payload,default=str),
                 farm_id,req.plot_id,req.crop_cycle_id,req.activity_date,req.activity_type_code,
                 req.application_method_code,req.name_en,req.name_mr,req.description_en,req.description_mr,
                 req.notes_en,req.notes_mr,req.pump_count,req.water_volume,req.water_unit_code,
                 req.area,req.area_unit_code,req.source_confidence,req.verification_status)
            ).fetchone()
            for i,item in enumerate(req.inputs,1):
                conn.execute(
                    """INSERT INTO public.activity_import_record_inputs(
                        import_record_id,source_sequence,raw_product_name,raw_product_code,
                        dose,dose_unit_code,dose_basis_code,total_quantity,total_unit_code,
                        notes_en,notes_mr
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (row["id"],item.source_sequence or i,item.raw_product_name,item.raw_product_code,
                     item.dose,item.dose_unit_code,item.dose_basis_code,item.total_quantity,
                     item.total_unit_code,item.notes_en,item.notes_mr)
                )
            conn.execute(
                """UPDATE public.activity_import_batches
                   SET total_records=(SELECT count(*) FROM public.activity_import_records WHERE batch_id=%s),
                       updated_at=now()
                   WHERE id=%s""",(batch_id,batch_id)
            )
            conn.commit()
            return get_record(row["id"])
        except Exception:
            conn.rollback(); raise


def get_record(record_id):
    with connection() as conn:
        r=_record(conn,record_id)
        inputs=_ds(conn.execute(
            """SELECT iri.*,p.product_code,p.product_name,p.brand,p.base_unit
               FROM public.activity_import_record_inputs iri
               LEFT JOIN public.products p ON p.id=iri.product_id
               WHERE iri.import_record_id=%s ORDER BY iri.source_sequence,iri.created_at""",(record_id,)
        ).fetchall())
        issues=_ds(conn.execute(
            """SELECT * FROM public.activity_import_issues
               WHERE import_record_id=%s ORDER BY
               CASE severity WHEN 'BLOCKING' THEN 1 WHEN 'ERROR' THEN 2 WHEN 'WARNING' THEN 3 ELSE 4 END,
               created_at""",(record_id,)
        ).fetchall())
        return {"record":_d(r),"inputs":inputs,"issues":issues}


def set_context(record_id, req):
    with connection() as conn:
        try:
            r=_record(conn,record_id)
            if r["status"] in ("APPROVED","IMPORTED","REJECTED"):
                raise ImportConflict("Reviewed/imported record cannot be edited.")
            conn.execute(
                """UPDATE public.activity_import_records SET
                   farm_id=%s,plot_id=%s,crop_cycle_id=%s,activity_date=%s,
                   activity_type_code=%s,application_method_code=%s,
                   reconciliation_status='PENDING',status='STAGED',reviewed_at=now(),reviewed_by=%s,updated_at=now()
                   WHERE id=%s""",
                (req.farm_id,req.plot_id,req.crop_cycle_id,req.activity_date,
                 req.activity_type_code.upper(),req.application_method_code.upper() if req.application_method_code else None,
                 req.reviewed_by,record_id)
            )
            conn.commit()
            return reconcile_record(record_id)
        except Exception:
            conn.rollback(); raise


def resolve_product(record_id, req):
    with connection() as conn:
        try:
            r=_record(conn,record_id)
            if r["status"] in ("APPROVED","IMPORTED","REJECTED"):
                raise ImportConflict("Reviewed/imported record cannot be edited.")
            inp=conn.execute(
                "SELECT * FROM public.activity_import_record_inputs WHERE id=%s AND import_record_id=%s",
                (req.import_input_id,record_id)
            ).fetchone()
            if not inp: raise ImportNotFound("Import input not found.")
            p=conn.execute(
                """SELECT id FROM public.products WHERE lower(product_code)=lower(%s) AND active=TRUE""",
                (req.product_code.strip(),)
            ).fetchone()
            if not p: raise ImportValidation("Product code not found in Product Master.")
            conn.execute(
                """UPDATE public.activity_import_record_inputs
                   SET product_id=%s,match_status='MATCHED',match_method='MANUAL_PRODUCT_CODE',
                       match_confidence=100,updated_at=now()
                   WHERE id=%s""",(p["id"],req.import_input_id)
            )
            conn.execute(
                """UPDATE public.activity_import_records
                   SET status='STAGED',reconciliation_status='PENDING',reviewed_at=now(),reviewed_by=%s,updated_at=now()
                   WHERE id=%s""",(req.reviewed_by,record_id)
            )
            conn.commit()
            return reconcile_record(record_id)
        except Exception:
            conn.rollback(); raise


def _ref_exists(conn, table, code):
    return bool(conn.execute(f"SELECT 1 FROM public.{table} WHERE code=%s AND active=TRUE",(code,)).fetchone())


def _fingerprint(conn, r):
    products=conn.execute(
        """SELECT product_id,dose,dose_unit_code,dose_basis_code,total_quantity,total_unit_code
           FROM public.activity_import_record_inputs WHERE import_record_id=%s
           ORDER BY product_id NULLS LAST,source_sequence""",(r["id"],)
    ).fetchall()
    payload={
        "farm_id":str(r["farm_id"]) if r["farm_id"] else None,
        "crop_cycle_id":str(r["crop_cycle_id"]) if r["crop_cycle_id"] else None,
        "date":str(r["activity_date"]) if r["activity_date"] else None,
        "type":r["activity_type_code"],
        "method":r["application_method_code"],
        "inputs":[
            [str(x["product_id"]) if x["product_id"] else None,
             str(x["dose"]) if x["dose"] is not None else None,x["dose_unit_code"],x["dose_basis_code"],
             str(x["total_quantity"]) if x["total_quantity"] is not None else None,x["total_unit_code"]]
            for x in products
        ]
    }
    raw=json.dumps(payload,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def reconcile_record(record_id):
    with connection() as conn:
        try:
            r=_record(conn,record_id)
            if r["status"]=="IMPORTED": return get_record(record_id)
            _close_auto_issues(conn,record_id)
            blocking=False

            # Explicit source-evidence conflict guard.
            # Raw staging evidence is never silently overridden by a populated normalized field.
            source_conflicts=_source_conflict_evidence(r["raw_payload"])
            if source_conflicts and not _has_accepted_source_conflict(conn,record_id):
                _issue(
                    conn,batch_id=r["batch_id"],record_id=record_id,
                    code="SOURCE_CONFLICT",severity="BLOCKING",field_name="raw_payload",
                    message_en="Conflicting historical source evidence requires explicit review before approval.",
                    message_mr="विरोधी ऐतिहासिक स्रोत पुराव्यास मंजुरीपूर्वी स्पष्ट मानवी पडताळणी आवश्यक आहे.",
                    detected=json.dumps(source_conflicts,ensure_ascii=False,default=str),
                )
                blocking=True

            # Context
            if not r["farm_id"] or not conn.execute("SELECT 1 FROM public.farms WHERE id=%s AND active=TRUE",(r["farm_id"],)).fetchone():
                _issue(conn,batch_id=r["batch_id"],record_id=record_id,code="MISSING_FARM",severity="BLOCKING",
                       field_name="farm_id",message_en="Valid Farm is required.",message_mr="वैध शेत आवश्यक आहे.")
                blocking=True
            if not r["plot_id"] or not conn.execute("SELECT 1 FROM public.plots WHERE id=%s AND farm_id=%s AND active=TRUE",(r["plot_id"],r["farm_id"])).fetchone():
                _issue(conn,batch_id=r["batch_id"],record_id=record_id,code="MISSING_PLOT",severity="BLOCKING",
                       field_name="plot_id",message_en="Valid Plot in the Farm is required.",message_mr="शेतातील वैध प्लॉट आवश्यक आहे.")
                blocking=True
            cycle=None
            if r["crop_cycle_id"]:
                cycle=conn.execute(
                    """SELECT * FROM public.crop_cycles WHERE id=%s AND farm_id=%s AND plot_id=%s""",
                    (r["crop_cycle_id"],r["farm_id"],r["plot_id"])
                ).fetchone()
            if not cycle:
                _issue(conn,batch_id=r["batch_id"],record_id=record_id,code="MISSING_CROP_CYCLE",severity="BLOCKING",
                       field_name="crop_cycle_id",message_en="Exact Crop Cycle is required.",message_mr="अचूक पीक चक्र आवश्यक आहे.")
                blocking=True

            if not r["activity_date"]:
                _issue(conn,batch_id=r["batch_id"],record_id=record_id,code="MISSING_ACTIVITY_DATE",severity="BLOCKING",
                       field_name="activity_date",message_en="Historical Activity date is required for promotion.",
                       message_mr="ऐतिहासिक क्रियाकलाप आयात करण्यासाठी दिनांक आवश्यक आहे.")
                blocking=True
            elif cycle:
                baseline=cycle["dap_baseline_date"] or cycle["planting_date"]
                if r["activity_date"] < baseline:
                    _issue(conn,batch_id=r["batch_id"],record_id=record_id,code="INVALID_DAP_DATE",severity="BLOCKING",
                           field_name="activity_date",message_en="Activity date is earlier than the Crop Cycle DAP baseline.",
                           message_mr="क्रियाकलाप दिनांक पीक चक्राच्या DAP आधार दिनांकापूर्वी आहे.",
                           detected=r["activity_date"],suggested=baseline)
                    blocking=True

            if not r["activity_type_code"] or not _ref_exists(conn,"activity_types",r["activity_type_code"]):
                _issue(conn,batch_id=r["batch_id"],record_id=record_id,code="INVALID_ACTIVITY_TYPE",severity="BLOCKING",
                       field_name="activity_type_code",message_en="Valid Activity Type is required.",
                       message_mr="वैध क्रियाकलाप प्रकार आवश्यक आहे.",detected=r["activity_type_code"])
                blocking=True
            if r["application_method_code"] and not _ref_exists(conn,"application_methods",r["application_method_code"]):
                _issue(conn,batch_id=r["batch_id"],record_id=record_id,code="INVALID_APPLICATION_METHOD",severity="BLOCKING",
                       field_name="application_method_code",message_en="Application Method is not recognized.",
                       message_mr="वापर पद्धत वैध नाही.",detected=r["application_method_code"])
                blocking=True

            # Units on header
            for field,table in [("water_unit_code","measurement_units"),("area_unit_code","measurement_units")]:
                if r[field] and not _ref_exists(conn,table,r[field]):
                    _issue(conn,batch_id=r["batch_id"],record_id=record_id,code="INVALID_"+field.upper(),severity="BLOCKING",
                           field_name=field,message_en=f"{field} is not recognized.",message_mr=f"{field} वैध नाही.",detected=r[field])
                    blocking=True

            # Product matching: exact code, then exact name only.
            inputs=conn.execute(
                "SELECT * FROM public.activity_import_record_inputs WHERE import_record_id=%s ORDER BY source_sequence",(record_id,)
            ).fetchall()
            for inp in inputs:
                product=None
                if inp["product_id"]:
                    product=conn.execute("SELECT id FROM public.products WHERE id=%s AND active=TRUE",(inp["product_id"],)).fetchone()
                if not product and inp["raw_product_code"]:
                    product=conn.execute(
                        "SELECT id FROM public.products WHERE lower(product_code)=lower(%s) AND active=TRUE",
                        (inp["raw_product_code"],)
                    ).fetchone()
                    if product:
                        conn.execute("""UPDATE public.activity_import_record_inputs
                                      SET product_id=%s,match_status='MATCHED',match_method='EXACT_PRODUCT_CODE',
                                          match_confidence=100,updated_at=now() WHERE id=%s""",(product["id"],inp["id"]))
                if not product and inp["raw_product_name"]:
                    matches=conn.execute(
                        "SELECT id FROM public.products WHERE lower(product_name)=lower(%s) AND active=TRUE",
                        (inp["raw_product_name"],)
                    ).fetchall()
                    if len(matches)==1:
                        product=matches[0]
                        conn.execute("""UPDATE public.activity_import_record_inputs
                                      SET product_id=%s,match_status='MATCHED',match_method='EXACT_PRODUCT_NAME',
                                          match_confidence=95,updated_at=now() WHERE id=%s""",(product["id"],inp["id"]))
                    elif len(matches)>1:
                        conn.execute("UPDATE public.activity_import_record_inputs SET match_status='AMBIGUOUS',updated_at=now() WHERE id=%s",(inp["id"],))
                        _issue(conn,batch_id=r["batch_id"],record_id=record_id,input_id=inp["id"],code="AMBIGUOUS_PRODUCT",
                               severity="BLOCKING",field_name="product",message_en="Product name matches more than one Product Master record.",
                               message_mr="उत्पादन नाव एकापेक्षा जास्त उत्पादन मास्टर नोंदींशी जुळते.",detected=inp["raw_product_name"])
                        blocking=True
                if not product:
                    conn.execute("UPDATE public.activity_import_record_inputs SET match_status='MISSING_PRODUCT',updated_at=now() WHERE id=%s",(inp["id"],))
                    _issue(conn,batch_id=r["batch_id"],record_id=record_id,input_id=inp["id"],code="MISSING_PRODUCT",
                           severity="BLOCKING",field_name="product",message_en="Product could not be matched exactly to Product Master.",
                           message_mr="उत्पादन अचूकपणे उत्पादन मास्टरशी जुळले नाही.",
                           detected=inp["raw_product_code"] or inp["raw_product_name"])
                    blocking=True

                for field,table,code in [
                    ("dose_unit_code","measurement_units","INVALID_DOSE_UNIT"),
                    ("total_unit_code","measurement_units","INVALID_TOTAL_UNIT"),
                    ("dose_basis_code","dose_basis_types","INVALID_DOSE_BASIS"),
                ]:
                    if inp[field] and not _ref_exists(conn,table,inp[field]):
                        _issue(conn,batch_id=r["batch_id"],record_id=record_id,input_id=inp["id"],code=code,
                               severity="BLOCKING",field_name=field,message_en=f"{field} is not recognized.",
                               message_mr=f"{field} वैध नाही.",detected=inp[field])
                        blocking=True

            # Duplicate screening after exact context is available.
            if not blocking:
                candidates=conn.execute(
                    """SELECT DISTINCT a.id
                       FROM public.activities a
                       JOIN public.activity_types at ON at.id=a.activity_type_id
                       JOIN public.activity_executions ae ON ae.activity_id=a.id
                       WHERE a.crop_cycle_id=%s AND at.code=%s AND ae.execution_date=%s""",
                    (r["crop_cycle_id"],r["activity_type_code"],r["activity_date"])
                ).fetchall()
                if candidates:
                    _issue(conn,batch_id=r["batch_id"],record_id=record_id,code="POSSIBLE_DUPLICATE",
                           severity="BLOCKING",field_name="activity_date",
                           message_en="An authoritative Activity with the same Crop Cycle, type and execution date already exists. Review before importing.",
                           message_mr="याच पीक चक्र, प्रकार आणि अंमलबजावणी दिनांकाची अधिकृत क्रियाकलाप नोंद आधीच अस्तित्वात आहे. आयात करण्यापूर्वी पडताळणी करा.",
                           detected=r["activity_date"])
                    conn.execute(
                        "UPDATE public.activity_import_records SET duplicate_of_activity_id=%s WHERE id=%s",
                        (candidates[0]["id"],record_id)
                    )
                    blocking=True

            fp=None
            if not blocking:
                refreshed=_record(conn,record_id)
                fp=_fingerprint(conn,refreshed)
                collision=conn.execute(
                    """SELECT id FROM public.activity_import_records
                       WHERE import_fingerprint=%s AND id<>%s AND status IN ('APPROVED','IMPORTED') LIMIT 1""",
                    (fp,record_id)
                ).fetchone()
                if collision:
                    _issue(conn,batch_id=r["batch_id"],record_id=record_id,code="FINGERPRINT_DUPLICATE",
                           severity="BLOCKING",field_name="import_fingerprint",
                           message_en="The same normalized historical record has already been approved/imported.",
                           message_mr="हीच सामान्यीकृत ऐतिहासिक नोंद आधीच मंजूर/आयात केली आहे.")
                    blocking=True

            open_blocking=conn.execute(
                """SELECT count(*) n FROM public.activity_import_issues
                   WHERE import_record_id=%s AND status='OPEN' AND severity='BLOCKING'""",(record_id,)
            ).fetchone()["n"]
            ready = (open_blocking==0 and not blocking)
            conn.execute(
                """UPDATE public.activity_import_records
                   SET status=%s,reconciliation_status=%s,import_fingerprint=%s,
                       reviewed_at=now(),updated_at=now()
                   WHERE id=%s""",
                ("READY" if ready else "REVIEW_REQUIRED","READY" if ready else "CONFLICT",fp if ready else None,record_id)
            )
            _refresh_batch(conn,r["batch_id"])
            conn.commit()
            return get_record(record_id)
        except Exception:
            conn.rollback(); raise


def reconcile_batch(batch_id):
    with connection() as conn:
        _batch(conn,batch_id)
        ids=[x["id"] for x in conn.execute(
            "SELECT id FROM public.activity_import_records WHERE batch_id=%s AND status NOT IN ('IMPORTED','REJECTED') ORDER BY source_sequence,created_at",
            (batch_id,)
        ).fetchall()]
    results=[]
    for rid in ids: results.append(reconcile_record(rid))
    return get_batch_preview(batch_id)


def _refresh_batch(conn,batch_id):
    counts=conn.execute(
        """SELECT
          count(*) total,
          count(*) FILTER(WHERE status IN ('READY','APPROVED')) ready,
          count(*) FILTER(WHERE status='REVIEW_REQUIRED') review,
          count(*) FILTER(WHERE status='REJECTED') rejected,
          count(*) FILTER(WHERE status='IMPORTED') imported
        FROM public.activity_import_records WHERE batch_id=%s""",(batch_id,)
    ).fetchone()
    if counts["total"]==0: status="STAGED"
    elif counts["imported"]==counts["total"]: status="IMPORTED"
    elif counts["imported"]>0: status="PARTIALLY_IMPORTED"
    elif counts["review"]>0: status="REVIEW_REQUIRED"
    elif counts["ready"]==counts["total"]: status="READY"
    else: status="STAGED"
    conn.execute(
        """UPDATE public.activity_import_batches
           SET total_records=%s,ready_records=%s,review_records=%s,rejected_records=%s,
               imported_records=%s,status=%s,updated_at=now() WHERE id=%s""",
        (counts["total"],counts["ready"],counts["review"],counts["rejected"],counts["imported"],status,batch_id)
    )


def get_batch_preview(batch_id):
    with connection() as conn:
        b=_batch(conn,batch_id)
        records=_ds(conn.execute(
            """SELECT r.*,
               (SELECT count(*) FROM public.activity_import_record_inputs i WHERE i.import_record_id=r.id) input_count,
               (SELECT count(*) FROM public.activity_import_issues x WHERE x.import_record_id=r.id AND x.status='OPEN') open_issue_count,
               (SELECT count(*) FROM public.activity_import_issues x WHERE x.import_record_id=r.id AND x.status='OPEN' AND x.severity='BLOCKING') blocking_issue_count
               FROM public.activity_import_records r WHERE r.batch_id=%s
               ORDER BY r.source_sequence,r.created_at""",(batch_id,)
        ).fetchall())
        issues=_ds(conn.execute(
            """SELECT issue_code,severity,status,count(*) record_count
               FROM public.activity_import_issues WHERE batch_id=%s
               GROUP BY issue_code,severity,status ORDER BY severity,issue_code""",(batch_id,)
        ).fetchall())
        return {"batch":_d(b),"records":records,"issue_summary":issues}


def approve_record(record_id, req):
    with connection() as conn:
        try:
            r=_record(conn,record_id)
            if r["status"]!="READY":
                raise ImportValidation("Only READY records can be approved. Reconcile first.")
            n=conn.execute(
                "SELECT count(*) n FROM public.activity_import_issues WHERE import_record_id=%s AND status='OPEN' AND severity='BLOCKING'",
                (record_id,)
            ).fetchone()["n"]
            if n: raise ImportValidation("Blocking reconciliation issues remain.")
            conn.execute(
                """UPDATE public.activity_import_records SET status='APPROVED',reconciliation_status='READY',
                   verification_status=CASE WHEN verification_status='UNVERIFIED' THEN 'VERIFIED' ELSE verification_status END,
                   approved_at=now(),approved_by=%s,reviewed_at=now(),reviewed_by=%s,updated_at=now()
                   WHERE id=%s""",(req.reviewed_by,req.reviewed_by,record_id)
            )
            _refresh_batch(conn,r["batch_id"])
            conn.commit(); return get_record(record_id)
        except Exception:
            conn.rollback(); raise


def reject_record(record_id, req):
    with connection() as conn:
        try:
            r=_record(conn,record_id)
            if r["status"]=="IMPORTED": raise ImportConflict("Imported record cannot be rejected.")
            conn.execute(
                """UPDATE public.activity_import_records SET status='REJECTED',reconciliation_status='REJECTED',
                   reviewed_at=now(),reviewed_by=%s,notes_en=COALESCE(%s,notes_en),notes_mr=COALESCE(%s,notes_mr),updated_at=now()
                   WHERE id=%s""",(req.reviewed_by,req.notes_en,req.notes_mr,record_id)
            )
            _refresh_batch(conn,r["batch_id"])
            conn.commit(); return get_record(record_id)
        except Exception:
            conn.rollback(); raise


def promote_record(record_id, req):
    with connection() as conn:
        try:
            r=_record(conn,record_id)
            if r["status"]=="IMPORTED" and r["imported_activity_id"]:
                return {"idempotent":True,"activity_id":r["imported_activity_id"],"record":_d(r)}
            if r["status"]!="APPROVED":
                raise ImportValidation("Only APPROVED records can be promoted.")
            if not r["import_fingerprint"]:
                raise ImportValidation("Approved record is missing import fingerprint.")

            batch=_batch(conn,r["batch_id"])
            cycle=conn.execute("SELECT * FROM public.crop_cycles WHERE id=%s",(r["crop_cycle_id"],)).fetchone()
            at=conn.execute("SELECT id FROM public.activity_types WHERE code=%s AND active=TRUE",(r["activity_type_code"],)).fetchone()
            baseline=cycle["dap_baseline_date"] or cycle["planting_date"]
            dap=(r["activity_date"]-baseline).days
            source_ref=f"activity-import:{batch['batch_code']}:{r['source_record_key']}"

            existing=conn.execute(
                "SELECT id FROM public.activities WHERE source_type='IMPORT' AND source_reference=%s LIMIT 1",(source_ref,)
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE public.activity_import_records SET status='IMPORTED',reconciliation_status='IMPORTED',
                       imported_activity_id=%s,imported_at=now(),updated_at=now() WHERE id=%s""",
                    (existing["id"],record_id)
                )
                _refresh_batch(conn,r["batch_id"]); conn.commit()
                return {"idempotent":True,"activity_id":existing["id"],"record_id":record_id}

            activity=conn.execute(
                """INSERT INTO public.activities(
                   farm_id,crop_cycle_id,activity_type_id,application_method_code,status,
                   name_en,name_mr,description_en,description_mr,notes_en,notes_mr,
                   source_type,source_reference,verification_status,source_confidence,
                   created_by,updated_by
                ) VALUES(%s,%s,%s,%s,'COMPLETED',%s,%s,%s,%s,%s,%s,'IMPORT',%s,%s,%s,%s,%s)
                RETURNING *""",
                (r["farm_id"],r["crop_cycle_id"],at["id"],r["application_method_code"],
                 r["name_en"],r["name_mr"],r["description_en"],r["description_mr"],r["notes_en"],r["notes_mr"],
                 source_ref,r["verification_status"],r["source_confidence"],req.reviewed_by,req.reviewed_by)
            ).fetchone()

            execution=conn.execute(
                """INSERT INTO public.activity_executions(
                   activity_id,execution_no,execution_date,status,dap_at_execution,
                   area_treated,area_unit_code,pump_count,water_volume,water_unit_code,
                   notes_en,notes_mr,created_by,updated_by
                ) VALUES(%s,1,%s,'COMPLETED',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (activity["id"],r["activity_date"],dap,r["area"],r["area_unit_code"],r["pump_count"],
                 r["water_volume"],r["water_unit_code"],r["notes_en"],r["notes_mr"],req.reviewed_by,req.reviewed_by)
            ).fetchone()

            inputs=conn.execute(
                """SELECT * FROM public.activity_import_record_inputs WHERE import_record_id=%s ORDER BY source_sequence""",
                (record_id,)
            ).fetchall()
            for x in inputs:
                if not x["product_id"] or x["match_status"]!="MATCHED":
                    raise ImportValidation("All Products must be MATCHED before promotion.")
                ei=conn.execute(
                    """INSERT INTO public.activity_execution_inputs(
                      activity_id,execution_id,product_id,actual_dose,actual_dose_unit_code,dose_basis_code,
                      actual_total_quantity,actual_total_unit_code,stock_sync_status,notes_en,notes_mr
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'NOT_REQUESTED',%s,%s) RETURNING *""",
                    (activity["id"],execution["id"],x["product_id"],x["dose"],x["dose_unit_code"],x["dose_basis_code"],
                     x["total_quantity"],x["total_unit_code"],x["notes_en"],x["notes_mr"])
                ).fetchone()
                conn.execute(
                    """INSERT INTO public.activity_audit_log(
                      entity_type,entity_id,action,new_data,reason_en,reason_mr,changed_by,correlation_id
                    ) VALUES('EXECUTION_INPUT',%s,'IMPORT',%s::jsonb,%s,%s,%s,%s)""",
                    (ei["id"],json.dumps(dict(ei),default=str),
                     "Imported from approved historical evidence.","मंजूर ऐतिहासिक पुराव्यातून आयात केले.",
                     req.reviewed_by,str(record_id))
                )

            conn.execute(
                """INSERT INTO public.activity_audit_log(
                  entity_type,entity_id,action,new_data,reason_en,reason_mr,changed_by,correlation_id
                ) VALUES('ACTIVITY',%s,'IMPORT',%s::jsonb,%s,%s,%s,%s)""",
                (activity["id"],json.dumps(dict(activity),default=str),
                 "Promoted from approved historical migration staging.",
                 "मंजूर ऐतिहासिक स्थलांतर स्टेजिंगमधून अधिकृत नोंद तयार केली.",
                 req.reviewed_by,str(record_id))
            )
            conn.execute(
                """UPDATE public.activity_import_records SET status='IMPORTED',reconciliation_status='IMPORTED',
                   imported_activity_id=%s,imported_at=now(),updated_at=now() WHERE id=%s""",
                (activity["id"],record_id)
            )
            _refresh_batch(conn,r["batch_id"])
            conn.commit()
            return {"idempotent":False,"activity_id":activity["id"],"execution_id":execution["id"],"record_id":record_id}
        except Exception:
            conn.rollback(); raise
