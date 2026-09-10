from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from ..db import connection
from .activity_farmer_experience import farmer_dashboard
from .activity_intelligence import build_intelligence_context
from .activity_proactive_planner import proactive_board
from .activity_farmer_entry import preview_farmer_activity, complete_farmer_activity
from .activity_register import ActivityRegisterNotFound, ActivityRegisterValidation


CONTRACT_VERSION = "OI-1.0.0"


def _safe_section(name, fn):
    try:
        return {"status": "AVAILABLE", "data": fn()}
    except Exception as exc:
        # Operational context should degrade by evidence section rather than fabricate
        # a "no issue" state. Error details are intentionally compact.
        return {
            "status": "UNAVAILABLE",
            "reason": f"{type(exc).__name__}: {str(exc)[:500]}",
            "section": name,
        }


def _inventory():
    with connection() as conn:
        rows = conn.execute(
            """SELECT * FROM public.current_inventory
               ORDER BY category, product_name, location_code"""
        ).fetchall()
    return [dict(r) for r in rows]


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


def operational_health():
    required_relations = [
        "farms", "plots", "crop_cycles", "activities", "activity_executions",
        "stock_transactions", "current_inventory", "intelligence_recommendations",
        "weather_locations", "plot_geometries", "plot_remote_observations",
        "scouting_tasks",
    ]
    with connection() as conn:
        db_today = conn.execute("SELECT CURRENT_DATE AS today").fetchone()["today"]
        rels = {}
        for rel in required_relations:
            rels[rel] = bool(
                conn.execute("SELECT to_regclass(%s) AS r", (f"public.{rel}",)).fetchone()["r"]
            )
        phase_counts = conn.execute(
            """SELECT
              (SELECT count(*) FROM public.farms WHERE active=true) active_farms,
              (SELECT count(*) FROM public.crop_cycles WHERE status='ACTIVE') active_crop_cycles,
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
        "write_policy": "Explicit farmer authorization required for operational complete.",
    }


def capabilities():
    return {
        "contract_version": CONTRACT_VERSION,
        "mode": "FARMAI_OPERATIONAL",
        "read_tools": [
            "getOperationalContext",
            "getOperationalStock",
            "getOperationalHealth",
        ],
        "write_tools": [
            "previewOperationalActivity",
            "completeOperationalActivity",
        ],
        "write_guardrails": {
            "preview": "No authoritative write.",
            "complete": "Requires farmer_authorized=true and uses existing Farmer Entry + Stock sync.",
            "recommendations": "Never imply or record COMPLETED without explicit farmer authorization.",
            "remote_sensing": "Evidence only; never diagnosis or execution authority.",
        },
        "truth_model": {
            "current_operational_state": "FarmAI API/database",
            "conversation_memory": "Context aid only; never current operational truth",
        },
    }


def operational_stock():
    inv = _inventory()
    low = []
    for r in inv:
        # Column names come from current_inventory. If a deployment adds/removes
        # thresholds, the full row remains available and this low-stock derivative
        # simply becomes best-effort.
        qty = r.get("available_quantity", r.get("quantity", r.get("current_stock")))
        minimum = r.get("minimum_stock")
        try:
            if qty is not None and minimum is not None and qty <= minimum:
                low.append(r)
        except TypeError:
            pass
    return {
        "as_of_date": date.today(),
        "inventory": inv,
        "low_stock": low,
        "inventory_count": len(inv),
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
        if c["status"] == "ACTIVE" and (not crop_cycle_id or c["crop_cycle_id"] == crop_cycle_id)
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

    intelligence = {}
    if include_intelligence:
        for cycle in cycles:
            cid = cycle["crop_cycle_id"]
            intelligence[str(cid)] = _safe_section(
                "intelligence",
                lambda cid=cid: build_intelligence_context(cid, history_days=history_days),
            )

    attention = {
        "overdue": dashboard["summary"].get("overdue", 0),
        "today": dashboard["summary"].get("today", 0),
        "upcoming": dashboard["summary"].get("upcoming", 0),
        "degraded_sections": [
            name for name, section in (("planner", planner), ("stock", stock))
            if section["status"] != "AVAILABLE"
        ] + [
            f"intelligence:{cid}" for cid, section in intelligence.items()
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
        "intelligence_by_crop_cycle": intelligence,
        "guardrails": [
            "COMPLETED, PLANNED, RECOMMENDED, OBSERVED and REMOTE_EVIDENCE are distinct states.",
            "Remote sensing is evidence, not diagnosis.",
            "No recommendation becomes a completed Activity without farmer authorization.",
            "Current operational facts come from FarmAI, not conversation memory.",
        ],
    }


def preview_operational_activity(entry):
    return preview_farmer_activity(entry)


def complete_operational_activity(command):
    # Literal True is enforced by schema; retain a service-layer check as defense in depth.
    if command.farmer_authorized is not True:
        raise ActivityRegisterValidation(
            "Explicit farmer authorization is required for an operational write."
        )
    return complete_farmer_activity(command.entry)
