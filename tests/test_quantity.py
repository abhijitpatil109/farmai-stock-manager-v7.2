from decimal import Decimal
import pytest

from app.quantity import QuantityNormalizationError, normalize_quantity


def test_grams_to_kilograms():
    assert normalize_quantity(Decimal("400"), "g", "kg") == Decimal("0.400")


def test_litres_to_millilitres():
    assert normalize_quantity(Decimal("2"), "l", "ml") == Decimal("2000.000")


def test_zero_is_allowed():
    assert normalize_quantity(Decimal("0"), "g", "kg") == Decimal("0.000")


def test_incompatible_dimensions_rejected():
    with pytest.raises(QuantityNormalizationError):
        normalize_quantity(Decimal("1"), "ml", "kg")


def test_package_unit_rejected():
    with pytest.raises(QuantityNormalizationError):
        normalize_quantity(Decimal("1"), "bag", "kg")
