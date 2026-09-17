from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from ..db import connection
from .activity_farmer_experience import farmer_dashboard
from .activity_intelligence import build_intelligence_context
from .activity_proactive_planner import proactive_board
from .activity_farmer_entry import preview_farmer_activity, complete_farmer_activity
from .activity_history import activity_history_detail
from .activity_register import ActivityRegisterNotFound, ActivityRegisterValidation


CONTRACT_VERSION = "OI-1.3.2"


def _safe_section(name, fn):
    try:
        return {"status": "AVAILABLE", "data": fn()}
    except Exception as exc:
        return {
            "status": "UNAVAILABLE",
            "reason": f"{type(exc).__name__}: {str(exc)[:500]}",
            "section": name,
        }


def _resolve_farm(farm_id=None):
    with connection() as conn:
        if farm_id:
            row = conn.execute(
                "SELECT * FROM public.farms WHERE id=%s AND active=true", (farm_id,)
            ).fetchone()
        else:
            rows = conn.execute(
                "SELECT * FROM public.farms WHERE active=true ORDER BY created_at"
            ).fetchall()
            if len(rows) != 1:
                raise ActivityRegisterValidation(
                    "Operational default farm requires exactly one active farm; "
                    "supply farm_id when multiple farms exist."
                )
            row = rows[0]
    if not row:
        raise ActivityRegisterNotFound("Farm not found.")
    return dict(row)


def _complete_inventory():
    """
    Authoritative complete operational stock projection.

    Important: starts from products, not current_inventory, so an active product
    remains visible even if it has no transaction row yet or its quantity is zero.
    """
    with connection() as conn:
        rows = conn.execute(
            """
            WITH inventory_totals AS (
                SELECT
                    product_code,
                    MAX(unit) AS inventory_unit,
                    SUM(physical_stock) AS physical_stock,
                    SUM(reserved_stock) AS reserved_stock,
                    SUM(available_stock) AS available_stock,
                    jsonb_agg(
                        jsonb_build_object(
                            'location_code', location_code,
                            'physical_stock', physical_stock,
                            'reserved_stock', reserved_stock,
                            'available_stock', available_stock
                        )
                        ORDER BY location_code
                    ) AS locations
                FROM public.current_inventory
                GROUP BY product_code
            )
            SELECT
                p.id AS product_id,
                p.product_code,
                p.product_name,
                p.brand,
                p.category AS database_category,
                p.formulation,
                p.composition_text,
                p.base_unit,
                p.reorder_level,
                p.minimum_stock,
                pdm.registry_category,
                pdm.product_name_mr,
                pdm.used_for_en,
                pdm.used_for_mr,
                pdm.apply_when_en,
                pdm.apply_when_mr,
                pdm.standard_dose,
                pdm.content,
                pdm.farmai_advice_en,
                pdm.farmai_advice_mr,
                COALESCE(it.inventory_unit, p.base_unit) AS stock_unit,
                COALESCE(it.physical_stock, 0) AS physical_stock,
                COALESCE(it.reserved_stock, 0) AS reserved_stock,
                COALESCE(it.available_stock, 0) AS available_stock,
                COALESCE(it.locations, '[]'::jsonb) AS locations
            FROM public.products p
            LEFT JOIN inventory_totals it
              ON lower(it.product_code)=lower(p.product_code)
            LEFT JOIN public.product_display_metadata pdm
              ON pdm.product_id=p.id
            WHERE p.active=true
            ORDER BY
                COALESCE(pdm.registry_category, p.category, 'ZZZ'),
                p.product_name,
                p.product_code
            """
        ).fetchall()
    return [dict(r) for r in rows]


def _stock_status(row):
    qty = Decimal(str(row["available_stock"] or 0))
    reorder = Decimal(str(row["reorder_level"] or 0))
    if qty < 0:
        return "DISCREPANCY"
    if qty == 0:
        return "OUT"
    if reorder > 0 and qty <= reorder:
        return "LOW"
    return "GOOD"


