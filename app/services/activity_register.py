"""
FarmAI Activity Register - Phase 2A service layer.

Responsibilities:
- Existing Farm / Plot / Crop Cycle context reads/writes.
- Create/read/filter Activity (क्रियाकलाप).
- Preserve planned inputs separately from actual Execution (अंमलबजावणी).
- Calculate historical DAP from crop_cycles.dap_baseline_date.
- Record structured observations and append audit entries.
- DO NOT deduct or alter stock.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from ..db import connection


class ActivityRegisterError(Exception): pass
class ActivityRegisterNotFound(ActivityRegisterError): pass
class ActivityRegisterConflict(ActivityRegisterError): pass
class ActivityRegisterValidation(ActivityRegisterError): pass


REFERENCE_TABLES = {
    "measurement_units": ("measurement_units", "code"),
    "dose_basis_types": ("dose_basis_types", "code"),
    "application_methods": ("application_methods", "code"),
    "activity_types": ("activity_types", "sort_order"),
    "activity_purposes": ("activity_purposes", "sort_order"),
    "observation_types": ("observation_types", "sort_order"),
}


def _dict(row): return dict(row) if row is not None else None
def _dicts(rows): return [dict(r) for r in rows]


def _audit(conn, *, entity_type, entity_id, action, old_data=None, new_data=None,
           reason_en=None, reason_mr=None, changed_by=None, correlation_id=None):
    conn.execute(
        """
        INSERT INTO public.activity_audit_log(
            entity_type, entity_id, action, old_data, new_data,
            reason_en, reason_mr, changed_by, correlation_id
        )
        VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s)
        """,
        (
            entity_type, entity_id, action,
            None if old_data is None else __import__("json").dumps(old_data, default=str),
            None if new_data is None else __import__("json").dumps(new_data, default=str),
            reason_en, reason_mr, changed_by, correlation_id,
        ),
    )


def _active_ref(conn, table, code, *, name="Reference"):
    row = conn.execute(
        f"SELECT * FROM public.{table} WHERE code=%s AND active=TRUE",
        (code,),
    ).fetchone()
    if not row:
        raise ActivityRegisterValidation(
            f"{name} '{code}' not found or inactive. "
            f"({name} संदर्भ सापडला नाही किंवा निष्क्रिय आहे.)"
        )
    return row


def _product_by_code(conn, product_code):
    row = conn.execute(
        """
        SELECT id, product_code, product_name, brand, category, base_unit
        FROM public.products
        WHERE lower(product_code)=lower(%s) AND active=TRUE
        """,
        (product_code,),
    ).fetchone()
    if not row:
        raise ActivityRegisterValidation(
            f"Product '{product_code}' not found. "
            "(उत्पादन मास्टरमध्ये उत्पादन सापडले नाही.)"
        )
    return row


def _crop_cycle(conn, crop_cycle_id):
    row = conn.execute(
        """
        SELECT cc.*, f.name_en farm_name_en, f.name_mr farm_name_mr,
               p.name_en plot_name_en, p.name_mr plot_name_mr
        FROM public.crop_cycles cc
        JOIN public.farms f ON f.id=cc.farm_id
        JOIN public.plots p ON p.id=cc.plot_id
        WHERE cc.id=%s
        """,
        (crop_cycle_id,),
    ).fetchone()
    if not row:
        raise ActivityRegisterNotFound(
            "Crop Cycle not found. (पीक चक्र सापडले नाही.)"
        )
    return row


def _dap_for_date(cycle, event_date):
    baseline = cycle["dap_baseline_date"]
    if baseline is None:
        baseline = cycle["planting_date"]
    dap = (event_date - baseline).days
    if dap < 0:
        raise ActivityRegisterValidation(
            "Activity/observation date cannot be earlier than the Crop Cycle DAP baseline. "
            "(क्रियाकलाप/निरीक्षण दिनांक DAP आधार दिनांकापूर्वी असू शकत नाही.)"
        )
    return dap


def get_reference_data():
    out = {}
    with connection() as conn:
        for key, (table, order_col) in REFERENCE_TABLES.items():
            out[key] = _dicts(
                conn.execute(
                    f"SELECT * FROM public.{table} WHERE active=TRUE ORDER BY {order_col}"
                ).fetchall()
            )
    return out


# ---------------------------------------------------------------------------
# Agricultural-context foundation
# ---------------------------------------------------------------------------

def create_farm(req):
    with connection() as conn:
        try:
            if req.code and conn.execute(
                "SELECT 1 FROM public.farms WHERE lower(code)=lower(%s)", (req.code,)
            ).fetchone():
                raise ActivityRegisterConflict(
                    "Farm code already exists. (शेत कोड आधीच अस्तित्वात आहे.)"
                )
            row = conn.execute(
                """
                INSERT INTO public.farms(
                    name_en,name_mr,code,description_en,description_mr,created_by,updated_by
                ) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *
                """,
                (req.name_en,req.name_mr,req.code,req.description_en,req.description_mr,
                 req.created_by,req.created_by),
            ).fetchone()
            conn.commit()
            return _dict(row)
        except Exception:
            conn.rollback()
            raise


def list_farms(active_only=True):
    sql = "SELECT * FROM public.farms"
    if active_only:
        sql += " WHERE active=TRUE"
    sql += " ORDER BY name_en"
    with connection() as conn:
        return _dicts(conn.execute(sql).fetchall())


def create_plot(req):
    with connection() as conn:
        try:
            if not conn.execute(
                "SELECT 1 FROM public.farms WHERE id=%s AND active=TRUE", (req.farm_id,)
            ).fetchone():
                raise ActivityRegisterNotFound("Farm not found. (शेत सापडले नाही.)")
            if req.area_unit_code:
                _active_ref(conn, "measurement_units", req.area_unit_code, name="Unit")
            row = conn.execute(
                """
                INSERT INTO public.plots(
                    farm_id,parent_plot_id,code,name_en,name_mr,area,area_unit_code,
                    description_en,description_mr,created_by,updated_by
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
                """,
                (req.farm_id,req.parent_plot_id,req.code,req.name_en,req.name_mr,
                 req.area,req.area_unit_code,req.description_en,req.description_mr,
                 req.created_by,req.created_by),
            ).fetchone()
            conn.commit()
            return _dict(row)
        except Exception:
            conn.rollback()
            raise


def list_plots(farm_id, active_only=True):
    sql = "SELECT * FROM public.plots WHERE farm_id=%s"
    if active_only:
        sql += " AND active=TRUE"
    sql += " ORDER BY code NULLS LAST, name_en"
    with connection() as conn:
        return _dicts(conn.execute(sql, (farm_id,)).fetchall())


def create_crop_cycle(req):
    with connection() as conn:
        try:
            plot = conn.execute(
                "SELECT 1 FROM public.plots WHERE id=%s AND farm_id=%s AND active=TRUE",
                (req.plot_id, req.farm_id),
            ).fetchone()
            if not plot:
                raise ActivityRegisterValidation(
                    "Plot must belong to selected Farm. "
                    "(निवडलेला प्लॉट संबंधित शेताचाच असणे आवश्यक आहे.)"
                )
            row = conn.execute(
                """
                INSERT INTO public.crop_cycles(
                    farm_id,plot_id,cycle_code,crop_name_en,crop_name_mr,
                    variety_en,variety_mr,season_name_en,season_name_mr,
                    planting_date,harvest_date,dap_baseline_date,dap_baseline_type,
                    area,area_unit_code,status,description_en,description_mr,
                    created_by,updated_by
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    req.farm_id,req.plot_id,req.cycle_code,req.crop_name_en,req.crop_name_mr,
                    req.variety_en,req.variety_mr,req.season_name_en,req.season_name_mr,
                    req.planting_date,req.harvest_date,req.dap_baseline_date,req.dap_baseline_type,
                    req.area,req.area_unit_code,req.status,req.description_en,req.description_mr,
                    req.created_by,req.created_by,
                ),
            ).fetchone()
            conn.commit()
            return _dict(row)
        except Exception:
            conn.rollback()
            raise


