"""Adapters so the baskt web UI can use Baskt backend routes."""

from __future__ import annotations

import re

from app.config import get_settings
from app.schemas import BasketItem
from app.services.basket_analysis import analyze_basket
from app.services.gemini_service import identify_foods_from_image, suggest_workout_meals
from app.services.openfoodfacts import search_open_food_facts
from app.services.usda_service import UsdaService, get_usda_service

LEGACY_NUTRIENT_NUMBERS = {
    "208": "kcal",
    "203": "p",
    "205": "c",
    "204": "f",
    "291": "fib",
    "303": "fe",
    "401": "vc",
    "301": "ca",
}


def _r1(n: float | None) -> float:
    return round((float(n or 0)) * 10) / 10


def _tannin_tag(name: str) -> str:
    return "tannin" if re.search(r"coffee|\btea\b|cocoa|chocolate", name, re.I) else ""


def _nutrient_from_legacy_array(food_nutrients: list, number: str) -> float:
    for x in food_nutrients or []:
        num = str(x.get("nutrientNumber") or x.get("nutrient", {}).get("number") or "")
        if num == number:
            return _r1(x.get("value"))
    return 0.0


def _usda_row_to_baskt(row: dict) -> dict:
    brand = row.get("brandName") or ""
    desc = row.get("description") or "Unknown food"
    name = desc + (f" ({brand})" if brand else "")
    nutrients = row.get("foodNutrients") or []
    return {
        "id": "u" + str(row.get("fdcId")),
        "name": name,
        "srv": "100 g",
        "kcal": _nutrient_from_legacy_array(nutrients, "208"),
        "p": _nutrient_from_legacy_array(nutrients, "203"),
        "c": _nutrient_from_legacy_array(nutrients, "205"),
        "f": _nutrient_from_legacy_array(nutrients, "204"),
        "fib": _nutrient_from_legacy_array(nutrients, "291"),
        "fe": _nutrient_from_legacy_array(nutrients, "303"),
        "vc": _nutrient_from_legacy_array(nutrients, "401"),
        "ca": _nutrient_from_legacy_array(nutrients, "301"),
        "ing": row.get("ingredients") or "",
        "tag": _tannin_tag(desc),
        "src": "USDA",
    }


def _demo_row_to_baskt(food: dict) -> dict:
    n = food["nutrients_per_100g"]
    return {
        "id": "d" + str(food["fdc_id"]),
        "name": food["description"],
        "srv": "100 g",
        "kcal": _r1(n.get("calories_kcal")),
        "p": _r1(n.get("protein_g")),
        "c": _r1(n.get("carbs_g")),
        "f": _r1(n.get("fat_g")),
        "fib": _r1(n.get("fiber_g")),
        "fe": _r1(n.get("iron_mg")),
        "vc": _r1(n.get("vitamin_c_mg")),
        "ca": _r1(n.get("calcium_mg")),
        "ing": "",
        "tag": _tannin_tag(food["description"]),
        "src": "Demo USDA",
    }


async def search_foods_baskt(query: str, limit: int = 5) -> list[dict]:
    q = query.strip()[:80]
    if not q:
        return []

    usda = get_usda_service()
    usda_hits: list[dict] = []

    if usda.use_demo():
        ql = q.lower()
        for food in usda._load_demo_foods():
            keys = [k.lower() for k in food.get("search_keys", [])]
            desc = food["description"].lower()
            if any(k in ql or ql in k for k in keys) or ql in desc:
                usda_hits.append(_demo_row_to_baskt(food))
            if len(usda_hits) >= limit:
                break
    else:
        rows = await usda.search_foods(q, page_size=limit)
        usda_hits = [_usda_row_to_baskt(r) for r in rows[:limit]]

    off_hits = await search_open_food_facts(q, page_size=limit)
    return usda_hits + off_hits


async def identify_from_base64(image_b64: str, mime: str) -> dict:
    settings = get_settings()
    if settings.demo_mode and not settings.gemini_configured():
        return {"items": [{"name": "banana"}, {"name": "plain greek yogurt"}]}

    if not settings.gemini_configured():
        raise ValueError("GEMINI_API_KEY is not set on the server")

    names = await identify_foods_from_image(image_b64, mime)
    return {"items": [{"name": n} for n in names]}


async def workout_suggestion(text: str, pantry: list[str]) -> dict:
    settings = get_settings()
    cleaned_text = text[:300]
    pantry_names = pantry[:40]

    if settings.gemini_configured():
        try:
            return await suggest_workout_meals(cleaned_text, pantry_names)
        except Exception:
            pass

    return _workout_fallback(cleaned_text, pantry_names)


def _workout_fallback(text: str, pantry: list[str]) -> dict:
    s = text.lower()
    m = re.search(r"(\d+)\s*(hours?|hrs?|h|minutes?|mins?|m)\b", s)
    minutes = int(m.group(1)) * (60 if m and m.group(2).startswith("h") else 1) if m else 0

    if re.search(r"lift|strength|weight|gym|resist", s):
        kind = "strength"
        pre, post = ["banana", "oats"], ["eggs", "yogurt", "banana"]
    elif re.search(r"run|cycl|bike|swim|row|cardio|hiit", s):
        kind = "endurance"
        pre = ["oats", "banana"] if minutes >= 60 else ["banana", "almonds"]
        post = ["yogurt", "banana", "oats"]
    else:
        kind = "light"
        pre, post = ["banana"], ["yogurt", "orange"]

    def pick(items: list[str]) -> list[str]:
        out: list[str] = []
        pantry_l = [p.lower() for p in pantry]
        for item in items:
            hit = next((p for p in pantry if item in p.lower()), None)
            if hit:
                out.append(hit)
            elif any(item in p for p in pantry_l):
                out.append(pantry[pantry_l.index(item)])
            else:
                out.append(item.title())
        return out[:3]

    return {"kind": kind, "min": minutes, "pre": pick(pre), "post": pick(post)}


async def pantry_to_analyze(pantry_names: list[str]) -> dict:
    """Map pantry food names to Baskt analyze-basket (100 g each)."""
    from app.schemas import AnalyzeBasketRequest

    items = [
        BasketItem(
            id=f"pantry_{i}",
            name=name,
            quantity=100,
            unit="g",
            grams_per_unit=None,
            estimated=True,
        )
        for i, name in enumerate(pantry_names[:50])
    ]
    result = await analyze_basket(AnalyzeBasketRequest(items=items))
    return result.model_dump()