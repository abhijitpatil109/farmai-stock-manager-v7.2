"""
FarmAI Activity Register V1 - agricultural context service.

Scope:
- Read seeded Activity Register reference data.
- Create/list Farm (शेत), Plot (प्लॉट), and Crop Cycle (पीक चक्र).
- Keep Stock Manager tables untouched.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ..db import connection


REFERENCE_TABLES = {
    "measurement_units": ("measurement_units", "code"),
    "dose_basis_types": ("dose_basis_types", "code"),
    "application_methods": ("application_methods", "code"),
    "activity_types": ("activity_types", "sort_order"),
    "activity_purposes": ("activity_purposes", "sort_order"),
    "observation_types": ("observation_types", "sort_order"),
}


class ActivityRegisterConflict(Exception):
    pass


class ActivityRegisterNotFound(Exception):
    pass


class ActivityRegisterValidation(Exception):
    pass


def _row_to_dict(row):
    return dict(row) if row is not None else None


def _rows_to_dicts(rows):
    return [dict(row) for row in rows]


def get_reference_data() -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = {}
    with connection() as conn:
        for key, (table, order_column) in REFERENCE_TABLES.items():
            rows = conn.execute(
                f"SELECT * FROM public.{table} WHERE active=TRUE ORDER BY {order_column}"
            ).fetchall()
            data[key] = _rows_to_dicts(rows)
    return data


def create_farm(payload) -> dict[str, Any]:
    with connection() as conn:
        try:
            if payload.code:
                duplicate = conn.execute(
                    "SELECT id FROM public.farms WHERE lower(code)=lower(%s)",
                    (payload.code,),
                ).fetchone()
                if duplicate:
                    raise ActivityRegisterConflict(
                        "Farm code already exists. (शेत कोड आधीच अस्तित्वात आहे.)"
                    )

            row = conn.execute(
                """
                INSERT INTO public.farms(
                    name_en, name_mr, code, description_en, description_mr,
                    created_by, updated_by
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    payload.name_en, payload.name_mr, payload.code,
                    payload.description_en, payload.description_mr,
                    payload.created_by, payload.created_by,
                ),
            ).fetchone()
            conn.commit()
            return _row_to_dict(row)
        except Exception:
            conn.rollback()
            raise


def list_farms(active_only: bool = True) -> list[dict[str, Any]]:
    sql = "SELECT * FROM public.farms"
    params = ()
    if active_only:
        sql += " WHERE active=TRUE"
    sql += " ORDER BY name_en"
    with connection() as conn:
        return _rows_to_dicts(conn.execute(sql, params).fetchall())