def list_crop_cycles(farm_id=None, plot_id=None, status=None):
    clauses, params = [], []
    if farm_id:
        clauses.append("cc.farm_id=%s"); params.append(farm_id)
    if plot_id:
        clauses.append("cc.plot_id=%s"); params.append(plot_id)
    if status:
        clauses.append("cc.status=%s"); params.append(status)
    sql = """
        SELECT cc.*, f.name_en farm_name_en, f.name_mr farm_name_mr,
               p.code plot_code, p.name_en plot_name_en, p.name_mr plot_name_mr,
               (CURRENT_DATE-cc.dap_baseline_date) current_dap
        FROM public.crop_cycles cc
        JOIN public.farms f ON f.id=cc.farm_id
        JOIN public.plots p ON p.id=cc.plot_id
    """
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY cc.planting_date DESC, cc.crop_name_en"
    with connection() as conn:
        return _dicts(conn.execute(sql, tuple(params)).fetchall())


def get_crop_cycle(crop_cycle_id):
    with connection() as conn:
        row = conn.execute(
            """
            SELECT cc.*, f.name_en farm_name_en, f.name_mr farm_name_mr,
                   p.code plot_code, p.name_en plot_name_en, p.name_mr plot_name_mr,
                   (CURRENT_DATE-cc.dap_baseline_date) current_dap
            FROM public.crop_cycles cc
            JOIN public.farms f ON f.id=cc.farm_id
            JOIN public.plots p ON p.id=cc.plot_id
            WHERE cc.id=%s
            """,
            (crop_cycle_id,),
        ).fetchone()
        if not row:
            raise ActivityRegisterNotFound("Crop Cycle not found. (पीक चक्र सापडले नाही.)")
        return _dict(row)


