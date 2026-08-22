from contextlib import contextmanager
from decimal import Decimal

import pytest

from app.api.v1 import registry


def _row(
    *,
    product_code,
    product_name,
    database_category,
    registry_category,
    available_stock,
    reorder_level=Decimal("0"),
    base_unit="kg",
    product_name_mr=None,
    used_for_en="Used for EN",
    used_for_mr="वापर",
    apply_when_en="Apply when EN",
    apply_when_mr="कधी वापरावे",
    standard_dose="As per label",
    content="Verified content",
    farmai_advice_en="Advice EN",
    farmai_advice_mr="सल्ला",
):
    return {
        "product_id": f"id-{product_code}",
        "product_code": product_code,
        "product_name": product_name,
        "brand": None,
        "database_category": database_category,
        "base_unit": base_unit,
        "reorder_level": reorder_level,
        "minimum_stock": Decimal("0"),
        "registry_category": registry_category,
        "product_name_mr": product_name_mr,
        "used_for_en": used_for_en,
        "used_for_mr": used_for_mr,
        "apply_when_en": apply_when_en,
        "apply_when_mr": apply_when_mr,
        "standard_dose": standard_dose,
        "content": content,
        "farmai_advice_en": farmai_advice_en,
        "farmai_advice_mr": farmai_advice_mr,
        "stock_unit": base_unit,
        "physical_stock": available_stock,
        "reserved_stock": Decimal("0"),
        "available_stock": available_stock,
    }


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _query):
        return _FakeResult(self._rows)


def _fake_connection_factory(rows):
    @contextmanager
    def _connection():
        yield _FakeConnection(rows)

    return _connection


def test_registry_has_exact_frozen_category_order():
    assert [c["name_en"] for c in registry.CATEGORY_DEFINITIONS] == [
        "Fertilizers",
        "Biostimulants & Biofertilizers",
        "Micronutrients",
        "Fungicides",
        "Insecticides",
        "Herbicides",
        "Biopesticides",
        "Adjuvants / Stickers",
    ]


def test_quantity_formatting_removes_trailing_zeroes():
    assert registry._format_quantity(Decimal("27.280")) == "27.28"
    assert registry._format_quantity(Decimal("6.000")) == "6"
    assert registry._stock_display(Decimal("0.400"), "kg") == "0.4 kg"


@pytest.mark.parametrize(
    ("stock", "reorder", "expected_code", "expected_display", "discrepancy"),
    [
        (Decimal("20"), Decimal("5"), "GOOD", "🟢 Good", False),
        (Decimal("5"), Decimal("5"), "LOW", "🟡 Low", False),
        (Decimal("0"), Decimal("5"), "OUT", "🔴 Out", False),
        (Decimal("-1"), Decimal("5"), "UNKNOWN", "⚪ Unknown", True),
        (None, Decimal("5"), "UNKNOWN", "⚪ Unknown", False),
    ],
)
def test_status_contract(stock, reorder, expected_code, expected_display, discrepancy):
    code, display, flag = registry._status(stock, reorder)

    assert code == expected_code
    assert display == expected_display
    assert flag is discrepancy


def test_zero_reorder_level_does_not_force_low_status():
    code, display, discrepancy = registry._status(
        Decimal("0.001"),
        Decimal("0"),
    )

    assert code == "GOOD"
    assert display == "🟢 Good"
    assert discrepancy is False


def test_product_marathi_exception_for_numeric_product_names():
    assert registry._show_marathi_product_name(
        "00:52:34 (MKP)",
        "मराठी नाव",
    ) is False

    assert registry._show_marathi_product_name(
        "Solubor (20% Boron)",
        "सोल्युबोर",
    ) is False

    assert registry._show_marathi_product_name(
        "Coragen",
        "कोराजेन",
    ) is True


def test_registry_endpoint_returns_eight_categories_and_fixed_columns(monkeypatch):
    rows = [
        _row(
            product_code="FERT-CN",
            product_name="Calcium Nitrate",
            database_category="Fertilizers",
            registry_category="Fertilizers",
            available_stock=Decimal("10"),
            reorder_level=Decimal("10"),
            product_name_mr="कॅल्शियम नायट्रेट",
        ),
        _row(
            product_code="INSECT-COR",
            product_name="Coragen",
            database_category="Insecticides",
            registry_category="Insecticides",
            available_stock=Decimal("0"),
            reorder_level=Decimal("150"),
            base_unit="ml",
            product_name_mr="कोराजेन",
        ),
        _row(
            product_code="BIO-METARHIZIUM",
            product_name="Metarhizium",
            database_category="Biologicals",
            registry_category="Biopesticides",
            available_stock=Decimal("2"),
            base_unit="kg",
            product_name_mr="मेटारायझियम",
        ),
    ]

    monkeypatch.setattr(
        registry,
        "connection",
        _fake_connection_factory(rows),
    )

    response = registry.get_registry_v72()

    assert response["ok"] is True
    assert response["data"]["registry_version"] == "7.2"
    assert response["data"]["columns"] == [
        "Product",
        "Stock",
        "Status",
        "Used For",
        "Apply When",
        "Dose",
        "Content",
        "FarmAI Advice",
    ]

    categories = response["data"]["categories"]

    assert len(categories) == 8
    assert [c["order"] for c in categories] == list(range(1, 9))
    assert [c["name_en"] for c in categories] == [
        "Fertilizers",
        "Biostimulants & Biofertilizers",
        "Micronutrients",
        "Fungicides",
        "Insecticides",
        "Herbicides",
        "Biopesticides",
        "Adjuvants / Stickers",
    ]

    assert response["meta"]["category_count"] == 8
    assert response["meta"]["product_count"] == 3
    assert response["meta"]["unmapped_product_count"] == 0