def operational_stock():
    """
    Compact, complete GPT-facing stock projection.

    Completeness is preserved by sourcing from _complete_inventory(), which starts
    from every active product. The response intentionally excludes internal IDs,
    per-location balances, formulation/composition duplicates and duplicated
    low-stock objects because those fields are not required to render the frozen
    V7.2 registry and can exceed GPT Action response limits.
    """
    source_rows = _complete_inventory()

    category_order = [
        ("Fertilizers", "खते"),
        ("Biostimulants & Biofertilizers", "जैव उत्तेजक व जैव खते"),
        ("Micronutrients", "सूक्ष्म अन्नद्रव्ये"),
        ("Fungicides", "बुरशीनाशके"),
        ("Insecticides", "कीटकनाशके"),
        ("Herbicides", "तणनाशके"),
        ("Biopesticides", "जैव कीटकनाशके"),
        ("Adjuvants / Stickers", "सहाय्यक द्रव्ये / स्टिकर्स"),
    ]

    legacy_map = {
        "Fertilizers": "Fertilizers",
        "Biostimulants & Growth Promoters": "Biostimulants & Biofertilizers",
        "Biostimulants & Biofertilizers": "Biostimulants & Biofertilizers",
        "Micronutrients": "Micronutrients",
        "Fungicides": "Fungicides",
        "Insecticides": "Insecticides",
        "Herbicides": "Herbicides",
        "Biopesticides": "Biopesticides",
        "Adjuvants": "Adjuvants / Stickers",
        "Adjuvants / Stickers": "Adjuvants / Stickers",
    }

    grouped = {
        name_en: {
            "name_en": name_en,
            "name_mr": name_mr,
            "products": [],
        }
        for name_en, name_mr in category_order
    }

    unmapped = []

    for row in source_rows:
        category = (
            row.get("registry_category")
            or legacy_map.get(row.get("database_category"))
        )

        if category not in grouped:
            unmapped.append(row["product_code"])
            continue

        status_code = _stock_status(row)
        status_display = {
            "GOOD": "🟢 Good",
            "LOW": "🟡 Low",
            "OUT": "🔴 Out",
            "DISCREPANCY": "⚪ Unknown",
        }[status_code]

        qty = row.get("available_stock")
        unit = row.get("stock_unit") or row.get("base_unit")
        qty_text = format(Decimal(str(qty or 0)), "f").rstrip("0").rstrip(".")
        if not qty_text:
            qty_text = "0"
        stock_display = f"{qty_text} {unit}" if unit else qty_text

        grouped[category]["products"].append({
            "product_code": row["product_code"],
            "product_en": row["product_name"],
            "product_mr": row.get("product_name_mr"),
            "stock": stock_display,
            "status": status_display,
            "used_for_en": row.get("used_for_en") or "Unknown",
            "used_for_mr": row.get("used_for_mr") or "Unknown",
            "apply_when_en": row.get("apply_when_en") or "Unknown",
            "apply_when_mr": row.get("apply_when_mr") or "Unknown",
            "dose": row.get("standard_dose") or "Unknown",
            "content": row.get("content") or "Unknown",
            "farmai_advice_en": row.get("farmai_advice_en") or "—",
            "farmai_advice_mr": row.get("farmai_advice_mr") or "—",
            "inventory_discrepancy": status_code == "DISCREPANCY",
        })

    categories = [grouped[name_en] for name_en, _ in category_order]
    returned_count = sum(len(c["products"]) for c in categories)

    return {
        "contract_version": CONTRACT_VERSION,
        "as_of_date": date.today(),
        "registry_version": "7.2",
        "columns": [
            "Product",
            "Stock",
            "Status",
            "Used For",
            "Apply When",
            "Dose",
            "Content",
            "FarmAI Advice",
        ],
        "completeness": {
            "complete_active_product_projection": True,
            "active_product_count": len(source_rows),
            "returned_product_count": returned_count,
            "unmapped_product_count": len(unmapped),
            "unmapped_product_codes": unmapped,
        },
        "categories": categories,
    }