# ---------------------------------------------------------------------------
# Activity core
# ---------------------------------------------------------------------------

def create_activity(req):
    with connection() as conn:
        try:
            cycle = _crop_cycle(conn, req.crop_cycle_id)
            atype = _active_ref(conn, "activity_types", req.activity_type_code, name="Activity Type")
            if req.application_method_code:
                _active_ref(
                    conn, "application_methods", req.application_method_code,
                    name="Application Method"
                )

            planned_dap = None
            dap_date = req.scheduled_date or req.planned_date
            if dap_date:
                planned_dap = _dap_for_date(cycle, dap_date)

            purpose_rows = []
            for code in req.purpose_codes:
                purpose_rows.append(
                    _active_ref(conn, "activity_purposes", code, name="Activity Purpose")
                )

            products = []
            for item in req.inputs:
                products.append((item, _product_by_code(conn, item.product_code)))
                if item.planned_dose_unit_code:
                    _active_ref(conn, "measurement_units", item.planned_dose_unit_code, name="Unit")
                    _active_ref(conn, "dose_basis_types", item.dose_basis_code, name="Dose Basis")
                if item.planned_total_unit_code:
                    _active_ref(conn, "measurement_units", item.planned_total_unit_code, name="Unit")

            row = conn.execute(
                """
                INSERT INTO public.activities(
                    farm_id,crop_cycle_id,activity_type_id,application_method_code,status,
                    planned_date,scheduled_date,planned_dap,
                    planned_area,planned_area_unit_code,planned_pump_count,
                    planned_water_volume,planned_water_unit_code,
                    name_en,name_mr,description_en,description_mr,notes_en,notes_mr,
                    source_type,source_reference,verification_status,source_confidence,
                    created_by,updated_by
                )
                VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                RETURNING *
                """,
                (
                    cycle["farm_id"], req.crop_cycle_id, atype["id"],
                    req.application_method_code, req.status,
                    req.planned_date, req.scheduled_date, planned_dap,
                    req.planned_area, req.planned_area_unit_code, req.planned_pump_count,
                    req.planned_water_volume, req.planned_water_unit_code,
                    req.name_en, req.name_mr, req.description_en, req.description_mr,
                    req.notes_en, req.notes_mr,
                    req.source_type, req.source_reference,
                    req.verification_status, req.source_confidence,
                    req.created_by, req.created_by,
                ),
            ).fetchone()

            for p in purpose_rows:
                conn.execute(
                    """
                    INSERT INTO public.activity_purpose_links(activity_id,activity_purpose_id)
                    VALUES (%s,%s)
                    """,
                    (row["id"], p["id"]),
                )

            for item, product in products:
                conn.execute(
                    """
                    INSERT INTO public.activity_inputs(
                        activity_id,product_id,sequence_no,
                        planned_dose,planned_dose_unit_code,dose_basis_code,
                        planned_total_quantity,planned_total_unit_code,
                        notes_en,notes_mr
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        row["id"],product["id"],item.sequence_no,
                        item.planned_dose,item.planned_dose_unit_code,item.dose_basis_code,
                        item.planned_total_quantity,item.planned_total_unit_code,
                        item.notes_en,item.notes_mr,
                    ),
                )

            _audit(
                conn, entity_type="ACTIVITY", entity_id=row["id"], action="CREATE",
                new_data=_dict(row), changed_by=req.created_by
            )
            conn.commit()
            return get_activity(row["id"])
        except Exception:
            conn.rollback()
            raise


def _activity_header(conn, activity_id):
    row = conn.execute(
        """
        SELECT
            a.*,
            at.code activity_type_code,
            at.name_en activity_type_name_en,
            at.name_mr activity_type_name_mr,
            am.name_en application_method_name_en,
            am.name_mr application_method_name_mr,
            cc.crop_name_en, cc.crop_name_mr, cc.cycle_code,
            cc.dap_baseline_date, cc.dap_baseline_type,
            p.code plot_code, p.name_en plot_name_en, p.name_mr plot_name_mr
        FROM public.activities a
        JOIN public.activity_types at ON at.id=a.activity_type_id
        LEFT JOIN public.application_methods am ON am.code=a.application_method_code
        JOIN public.crop_cycles cc ON cc.id=a.crop_cycle_id
        JOIN public.plots p ON p.id=cc.plot_id
        WHERE a.id=%s
        """,
        (activity_id,),
    ).fetchone()
    if not row:
        raise ActivityRegisterNotFound("Activity not found. (क्रियाकलाप सापडला नाही.)")
    return row


def get_activity(activity_id):
    with connection() as conn:
        header = _activity_header(conn, activity_id)
        purposes = _dicts(conn.execute(
            """
            SELECT ap.code,ap.name_en,ap.name_mr
            FROM public.activity_purpose_links apl
            JOIN public.activity_purposes ap ON ap.id=apl.activity_purpose_id
            WHERE apl.activity_id=%s ORDER BY ap.sort_order
            """, (activity_id,)
        ).fetchall())
        planned_inputs = _dicts(conn.execute(
            """
            SELECT ai.*,p.product_code,p.product_name,p.brand,p.base_unit
            FROM public.activity_inputs ai
            JOIN public.products p ON p.id=ai.product_id
            WHERE ai.activity_id=%s ORDER BY ai.sequence_no,ai.created_at
            """, (activity_id,)
        ).fetchall())
        executions = _dicts(conn.execute(
            """
            SELECT * FROM public.activity_executions
            WHERE activity_id=%s ORDER BY execution_no
            """, (activity_id,)
        ).fetchall())
        for ex in executions:
            ex["inputs"] = _dicts(conn.execute(
                """
                SELECT aei.*,p.product_code,p.product_name,p.brand,p.base_unit
                FROM public.activity_execution_inputs aei
                JOIN public.products p ON p.id=aei.product_id
                WHERE aei.execution_id=%s ORDER BY aei.created_at
                """, (ex["id"],)
            ).fetchall())
        observations = _dicts(conn.execute(
            """
            SELECT ao.*,ot.code observation_type_code,
                   ot.name_en observation_type_name_en,ot.name_mr observation_type_name_mr
            FROM public.activity_observations ao
            JOIN public.observation_types ot ON ot.id=ao.observation_type_id
            WHERE ao.activity_id=%s ORDER BY ao.observed_at
            """, (activity_id,)
        ).fetchall())
        return {
            "activity": _dict(header),
            "purposes": purposes,
            "planned_inputs": planned_inputs,
            "executions": executions,
            "observations": observations,
        }


def list_activities(crop_cycle_id=None, status=None, activity_type_code=None,
                    date_from=None, date_to=None):
    clauses, params = [], []
    if crop_cycle_id:
        clauses.append("a.crop_cycle_id=%s"); params.append(crop_cycle_id)
    if status:
        clauses.append("a.status=%s"); params.append(status)
    if activity_type_code:
        clauses.append("at.code=%s"); params.append(activity_type_code.upper())
    if date_from:
        clauses.append("COALESCE(a.scheduled_date,a.planned_date,a.created_at::date)>=%s")
        params.append(date_from)
    if date_to:
        clauses.append("COALESCE(a.scheduled_date,a.planned_date,a.created_at::date)<=%s")
        params.append(date_to)

    sql = """
        SELECT a.id,a.crop_cycle_id,a.status,a.planned_date,a.scheduled_date,a.planned_dap,
               a.name_en,a.name_mr,a.source_type,a.verification_status,
               at.code activity_type_code,at.name_en activity_type_name_en,
               at.name_mr activity_type_name_mr,
               cc.cycle_code,cc.crop_name_en,cc.crop_name_mr,
               p.code plot_code,p.name_en plot_name_en,p.name_mr plot_name_mr,
               (SELECT count(*) FROM public.activity_inputs ai WHERE ai.activity_id=a.id) planned_input_count,
               (SELECT count(*) FROM public.activity_executions ae WHERE ae.activity_id=a.id) execution_count
        FROM public.activities a
        JOIN public.activity_types at ON at.id=a.activity_type_id
        JOIN public.crop_cycles cc ON cc.id=a.crop_cycle_id
        JOIN public.plots p ON p.id=cc.plot_id
    """
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY COALESCE(a.scheduled_date,a.planned_date,a.created_at::date) DESC,a.created_at DESC"
    with connection() as conn:
        return _dicts(conn.execute(sql, tuple(params)).fetchall())


def add_execution(activity_id, req):
    with connection() as conn:
        try:
            activity = _activity_header(conn, activity_id)
            if activity["status"] in ("SKIPPED","CANCELLED"):
                raise ActivityRegisterValidation(
                    "Cannot execute a skipped or cancelled Activity. "
                    "(वगळलेला किंवा रद्द केलेला क्रियाकलाप अंमलात आणता येत नाही.)"
                )
            cycle = _crop_cycle(conn, activity["crop_cycle_id"])
            dap = _dap_for_date(cycle, req.execution_date)

            row_no = conn.execute(
                "SELECT COALESCE(MAX(execution_no),0)+1 n FROM public.activity_executions WHERE activity_id=%s",
                (activity_id,),
            ).fetchone()
            execution_no = row_no["n"]

            ex = conn.execute(
                """
                INSERT INTO public.activity_executions(
                    activity_id,execution_no,execution_date,started_at,completed_at,status,
                    dap_at_execution,area_treated,area_unit_code,pump_count,
                    water_volume,water_unit_code,performed_by,notes_en,notes_mr,
                    created_by,updated_by
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    activity_id,execution_no,req.execution_date,req.started_at,req.completed_at,
                    req.status,dap,req.area_treated,req.area_unit_code,req.pump_count,
                    req.water_volume,req.water_unit_code,req.performed_by,req.notes_en,req.notes_mr,
                    req.created_by,req.created_by,
                ),
            ).fetchone()

            for item in req.inputs:
                product = _product_by_code(conn, item.product_code)
                if item.actual_dose_unit_code:
                    _active_ref(conn,"measurement_units",item.actual_dose_unit_code,name="Unit")
                    _active_ref(conn,"dose_basis_types",item.dose_basis_code,name="Dose Basis")
                if item.actual_total_unit_code:
                    _active_ref(conn,"measurement_units",item.actual_total_unit_code,name="Unit")

                planned = conn.execute(
                    """
                    SELECT id FROM public.activity_inputs
                    WHERE activity_id=%s AND product_id=%s
                    """, (activity_id,product["id"])
                ).fetchone()

                actual = conn.execute(
                    """
                    INSERT INTO public.activity_execution_inputs(
                        activity_id,execution_id,activity_input_id,product_id,
                        actual_dose,actual_dose_unit_code,dose_basis_code,
                        actual_total_quantity,actual_total_unit_code,
                        stock_sync_status,notes_en,notes_mr
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'NOT_REQUESTED',%s,%s)
                    RETURNING *
                    """,
                    (
                        activity_id,ex["id"],planned["id"] if planned else None,product["id"],
                        item.actual_dose,item.actual_dose_unit_code,item.dose_basis_code,
                        item.actual_total_quantity,item.actual_total_unit_code,
                        item.notes_en,item.notes_mr,
                    ),
                ).fetchone()
                _audit(
                    conn,entity_type="EXECUTION_INPUT",entity_id=actual["id"],action="CREATE",
                    new_data=_dict(actual),changed_by=req.created_by
                )

            # Execution state drives the parent Activity operational state.
            new_status = {
                "IN_PROGRESS": "IN_PROGRESS",
                "PARTIALLY_COMPLETED": "PARTIALLY_COMPLETED",
                "COMPLETED": "COMPLETED",
                "CANCELLED": "CANCELLED",
            }[req.status]
            old_status = activity["status"]
            conn.execute(
                "UPDATE public.activities SET status=%s,updated_at=now(),updated_by=%s WHERE id=%s",
                (new_status,req.created_by,activity_id),
            )
            _audit(
                conn,entity_type="EXECUTION",entity_id=ex["id"],action="CREATE",
                new_data=_dict(ex),changed_by=req.created_by
            )
            if old_status != new_status:
                _audit(
                    conn,entity_type="ACTIVITY",entity_id=activity_id,action="STATUS_CHANGE",
                    old_data={"status":old_status},new_data={"status":new_status},
                    changed_by=req.created_by
                )
            conn.commit()
            return get_activity(activity_id)
        except Exception:
            conn.rollback()
            raise


