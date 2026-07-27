from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

PRECISION = Decimal("0.001")

UNIT_ALIASES = {
    "kilogram": "kg", "kilograms": "kg", "kgs": "kg",
    "gram": "g", "grams": "g", "gm": "g", "gms": "g",
    "milligram": "mg", "milligrams": "mg", "mgs": "mg",
    "litre": "l", "litres": "l", "liter": "l", "liters": "l",
    "ltr": "l", "ltrs": "l",
    "millilitre": "ml", "millilitres": "ml",
    "milliliter": "ml", "milliliters": "ml",
}

WEIGHT_TO_MG = {
    "kg": Decimal("1000000"),
    "g": Decimal("1000"),
    "mg": Decimal("1"),
}

VOLUME_TO_ML = {
    "l": Decimal("1000"),
    "ml": Decimal("1"),
}


class QuantityNormalizationError(ValueError):
    pass


def canonical_unit(unit: str) -> str:
    if not unit or not unit.strip():
        raise QuantityNormalizationError("Unit is required.")
    value = unit.strip().lower()
    return UNIT_ALIASES.get(value, value)


def unit_dimension(unit: str) -> str | None:
    normalized = canonical_unit(unit)
    if normalized in WEIGHT_TO_MG:
        return "WEIGHT"
    if normalized in VOLUME_TO_ML:
        return "VOLUME"
    return None


def normalize_quantity(quantity: Decimal, supplied_unit: str, base_unit: str) -> Decimal:
    try:
        value = Decimal(str(quantity))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise QuantityNormalizationError("Quantity must be a valid decimal number.") from exc

    source = canonical_unit(supplied_unit)
    target = canonical_unit(base_unit)

    if value < 0:
        raise QuantityNormalizationError("Quantity cannot be negative.")

    if source == target:
        normalized = value
    elif source in WEIGHT_TO_MG and target in WEIGHT_TO_MG:
        normalized = value * WEIGHT_TO_MG[source] / WEIGHT_TO_MG[target]
    elif source in VOLUME_TO_ML and target in VOLUME_TO_ML:
        normalized = value * VOLUME_TO_ML[source] / VOLUME_TO_ML[target]
    else:
        raise QuantityNormalizationError(
            f"Incompatible or unsupported unit conversion: {supplied_unit} to {base_unit}."
        )

    normalized = normalized.quantize(PRECISION, rounding=ROUND_HALF_UP)
    if value > 0 and normalized == 0:
        raise QuantityNormalizationError(
            "Quantity is below the supported precision of 0.001 base units."
        )
    return normalized