def create_plot(payload) -> dict[str, Any]:
    with connection() as conn:
        try:
            farm = conn.execute(
                "SELECT id FROM public.farms WHERE id=%s AND active=TRUE",
                (payload.farm_id,),
            ).fetchone()
            if not farm:
                raise ActivityRegisterNotFound(
                    "Farm not found. (शेत सापडले नाही.)"
                )

            if payload.parent_plot_id:
                parent = conn.execute(
                    """
                    SELECT id FROM public.plots
                    WHERE id=%s AND farm_id=%s AND active=TRUE
                    """,
                    (payload.parent_plot_id, payload.farm_id),
                ).fetchone()
                if not parent:
                    raise ActivityRegisterValidation(
                        "Parent plot must belong to the same farm. "
                        "(पालक प्लॉट त्याच शेताचा असणे आवश्यक आहे.)"
                    )

            if payload.area_unit_code:
                unit = conn.execute(
                    """
                    SELECT code FROM public.measurement_units
                    WHERE code=%s AND active=TRUE AND dimension='AREA'
                    """,
                    (payload.area_unit_code.upper(),),
                ).fetchone()
                if not unit:
                    raise ActivityRegisterValidation(
                        "Invalid area unit. (क्षेत्रफळाचे एकक अवैध आहे.)"
                    )

            if payload.code:
                duplicate = conn.execute(
                    """
                    SELECT id FROM public.plots
                    WHERE farm_id=%s AND lower(code)=lower(%s)
                    """,
                    (payload.farm_id, payload.code),
                ).fetchone()
                if duplicate:
                    raise ActivityRegisterConflict(
                        "Plot code already exists in this farm. "
                        "(या शेतात प्लॉट कोड आधीच अस्तित्वात आहे.)"
                    )

            row = conn.execute(
                """
                INSERT INTO public.plots(
                    farm_id, parent_plot_id, code, name_en, name_mr,
                    area, area_unit_code, description_en, description_mr,
                    created_by, updated_by
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    payload.farm_id, payload.parent_plot_id, payload.code,
                    payload.name_en, payload.name_mr, payload.area,
                    payload.area_unit_code.upper() if payload.area_unit_code else None,
                    payload.description_en, payload.description_mr,
                    payload.created_by, payload.created_by,
                ),
            ).fetchone()
            conn.commit()
            return _row_to_dict(row)
        except Exception:
            conn.rollback()
            raise


def list_plots(farm_id: UUID, active_only: bool = True) -> list[dict[str, Any]]:
    sql = "SELECT * FROM public.plots WHERE farm_id=%s"
    params: list[Any] = [farm_id]
    if active_only:
        sql += " AND active=TRUE"
    sql += " ORDER BY name_en"
    with connection() as conn:
        return _rows_to_dicts(conn.execute(sql, tuple(params)).fetchall())


def create_crop_cycle(payload) -> dict[str, Any]:
    with connection() as conn:
        try:
            plot = conn.execute(
                """
                SELECT id FROM public.plots
                WHERE id=%s AND farm_id=%s AND active=TRUE
                """,
                (payload.plot_id, payload.farm_id),
            ).fetchone()
            if not plot:
                raise ActivityRegisterValidation(
                    "Plot must belong to the selected farm. "
                    "(निवडलेला प्लॉट संबंधित शेताचाच असणे आवश्यक आहे.)"
                )

            if payload.area_unit_code:
                unit = conn.execute(
                    """
                    SELECT code FROM public.measurement_units
                    WHERE code=%s AND active=TRUE AND dimension='AREA'
                    """,
                    (payload.area_unit_code.upper(),),
                ).fetchone()
                if not unit:
                    raise ActivityRegisterValidation(
                        "Invalid area unit. (क्षेत्रफळाचे एकक अवैध आहे.)"
                    )

            if payload.cycle_code:
                duplicate = conn.execute(
                    """
                    SELECT id FROM public.crop_cycles
                    WHERE farm_id=%s AND lower(cycle_code)=lower(%s)
                    """,
                    (payload.farm_id, payload.cycle_code),
                ).fetchone()
                if duplicate:
                    raise ActivityRegisterConflict(
                        "Crop Cycle code already exists in this farm. "
                        "(या शेतात पीक चक्र कोड आधीच अस्तित्वात आहे.)"
                    )

            row = conn.execute(
                """
                INSERT INTO public.crop_cycles(
                    farm_id, plot_id, cycle_code,
                    crop_name_en, crop_name_mr,
                    variety_en, variety_mr,
                    season_name_en, season_name_mr,
                    planting_date, harvest_date,
                    area, area_unit_code, status,
                    description_en, description_mr,
                    created_by, updated_by
                )
                VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                RETURNING *
                """,
                (
                    payload.farm_id, payload.plot_id, payload.cycle_code,
                    payload.crop_name_en, payload.crop_name_mr,
                    payload.variety_en, payload.variety_mr,
                    payload.season_name_en, payload.season_name_mr,
                    payload.planting_date, payload.harvest_date,
                    payload.area,
                    payload.area_unit_code.upper() if payload.area_unit_code else None,
                    payload.status,
                    payload.description_en, payload.description_mr,
                    payload.created_by, payload.created_by,
                ),
            ).fetchone()
            conn.commit()
            return _row_to_dict(row)
        except Exception:
            conn.rollback()
            raise


def list_crop_cycles(
    farm_id: UUID | None = None,
    plot_id: UUID | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    where = []
    params: list[Any] = []
    if farm_id:
        where.append("cc.farm_id=%s")
        params.append(farm_id)
    if plot_id:
        where.append("cc.plot_id=%s")
        params.append(plot_id)
    if status:
        where.append("cc.status=%s")
        params.append(status)

    sql = """
        SELECT
            cc.*,
            f.name_en AS farm_name_en,
            f.name_mr AS farm_name_mr,
            p.name_en AS plot_name_en,
            p.name_mr AS plot_name_mr
        FROM public.crop_cycles cc
        JOIN public.farms f ON f.id=cc.farm_id
        JOIN public.plots p ON p.id=cc.plot_id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY cc.planting_date DESC, cc.crop_name_en"

    with connection() as conn:
        return _rows_to_dicts(conn.execute(sql, tuple(params)).fetchall())


def get_crop_cycle(crop_cycle_id: UUID) -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT
                cc.*,
                f.name_en AS farm_name_en,
                f.name_mr AS farm_name_mr,
                p.name_en AS plot_name_en,
                p.name_mr AS plot_name_mr,
                (CURRENT_DATE - cc.planting_date) AS current_dap
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
        return _row_to_dict(row)