def change_activity_status(activity_id, target_status, req):
    with connection() as conn:
        try:
            activity = _activity_header(conn, activity_id)
            old = activity["status"]
            allowed = {
                "SKIPPED": {"DRAFT","PLANNED","SCHEDULED"},
                "CANCELLED": {"DRAFT","PLANNED","SCHEDULED","IN_PROGRESS","PARTIALLY_COMPLETED"},
            }
            if old not in allowed[target_status]:
                raise ActivityRegisterValidation(
                    f"Cannot change Activity from {old} to {target_status}. "
                    "(या स्थितीमध्ये क्रियाकलाप बदलण्यास परवानगी नाही.)"
                )
            conn.execute(
                """
                UPDATE public.activities
                SET status=%s,notes_en=COALESCE(%s,notes_en),notes_mr=COALESCE(%s,notes_mr),
                    updated_at=now(),updated_by=%s
                WHERE id=%s
                """,
                (target_status,req.reason_en,req.reason_mr,req.changed_by,activity_id),
            )
            _audit(
                conn,entity_type="ACTIVITY",entity_id=activity_id,action="STATUS_CHANGE",
                old_data={"status":old},new_data={"status":target_status},
                reason_en=req.reason_en,reason_mr=req.reason_mr,changed_by=req.changed_by
            )
            conn.commit()
            return get_activity(activity_id)
        except Exception:
            conn.rollback()
            raise