def operational_activity_history(
    *,
    crop_cycle_id: UUID | None = None,
    crop_name: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    execution_status: str | None = None,
    limit: int = 200,
):
    if not 1 <= limit <= 500:
        raise ActivityRegisterValidation("limit must be between 1 and 500.")
    if date_from and date_to and date_from > date_to:
        raise ActivityRegisterValidation("date_from cannot be later than date_to.")

    clauses = ["1=1"]
    params = []

    if crop_cycle_id:
        clauses.append("cc.id=%s")
        params.append(crop_cycle_id)
    if crop_name:
        clauses.append(
            "(lower(cc.crop_name_en)=lower(%s) OR cc.crop_name_mr=%s)"
        )
        params.extend([crop_name, crop_name])
    if date_from:
        clauses.append(
            "COALESCE(ae.execution_date,a.scheduled_date,a.planned_date,a.created_at::date) >= %s"
        )
        params.append(date_from)
    if date_to:
        clauses.append(
            "COALESCE(ae.execution_date,a.scheduled_date,a.planned_date,a.created_at::date) <= %s"
        )
        params.append(date_to)
    if execution_status:
        clauses.append("ae.status=%s")
        params.append(execution_status)

    params.append(limit)

    sql = f"""
        SELECT
            cc.id AS crop_cycle_id,
            cc.cycle_code,
            cc.crop_name_en,
            cc.crop_name_mr,
            cc.planting_date,
            cc.dap_baseline_date,
            pplot.code AS plot_code,
            pplot.name_en AS plot_name_en,
            pplot.name_mr AS plot_name_mr,

            a.id AS activity_id,
            a.status AS activity_status,
            a.name_en AS activity_name_en,
            a.name_mr AS activity_name_mr,
            a.notes_en AS activity_notes_en,
            a.notes_mr AS activity_notes_mr,
            a.source_type,
            a.source_reference,
            a.verification_status,
            a.source_confidence,
            at.code AS activity_type_code,
            at.name_en AS activity_type_name_en,
            at.name_mr AS activity_type_name_mr,
            a.application_method_code,

            ae.id AS execution_id,
            ae.execution_no,
            ae.execution_date,
            ae.status AS execution_status,
            ae.dap_at_execution,
            ae.area_treated,
            ae.area_unit_code,
            ae.pump_count,
            ae.water_volume,
            ae.water_unit_code,
            ae.performed_by,
            ae.notes_en AS execution_notes_en,
            ae.notes_mr AS execution_notes_mr,

            COALESCE(
                (
                    SELECT jsonb_agg(
                        jsonb_build_object(
                            'code', ap.code,
                            'name_en', ap.name_en,
                            'name_mr', ap.name_mr
                        )
                        ORDER BY ap.sort_order, ap.code
                    )
                    FROM public.activity_purpose_links apl
                    JOIN public.activity_purposes ap
                      ON ap.id=apl.activity_purpose_id
                    WHERE apl.activity_id=a.id
                ),
                '[]'::jsonb
            ) AS purposes,

            COALESCE(
                (
                    SELECT jsonb_agg(
                        jsonb_build_object(
                            'execution_input_id', aei.id,
                            'product_id', prod.id,
                            'product_code', prod.product_code,
                            'product_name_en', prod.product_name,
                            'product_name_mr', pdm.product_name_mr,
                            'brand', prod.brand,
                            'category', prod.category,
                            'actual_dose', aei.actual_dose,
                            'actual_dose_unit_code', aei.actual_dose_unit_code,
                            'dose_basis_code', aei.dose_basis_code,
                            'actual_total_quantity', aei.actual_total_quantity,
                            'actual_total_unit_code', aei.actual_total_unit_code,
                            'stock_sync_status', aei.stock_sync_status,
                            'stock_transaction_id', aei.stock_transaction_id,
                            'stock_transaction_no', st.transaction_no,
                            'stock_transaction_type', st.transaction_type,
                            'stock_quantity_out', st.quantity_out,
                            'stock_unit', st.unit,
                            'stock_transaction_status', st.status
                        )
                        ORDER BY aei.created_at, aei.id
                    )
                    FROM public.activity_execution_inputs aei
                    JOIN public.products prod ON prod.id=aei.product_id
                    LEFT JOIN public.product_display_metadata pdm
                      ON pdm.product_id=prod.id
                    LEFT JOIN public.stock_transactions st
                      ON st.id=aei.stock_transaction_id
                    WHERE aei.execution_id=ae.id
                ),
                '[]'::jsonb
            ) AS inputs

        FROM public.activities a
        JOIN public.crop_cycles cc ON cc.id=a.crop_cycle_id
        JOIN public.plots pplot ON pplot.id=cc.plot_id
        JOIN public.activity_types at ON at.id=a.activity_type_id
        LEFT JOIN public.activity_executions ae ON ae.activity_id=a.id
        WHERE {" AND ".join(clauses)}
        ORDER BY
            COALESCE(ae.execution_date,a.scheduled_date,a.planned_date,a.created_at::date) DESC,
            a.created_at DESC,
            ae.execution_no DESC NULLS LAST
        LIMIT %s
    """

    with connection() as conn:
        rows = [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]

    completed = [
        r for r in rows if r.get("execution_status") == "COMPLETED"
    ]
    synced_inputs = sum(
        1
        for r in rows
        for item in (r.get("inputs") or [])
        if item.get("stock_sync_status") == "SYNCED"
    )

    return {
        "contract_version": CONTRACT_VERSION,
        "filters": {
            "crop_cycle_id": crop_cycle_id,
            "crop_name": crop_name,
            "date_from": date_from,
            "date_to": date_to,
            "execution_status": execution_status,
            "limit": limit,
        },
        "summary": {
            "returned_rows": len(rows),
            "completed_executions": len(completed),
            "stock_synced_inputs": synced_inputs,
        },
        "history": rows,
    }


