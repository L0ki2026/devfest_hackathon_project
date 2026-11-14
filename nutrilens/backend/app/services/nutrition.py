"""Deterministic mass and nutrient calculations."""

from app.schemas import BasketItem, Nutrients

MASS_UNITS_TO_GRAMS = {
    "g": 1.0,
    "kg": 1000.0,
    "oz": 28.3495,
    "lb": 453.592,
}

VOLUME_UNITS = frozenset({"cup", "ml", "l"})


def resolve_mass_g(
    item: BasketItem,
    default_grams_per_piece: float | None = None,
) -> tuple[float | None, list[str]]:
    """Return canonical mass in grams and any warnings."""
    warnings: list[str] = []

    if item.quantity is None or item.quantity <= 0:
        warnings.append(f"{item.name}: quantity missing or non-positive; cannot compute mass.")
        return None, warnings

    unit = item.unit

    if unit == "g":
        return item.quantity, warnings
    if unit == "kg":
        return item.quantity * 1000.0, warnings
    if unit == "oz":
        return item.quantity * MASS_UNITS_TO_GRAMS["oz"], warnings
    if unit == "lb":
        return item.quantity * MASS_UNITS_TO_GRAMS["lb"], warnings

    if unit == "piece":
        gpp = item.grams_per_unit or default_grams_per_piece
        if gpp is None:
            warnings.append(
                f"{item.name}: piece count without food-specific grams_per_unit; needs confirmation."
            )
            return None, warnings
        if item.estimated:
            warnings.append(f"{item.name}: piece mass is estimated; verify quantity and size.")
        return item.quantity * gpp, warnings

    if unit == "ml":
        return item.quantity, warnings  # assume water-like density when mass only path needed
    if unit == "l":
        return item.quantity * 1000.0, warnings
    if unit == "cup":
        if item.grams_per_unit is not None:
            return item.quantity * item.grams_per_unit, warnings
        warnings.append(f"{item.name}: cup measure without grams_per_unit; needs confirmation.")
        return None, warnings

    warnings.append(f"{item.name}: unsupported unit conversion.")
    return None, warnings


def nutrients_for_mass(nutrients_per_100g: Nutrients, mass_g: float) -> Nutrients:
    """Scale per-100g nutrients to the given mass; null stays null."""
    factor = mass_g / 100.0
    out: dict[str, float | None] = {}
    for field_name in Nutrients.model_fields:
        per_100 = getattr(nutrients_per_100g, field_name)
        if per_100 is None:
            out[field_name] = None
        else:
            out[field_name] = round(per_100 * factor, 2)
    return Nutrients(**out)


def sum_nutrients(parts: list[Nutrients]) -> tuple[Nutrients, bool]:
    """Sum nutrients; if any part lacks a field, total field is null (incomplete)."""
    fields = list(Nutrients.model_fields.keys())
    totals: dict[str, float | None] = {}
    incomplete = False

    for field_name in fields:
        values = [getattr(n, field_name) for n in parts]
        known = [v for v in values if v is not None]
        if not known:
            totals[field_name] = None
            continue
        if len(known) < len(values):
            incomplete = True
            totals[field_name] = None
        else:
            totals[field_name] = round(sum(known), 2)

    return Nutrients(**totals), incomplete


def dict_to_nutrients(data: dict) -> Nutrients:
    """Build Nutrients from a dict; map explicit null and omit unknown keys."""
    allowed = Nutrients.model_fields.keys()
    payload = {k: data.get(k) for k in allowed if k in data}
    return Nutrients(**payload)