def test_registry_endpoint_keeps_empty_categories(monkeypatch):
    rows = [
        _row(
            product_code="FERT-CN",
            product_name="Calcium Nitrate",
            database_category="Fertilizers",
            registry_category="Fertilizers",
            available_stock=Decimal("10"),
            product_name_mr="कॅल्शियम नायट्रेट",
        )
    ]

    monkeypatch.setattr(
        registry,
        "connection",
        _fake_connection_factory(rows),
    )

    response = registry.get_registry_v72()

    categories = response["data"]["categories"]

    assert len(categories) == 8
    assert len(categories[0]["products"]) == 1
    assert all(
        len(category["products"]) == 0
        for category in categories[1:]
    )


def test_registry_endpoint_returns_bilingual_fields(monkeypatch):
    rows = [
        _row(
            product_code="INSECT-COR",
            product_name="Coragen",
            database_category="Insecticides",
            registry_category="Insecticides",
            available_stock=Decimal("100"),
            reorder_level=Decimal("50"),
            base_unit="ml",
            product_name_mr="कोराजेन",
            used_for_en="Caterpillar Control",
            used_for_mr="अळी नियंत्रण",
            apply_when_en="When caterpillars appear",
            apply_when_mr="अळी दिसल्यावर",
            standard_dose="5 ml / 20 L",
            content="Chlorantraniliprole 18.5% SC",
            farmai_advice_en="Rotate chemistry.",
            farmai_advice_mr="रासायनिक गट बदलत वापरा.",
        )
    ]

    monkeypatch.setattr(
        registry,
        "connection",
        _fake_connection_factory(rows),
    )

    response = registry.get_registry_v72()

    insecticides = response["data"]["categories"][4]
    product = insecticides["products"][0]

    assert product["product_en"] == "Coragen"
    assert product["product_mr"] == "कोराजेन"
    assert product["show_marathi_name"] is True
    assert product["used_for_en"] == "Caterpillar Control"
    assert product["used_for_mr"] == "अळी नियंत्रण"
    assert product["apply_when_en"] == "When caterpillars appear"
    assert product["apply_when_mr"] == "अळी दिसल्यावर"
    assert product["dose"] == "5 ml / 20 L"
    assert product["content"] == "Chlorantraniliprole 18.5% SC"
    assert product["farmai_advice_en"] == "Rotate chemistry."
    assert product["farmai_advice_mr"] == "रासायनिक गट बदलत वापरा."


def test_registry_endpoint_marks_negative_stock_as_discrepancy(monkeypatch):
    rows = [
        _row(
            product_code="FUNG-TROPHY",
            product_name="Trophy",
            database_category="Fungicides",
            registry_category="Fungicides",
            available_stock=Decimal("-200"),
            base_unit="g",
            product_name_mr="ट्रॉफी",
        )
    ]

    monkeypatch.setattr(
        registry,
        "connection",
        _fake_connection_factory(rows),
    )

    response = registry.get_registry_v72()

    fungicides = response["data"]["categories"][3]
    product = fungicides["products"][0]

    assert product["stock_display"] == "-200 g"
    assert product["status_code"] == "UNKNOWN"
    assert product["status_display"] == "⚪ Unknown"
    assert product["inventory_discrepancy"] is True


def test_registry_endpoint_reports_unmapped_products_without_creating_extra_category(
    monkeypatch,
):
    rows = [
        _row(
            product_code="TEST-UNMAPPED",
            product_name="Unmapped Product",
            database_category="Legacy Unknown",
            registry_category=None,
            available_stock=Decimal("1"),
            product_name_mr="चाचणी",
        )
    ]

    monkeypatch.setattr(
        registry,
        "connection",
        _fake_connection_factory(rows),
    )

    response = registry.get_registry_v72()

    assert len(response["data"]["categories"]) == 8
    assert response["meta"]["product_count"] == 0
    assert response["meta"]["unmapped_product_count"] == 1
    assert response["meta"]["unmapped_product_codes"] == ["TEST-UNMAPPED"]
