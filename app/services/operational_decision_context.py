from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from ..db import connection
from .activity_intelligence import build_intelligence_context, intelligence_analysis
from .activity_proactive_planner import proactive_board
from .activity_register import ActivityRegisterNotFound, ActivityRegisterValidation

CONTRACT_VERSION = "OI-1.1.0"
DECISION_STATUSES = ["APPLY", "CONDITIONAL", "MODIFY", "HOLD", "REJECT"]


def _age_days(value, as_of_date: date):
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.date()
    return max(0, (as_of_date - value).days)


def _freshness(age_days):
    if age_days is None:
        return "UNKNOWN"
    if age_days <= 7:
        return "CURRENT"
    if age_days <= 21:
        return "RECENT"
    return "HISTORICAL"


def _all_stock():
    with connection() as conn:
        rows = conn.execute(
            """SELECT ci.*,p.category,p.formulation,p.composition_text
               FROM public.current_inventory ci
               JOIN public.products p ON p.product_code=ci.product_code
               WHERE p.active=true
               ORDER BY p.category,ci.product_name,ci.location_code"""
        ).fetchall()
    return [dict(r) for r in rows]


def _product_recency(ctx):
    uses = {}
    for activity in ctx["recent_activities"]:
        for product in activity["products"]:
            code = product["product_code"]
            item = uses.setdefault(code, {
                "product_code": code,
                "product_name": product.get("product_name"),
                "category": product.get("category"),
                "formulation": product.get("formulation"),
                "composition_text": product.get("composition_text"),
                "last_used_date": activity["execution_date"],
                "last_used_dap": activity.get("dap_at_execution"),
                "use_count_in_window": 0,
                "active_ingredients": product.get("active_ingredients") or [],
                "recent_uses": [],
            })
            item["use_count_in_window"] += 1
            item["recent_uses"].append({
                "date": activity["execution_date"],
                "dap": activity.get("dap_at_execution"),
                "activity_type_code": activity.get("activity_type_code"),
                "quantity": product.get("actual_total_quantity"),
                "unit": product.get("actual_total_unit_code"),
            })
            if activity["execution_date"] > item["last_used_date"]:
                item["last_used_date"] = activity["execution_date"]
                item["last_used_dap"] = activity.get("dap_at_execution")
    out = []
    for item in uses.values():
        item["days_since_last_use"] = (ctx["as_of_date"] - item["last_used_date"]).days
        item["recent_uses"].sort(key=lambda x: x["date"], reverse=True)
        out.append(item)
    return sorted(out, key=lambda x: (x["days_since_last_use"], x["product_code"]))


def _observations(ctx):
    out = []
    for raw in ctx["observations"]:
        row = dict(raw)
        age = _age_days(row.get("observed_at"), ctx["as_of_date"])
        row["age_days"] = age
        row["freshness"] = _freshness(age)
        out.append(row)
    return out