def operational_health():
    required_relations = [
        "farms", "plots", "crop_cycles", "activities", "activity_executions",
        "activity_execution_inputs", "stock_transactions", "current_inventory",
        "products", "product_display_metadata", "intelligence_recommendations",
        "weather_locations", "plot_geometries", "plot_remote_observations",
        "scouting_tasks", "external_data_providers", "weather_fetch_runs",
        "weather_data_points", "weather_ensemble_runs", "weather_ensemble_points",
    ]
    with connection() as conn:
        db_today = conn.execute("SELECT CURRENT_DATE AS today").fetchone()["today"]
        rels = {}
        for rel in required_relations:
            rels[rel] = bool(
                conn.execute(
                    "SELECT to_regclass(%s) AS r", (f"public.{rel}",)
                ).fetchone()["r"]
            )
        phase_counts = conn.execute(
            """SELECT
              (SELECT count(*) FROM public.farms WHERE active=true) active_farms,
              (SELECT count(*) FROM public.crop_cycles WHERE status='ACTIVE') active_crop_cycles,
              (SELECT count(*) FROM public.products WHERE active=true) active_products,
              (SELECT count(*) FROM public.activities) activities,
              (SELECT count(*) FROM public.activity_executions) executions,
              (SELECT count(*) FROM public.stock_transactions) stock_transactions"""
        ).fetchone()
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "READY" if all(rels.values()) else "DEGRADED",
        "db_today": db_today,
        "required_relations": rels,
        "counts": dict(phase_counts),
        "write_policy": (
            "Crop-use stock consumption must be recorded through "
            "completeOperationalActivity so Activity + Execution + Stock lineage is preserved."
        ),
    }