def create_observation(crop_cycle_id, req):
    with connection() as conn:
        try:
            cycle = _crop_cycle(conn, crop_cycle_id)
            otype = _active_ref(conn,"observation_types",req.observation_type_code,name="Observation Type")
            observed_at = req.observed_at or datetime.now(timezone.utc)
            dap = _dap_for_date(cycle, observed_at.date())

            if req.value_unit_code:
                _active_ref(conn,"measurement_units",req.value_unit_code,name="Unit")

            if req.activity_id:
                activity = _activity_header(conn, req.activity_id)
                if activity["crop_cycle_id"] != crop_cycle_id:
                    raise ActivityRegisterValidation(
                        "Observation Activity belongs to another Crop Cycle. "
                        "(निरीक्षणातील क्रियाकलाप दुसऱ्या पीक चक्राशी संबंधित आहे.)"
                    )
            if req.execution_id:
                ex = conn.execute(
                    """
                    SELECT 1 FROM public.activity_executions
                    WHERE id=%s AND activity_id=%s
                    """,(req.execution_id,req.activity_id)
                ).fetchone()
                if not ex:
                    raise ActivityRegisterValidation(
                        "Execution does not belong to the supplied Activity. "
                        "(अंमलबजावणी दिलेल्या क्रियाकलापाशी संबंधित नाही.)"
                    )

            row = conn.execute(
                """
                INSERT INTO public.activity_observations(
                    farm_id,crop_cycle_id,activity_id,execution_id,observation_type_id,
                    observed_at,dap_at_observation,severity,numeric_value,value_unit_code,
                    description_en,description_mr,notes_en,notes_mr,
                    source_type,source_reference,verification_status,created_by,updated_by
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    cycle["farm_id"],crop_cycle_id,req.activity_id,req.execution_id,otype["id"],
                    observed_at,dap,req.severity,req.numeric_value,req.value_unit_code,
                    req.description_en,req.description_mr,req.notes_en,req.notes_mr,
                    req.source_type,req.source_reference,req.verification_status,
                    req.created_by,req.created_by,
                ),
            ).fetchone()
            _audit(
                conn,entity_type="OBSERVATION",entity_id=row["id"],action="CREATE",
                new_data=_dict(row),changed_by=req.created_by
            )
            conn.commit()
            return _dict(row)
        except Exception:
            conn.rollback()
            raise


def crop_timeline(crop_cycle_id, date_from=None, date_to=None):
    with connection() as conn:
        _crop_cycle(conn,crop_cycle_id)
        params = [crop_cycle_id]
        activity_where = ""
        observation_where = ""
        if date_from:
            activity_where += " AND COALESCE(ae.execution_date,a.scheduled_date,a.planned_date,a.created_at::date)>=%s"
            observation_where += " AND ao.observed_at::date>=%s"
            params.append(date_from)
        # Simpler to execute separately to keep parameter sets deterministic.
        aparams=[crop_cycle_id]
        awhere=""
        if date_from: awhere+=" AND COALESCE(ae.execution_date,a.scheduled_date,a.planned_date,a.created_at::date)>=%s"; aparams.append(date_from)
        if date_to: awhere+=" AND COALESCE(ae.execution_date,a.scheduled_date,a.planned_date,a.created_at::date)<=%s"; aparams.append(date_to)
        activities = _dicts(conn.execute(
            f"""
            SELECT
                a.id activity_id, a.status activity_status,
                at.code activity_type_code,at.name_en activity_type_name_en,at.name_mr activity_type_name_mr,
                a.planned_date,a.scheduled_date,a.planned_dap,
                ae.id execution_id,ae.execution_no,ae.execution_date,ae.status execution_status,
                ae.dap_at_execution,ae.pump_count,ae.water_volume,ae.water_unit_code,
                COALESCE(ae.execution_date,a.scheduled_date,a.planned_date,a.created_at::date) event_date
            FROM public.activities a
            JOIN public.activity_types at ON at.id=a.activity_type_id
            LEFT JOIN public.activity_executions ae ON ae.activity_id=a.id
            WHERE a.crop_cycle_id=%s {awhere}
            ORDER BY event_date,a.created_at,ae.execution_no
            """,tuple(aparams)
        ).fetchall())
        oparams=[crop_cycle_id]
        owhere=""
        if date_from: owhere+=" AND ao.observed_at::date>=%s"; oparams.append(date_from)
        if date_to: owhere+=" AND ao.observed_at::date<=%s"; oparams.append(date_to)
        observations = _dicts(conn.execute(
            f"""
            SELECT
                ao.id observation_id,ao.activity_id,ao.execution_id,ao.observed_at,
                ao.dap_at_observation,ao.severity,ao.description_en,ao.description_mr,
                ot.code observation_type_code,ot.name_en observation_type_name_en,ot.name_mr observation_type_name_mr
            FROM public.activity_observations ao
            JOIN public.observation_types ot ON ot.id=ao.observation_type_id
            WHERE ao.crop_cycle_id=%s {owhere}
            ORDER BY ao.observed_at
            """,tuple(oparams)
        ).fetchall())
        return {"crop_cycle":get_crop_cycle(crop_cycle_id),"activities":activities,"observations":observations}