def _latest_weather_outlook(crop_cycle_id: UUID, horizon_days: int):
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=horizon_days)
    with connection() as conn:
        cycle = conn.execute(
            "SELECT farm_id,plot_id FROM public.crop_cycles WHERE id=%s",
            (crop_cycle_id,),
        ).fetchone()
        if not cycle:
            raise ActivityRegisterNotFound("Crop Cycle not found.")
        loc = conn.execute(
            """SELECT * FROM public.weather_locations
               WHERE farm_id=%s AND plot_id=%s AND active=true
               ORDER BY updated_at DESC LIMIT 1""",
            (cycle["farm_id"], cycle["plot_id"]),
        ).fetchone()
        if not loc:
            loc = conn.execute(
                """SELECT * FROM public.weather_locations
                   WHERE farm_id=%s AND plot_id IS NULL AND active=true
                   ORDER BY updated_at DESC LIMIT 1""",
                (cycle["farm_id"],),
            ).fetchone()
        if not loc:
            return {
                "status": "UNAVAILABLE",
                "reason": "WEATHER_LOCATION_NOT_CONFIGURED",
                "guardrail": "Unavailable weather is not equivalent to safe weather.",
            }
        det = conn.execute(
            """WITH latest AS (
                 SELECT DISTINCT ON(model_code) id,model_code,retrieved_at
                 FROM public.weather_fetch_runs
                 WHERE weather_location_id=%s AND status='SUCCESS'
                 ORDER BY model_code,retrieved_at DESC)
               SELECT l.model_code,l.retrieved_at,p.valid_at,p.precipitation_mm,
                      p.temperature_c,p.relative_humidity_pct,p.wind_speed_kmh,p.wind_gust_kmh
               FROM latest l JOIN public.weather_data_points p ON p.fetch_run_id=l.id
               WHERE p.valid_at BETWEEN %s AND %s
               ORDER BY p.valid_at,l.model_code""",
            (loc["id"], now, end),
        ).fetchall()
        ens = conn.execute(
            """WITH latest AS (
                 SELECT DISTINCT ON(model_code) id,model_code,retrieved_at
                 FROM public.weather_ensemble_runs
                 WHERE weather_location_id=%s AND status='SUCCESS'
                 ORDER BY model_code,retrieved_at DESC)
               SELECT l.model_code,l.retrieved_at,p.valid_at,
                      p.precipitation_probability_pct,p.precipitation_median_mm,p.precipitation_max_mm
               FROM latest l JOIN public.weather_ensemble_points p ON p.ensemble_run_id=l.id
               WHERE p.valid_at BETWEEN %s AND %s
               ORDER BY p.valid_at,l.model_code""",
            (loc["id"], now, end),
        ).fetchall()
    if not det and not ens:
        return {
            "status": "UNAVAILABLE",
            "reason": "NO_CURRENT_FORECAST_POINTS",
            "location_id": str(loc["id"]),
            "guardrail": "Unavailable weather is not equivalent to safe weather.",
        }
    retrieved = [r["retrieved_at"] for r in det] + [r["retrieved_at"] for r in ens]
    latest = max(retrieved) if retrieved else None
    if latest and latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    age_hours = round((now-latest.astimezone(timezone.utc)).total_seconds()/3600, 2) if latest else None
    by = defaultdict(lambda: {"det": set(), "ens": set(), "rain": [], "prob": [], "temp": [], "wind": [], "gust": []})
    for r in det:
        x = by[r["valid_at"].date().isoformat()]
        x["det"].add(r["model_code"])
        for src, dst in [("precipitation_mm","rain"),("temperature_c","temp"),("wind_speed_kmh","wind"),("wind_gust_kmh","gust")]:
            if r[src] is not None:
                x[dst].append(float(r[src]))
    for r in ens:
        x = by[r["valid_at"].date().isoformat()]
        x["ens"].add(r["model_code"])
        if r["precipitation_probability_pct"] is not None:
            x["prob"].append(float(r["precipitation_probability_pct"]))
    daily = []
    for day, x in sorted(by.items()):
        daily.append({
            "date": day,
            "deterministic_model_count": len(x["det"]),
            "ensemble_model_count": len(x["ens"]),
            "hourly_precipitation_signal_min_mm": min(x["rain"]) if x["rain"] else None,
            "hourly_precipitation_signal_max_mm": max(x["rain"]) if x["rain"] else None,
            "max_ensemble_precipitation_probability_pct": max(x["prob"]) if x["prob"] else None,
            "temperature_min_c": min(x["temp"]) if x["temp"] else None,
            "temperature_max_c": max(x["temp"]) if x["temp"] else None,
            "wind_speed_max_kmh": max(x["wind"]) if x["wind"] else None,
            "wind_gust_max_kmh": max(x["gust"]) if x["gust"] else None,
        })
    freshness = "FRESH" if age_hours is not None and age_hours <= 4 else "AGING" if age_hours is not None and age_hours <= 8 else "STALE"
    return {
        "status": "AVAILABLE",
        "location_id": str(loc["id"]),
        "forecast_timezone": loc["timezone"],
        "latest_retrieved_at": latest,
        "age_hours": age_hours,
        "freshness_status": freshness,
        "daily_outlook": daily,
        "guardrails": [
            "This is decision evidence, not an application authorization.",
            "For a specific spray/fertigation time, use the existing operational weather check.",
            "Stale or unavailable weather must not be interpreted as safe.",
        ],
    }