def capabilities():
    return {
        "contract_version": CONTRACT_VERSION,
        "mode": "FARMAI_OPERATIONAL",
        "read_tools": [
            "getOperationalContext",
            "getOperationalStock",
            "getOperationalActivityHistory",
            "getOperationalHealth",
            "getOperationalCropDecisionContext",
            "getBestOperationalSprayWindow",
        ],
        "write_tools": [
            "previewOperationalActivity",
            "completeOperationalActivity",
        ],
        "write_guardrails": {
            "preview": "No authoritative write.",
            "complete": (
                "Requires farmer_authorized=true. Crop-use consumption creates "
                "Activity + Execution and then idempotently synchronizes Stock."
            ),
            "crop_usage_rule": (
                "Never use a generic stock-usage transaction when crop/activity/purpose "
                "context exists; use completeOperationalActivity."
            ),
            "idempotency": (
                "Retry the same logical write with the same idempotency_key. "
                "Never generate a new key for a retry of the same activity."
            ),
            "recommendations": (
                "Never imply or record COMPLETED without explicit farmer authorization."
            ),
            "remote_sensing": "Evidence only; never diagnosis or execution authority.",
        },
        "read_contract": {
            "stock": (
                "getOperationalStock returns every active product, including zero-stock "
                "products and products without inventory transactions."
            ),
            "activity_history": (
                "getOperationalActivityHistory is the authoritative GPT-facing history read."
            ),
            "spray_window": (
                "getBestOperationalSprayWindow resolves stored farm/crop/plot geotags, "
                "refreshes weather evidence and ranks today/tomorrow spray windows."
            ),
        },
        "truth_model": {
            "current_operational_state": "FarmAI API/database",
            "conversation_memory": "Context aid only; never current operational truth",
        },
    }


def build_operational_context(
    farm_id: UUID | None = None,
    crop_cycle_id: UUID | None = None,
    horizon_days: int = 7,
    history_days: int = 30,
    include_intelligence: bool = True,
):
    if not 1 <= horizon_days <= 30:
        raise ActivityRegisterValidation("horizon_days must be between 1 and 30.")
    if not 1 <= history_days <= 180:
        raise ActivityRegisterValidation("history_days must be between 1 and 180.")

    farm = _resolve_farm(farm_id)
    today = date.today()
    dashboard = farmer_dashboard(
        farm_id=farm["id"],
        crop_cycle_id=crop_cycle_id,
        date_from=today - timedelta(days=history_days),
        date_to=today + timedelta(days=horizon_days),
    )
    cycles = [
        c for c in dashboard["crop_cycles"]
        if c["status"] == "ACTIVE"
        and (not crop_cycle_id or c["crop_cycle_id"] == crop_cycle_id)
    ]

    planner = _safe_section(
        "planner",
        lambda: proactive_board(
            farm_id=farm["id"],
            crop_cycle_id=crop_cycle_id,
            date_from=today,
            date_to=today + timedelta(days=horizon_days),
        ),
    )
    stock = _safe_section("stock", operational_stock)
    recent_history = _safe_section(
        "activity_history",
        lambda: operational_activity_history(
            crop_cycle_id=crop_cycle_id,
            date_from=today - timedelta(days=history_days),
            date_to=today,
            limit=200,
        ),
    )

    intelligence = {}
    if include_intelligence:
        for cycle in cycles:
            cid = cycle["crop_cycle_id"]
            intelligence[str(cid)] = _safe_section(
                "intelligence",
                lambda cid=cid: build_intelligence_context(
                    cid, history_days=history_days
                ),
            )

    attention = {
        "overdue": dashboard["summary"].get("overdue", 0),
        "today": dashboard["summary"].get("today", 0),
        "upcoming": dashboard["summary"].get("upcoming", 0),
        "degraded_sections": [
            name for name, section in (
                ("planner", planner),
                ("stock", stock),
                ("activity_history", recent_history),
            )
            if section["status"] != "AVAILABLE"
        ] + [
            f"intelligence:{cid}"
            for cid, section in intelligence.items()
            if section["status"] != "AVAILABLE"
        ],
    }

    return {
        "contract_version": CONTRACT_VERSION,
        "mode": "FARMAI_OPERATIONAL",
        "as_of_date": today,
        "farm": farm,
        "attention": attention,
        "dashboard": dashboard,
        "planner": planner,
        "stock": stock,
        "recent_activity_history": recent_history,
        "intelligence_by_crop_cycle": intelligence,
        "guardrails": [
            "COMPLETED, PLANNED, RECOMMENDED, OBSERVED and REMOTE_EVIDENCE are distinct states.",
            "Remote sensing is evidence, not diagnosis.",
            "No recommendation becomes a completed Activity without farmer authorization.",
            "Crop-use stock deductions must retain Activity/Execution lineage.",
            "Current operational facts come from FarmAI, not conversation memory.",
        ],
    }


