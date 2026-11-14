"""Inventory-driven quality, gaps, and pairings from analyzed pantry (not daily intake)."""

from __future__ import annotations

import re

from app.schemas import AnalyzeBasketResponse, BasketItem, Nutrients

# Generic reference amounts for relative basket comparison only (not medical targets).
REFERENCE = {
    "calories_kcal": 2000.0,
    "protein_g": 60.0,
    "carbs_g": 250.0,
    "fat_g": 65.0,
    "fiber_g": 28.0,
    "iron_mg": 18.0,
    "vitamin_c_mg": 90.0,
    "calcium_mg": 1000.0,
    "potassium_mg": 3500.0,
}

ADDITIVE_PATTERNS = [
    ("red 40", "Red 40"),
    ("yellow 5", "Yellow 5"),
    ("yellow 6", "Yellow 6"),
    ("blue 1", "Blue 1"),
    ("high fructose corn syrup", "High fructose corn syrup"),
    ("bht", "BHT"),
    ("artificial flavor", "Artificial flavor"),
    ("sodium nitrite", "Sodium nitrite"),
]

GAP_NOTES = (
    "Low relative representation in your current pantry basket—not a diagnosis "
    "of deficiency or daily intake."
)


def _flags_from_ingredients(ingredients: str) -> list[str]:
    ing = (ingredients or "").lower()
    return [label for key, label in ADDITIVE_PATTERNS if key in ing]


def relative_gaps(totals: Nutrients, threshold: float = 0.35) -> list[dict]:
    gaps: list[dict] = []
    fields = {
        "protein_g": "Protein",
        "fiber_g": "Fiber",
        "iron_mg": "Iron",
        "vitamin_c_mg": "Vitamin C",
        "calcium_mg": "Calcium",
    }
    for field, label in fields.items():
        ref = REFERENCE.get(field)
        val = getattr(totals, field)
        if ref is None or ref <= 0:
            continue
        if val is None:
            gaps.append(
                {
                    "nutrient": field,
                    "label": label,
                    "pct_of_reference": None,
                    "note": GAP_NOTES,
                }
            )
            continue
        pct = val / ref
        if pct < threshold:
            gaps.append(
                {
                    "nutrient": field,
                    "label": label,
                    "pct_of_reference": round(pct * 100, 1),
                    "note": GAP_NOTES,
                }
            )
    return gaps


def nutrient_bars(totals: Nutrients) -> list[dict]:
    rows = []
    mapping = [
        ("calories_kcal", "Calories", "kcal"),
        ("protein_g", "Protein", "g"),
        ("carbs_g", "Carbs", "g"),
        ("fat_g", "Fat", "g"),
        ("fiber_g", "Fiber", "g"),
        ("iron_mg", "Iron", "mg"),
        ("vitamin_c_mg", "Vitamin C", "mg"),
        ("calcium_mg", "Calcium", "mg"),
    ]
    for field, label, unit in mapping:
        ref = REFERENCE.get(field)
        val = getattr(totals, field)
        pct = None
        if val is not None and ref:
            pct = min(100.0, round(val / ref * 100, 1))
        rows.append({"field": field, "label": label, "unit": unit, "value": val, "pct": pct})
    return rows


def quality_report(pantry: list) -> list[dict]:
    out: list[dict] = []
    for p in pantry:
        ing = getattr(p, "ingredients", None) or (p.get("ingredients") if isinstance(p, dict) else "") or ""
        name = getattr(p, "name", None) or (p.get("name") if isinstance(p, dict) else "")
        pid = getattr(p, "id", None) or (p.get("id") if isinstance(p, dict) else "")
        flags = _flags_from_ingredients(ing)
        if flags:
            out.append({"id": pid, "name": name, "ingredients": ing, "flags": flags})
    return out


def pairing_tips(analysis: AnalyzeBasketResponse) -> list[dict]:
    iron_items = []
    vc_items = []
    tannin_items = []
    for row in analysis.items:
        n = row.nutrients
        name = row.input_name or ""
        if (n.iron_mg or 0) >= 2.0:
            iron_items.append(name)
        if (n.vitamin_c_mg or 0) >= 10:
            vc_items.append(name)
        if re.search(r"coffee|\btea\b|cocoa|chocolate", name, re.I):
            tannin_items.append(name)

    tips: list[dict] = []
    if iron_items and vc_items:
        tips.append(
            {
                "level": "good",
                "text": (
                    f"Pairing note: {iron_items[0]} with vitamin C sources like "
                    f"{vc_items[0]} may help non-heme iron absorption when eaten together."
                ),
            }
        )
    elif iron_items:
        tips.append(
            {
                "level": "warn",
                "text": (
                    f"{iron_items[0]} is iron-rich in this basket. Consider adding a "
                    "vitamin C food (pepper, orange) when you cook or eat."
                ),
            }
        )
    if iron_items and tannin_items:
        tips.append(
            {
                "level": "warn",
                "text": (
                    f"{tannin_items[0]} may reduce iron uptake from {iron_items[0]} "
                    "when taken at the same time—spacing them can help."
                ),
            }
        )
    return tips