def build_crop_decision_context(crop_cycle_id: UUID, horizon_days: int = 7, history_days: int = 60):
    if not 1 <= horizon_days <= 14:
        raise ActivityRegisterValidation("horizon_days must be between 1 and 14.")
    if not 14 <= history_days <= 180:
        raise ActivityRegisterValidation("history_days must be between 14 and 180.")
    ctx = build_intelligence_context(crop_cycle_id, history_days=history_days)
    analysis = intelligence_analysis(ctx)
    planner = proactive_board(
        farm_id=ctx["crop_cycle"]["farm_id"],
        crop_cycle_id=crop_cycle_id,
        date_from=ctx["as_of_date"],
        date_to=ctx["as_of_date"] + timedelta(days=horizon_days),
    )
    observations = _observations(ctx)
    weather = _latest_weather_outlook(crop_cycle_id, horizon_days)
    stage_matches = analysis.get("crop_stage_matches") or []
    stage = {
        "crop_dap": ctx["dap"],
        "status": "RULE_MATCHED" if stage_matches else "DAP_ONLY",
        "matches": stage_matches,
        "guardrail": "If no configured stage rule matches, DAP is authoritative but physiological stage remains an agronomic inference that must be checked against field condition.",
    }
    gaps = []
    if not [o for o in observations if o["freshness"] == "CURRENT"]:
        gaps.append("NO_CURRENT_FIELD_OBSERVATION_WITHIN_7_DAYS")
    if weather.get("status") != "AVAILABLE":
        gaps.append("WEATHER_UNAVAILABLE")
    elif weather.get("freshness_status") == "STALE":
        gaps.append("WEATHER_STALE")
    if (ctx.get("remote_sensing") or {}).get("status") != "AVAILABLE":
        gaps.append("REMOTE_SENSING_UNAVAILABLE")
    return {
        "contract_version": CONTRACT_VERSION,
        "mode": "FARMAI_OPERATIONAL_DECISION",
        "as_of_date": ctx["as_of_date"],
        "crop_cycle": ctx["crop_cycle"],
        "stage_context": stage,
        "decision_statuses": DECISION_STATUSES,
        "decision_order": [
            "1_CURRENT_DAP_AND_STAGE",
            "2_COMPLETED_ACTIVITY_AND_PRODUCT_RECENCY",
            "3_CONFIRMED_NUTRIENT_EXPOSURE",
            "4_ACTIVE_INGREDIENT_ROTATION",
            "5_CURRENT_FIELD_OBSERVATIONS",
            "6_WEATHER_AND_ROOT_ZONE_CONSTRAINTS",
            "7_REMOTE_SENSING_AND_SCOUTING_EVIDENCE",
            "8_AGRONOMIC_NEED",
            "9_PRODUCT_COMPATIBILITY_AND_STOCK",
        ],
        "recent_completed_activities": ctx["recent_activities"],
        "product_recency": _product_recency(ctx),
        "nutrient_exposure": analysis.get("nutrient_summary") or [],
        "rotation_signals": analysis.get("rotation_signals") or [],
        "field_observations": observations,
        "weather_outlook": weather,
        "remote_sensing": ctx.get("remote_sensing"),
        "planner": planner,
        "current_stock": _all_stock(),
        "evidence_gaps": gaps,
        "recommendation_guardrails": [
            "Need first; product second; stock third. Stock availability is never the reason to recommend.",
            "Crop DAP/stage and days-since-last-product are separate clocks.",
            "Do not recommend routine calendar pesticide/fungicide applications without a current target or verified preventive rule.",
            "Do not diagnose nutrient deficiency solely from DAP, weather, or satellite indices.",
            "Historical plot/subplot weakness is not current evidence until reconfirmed.",
            "Weather must change WHETHER, WHAT, or WHEN when operationally relevant.",
            "Use APPLY, CONDITIONAL, MODIFY, HOLD, or REJECT for proposed actions.",
            "Always state what should NOT be applied automatically when relevant.",
            "Always state the trigger/evidence that would change a CONDITIONAL or HOLD decision.",
            "Remote sensing is evidence, never diagnosis.",
        ],
    }