def preview_operational_activity(entry):
    return preview_farmer_activity(entry)


def _extract_write_confirmation(command, result):
    activity_record = result.get("activity") or {}
    header = activity_record.get("activity") or {}
    executions = activity_record.get("executions") or []
    execution = executions[-1] if executions else {}
    stock_sync = result.get("stock_sync") or {}

    activity_id = header.get("id")
    execution_id = execution.get("id")
    crop_cycle_id = header.get("crop_cycle_id") or command.entry.crop_cycle_id

    history_verified = False
    if activity_id:
        readback = activity_history_detail(activity_id)
        history_verified = any(
            row.get("execution_id") == execution_id
            for row in (readback.get("executions") or [])
        )

    stock_inputs = stock_sync.get("inputs") or []
    stock_verified = (
        not command.entry.sync_stock
        or (
            stock_sync.get("status") == "SYNCED"
            and len(stock_inputs) == len(command.entry.inputs)
            and all(x.get("transaction_id") for x in stock_inputs)
        )
    )

    return {
        "authoritative": True,
        "duplicate": bool(result.get("duplicate")),
        "activity_recorded": bool(activity_id),
        "execution_recorded": bool(execution_id),
        "history_verified": history_verified,
        "stock_sync_requested": command.entry.sync_stock,
        "stock_verified": stock_verified,
        "activity_id": activity_id,
        "execution_id": execution_id,
        "crop_cycle_id": crop_cycle_id,
        "crop_name": command.entry.crop_name,
        "execution_date": command.entry.execution_date,
        "activity_type_code": command.entry.activity_type_code,
        "purpose_codes": command.entry.purpose_codes,
        "stock_inputs": stock_inputs,
        "history_lookup": {
            "operation": "getOperationalActivityHistory",
            "activity_id": activity_id,
            "crop_cycle_id": crop_cycle_id,
        },
    }


def complete_operational_activity(command):
    if command.farmer_authorized is not True:
        raise ActivityRegisterValidation(
            "Explicit farmer authorization is required for an operational write."
        )

    # Preserve manual entry semantics elsewhere while recording GPT-originated
    # operational writes with accurate provenance.
    result = complete_farmer_activity(
        command.entry,
        source_type="AI_CHAT",
    )
    confirmation = _extract_write_confirmation(command, result)

    if not confirmation["activity_recorded"] or not confirmation["execution_recorded"]:
        raise ActivityRegisterValidation(
            "Operational write did not produce Activity + Execution lineage."
        )
    if command.entry.sync_stock and not confirmation["stock_verified"]:
        raise ActivityRegisterValidation(
            "Operational write completed without fully verified Stock synchronization."
        )
    if not confirmation["history_verified"]:
        raise ActivityRegisterValidation(
            "Operational write could not be verified in authoritative Activity History."
        )

    return {
        **result,
        "write_confirmation": confirmation,
    }
