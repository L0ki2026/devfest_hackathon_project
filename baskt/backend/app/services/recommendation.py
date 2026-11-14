"""Curated addition ideas ranked by focus nutrients (basket representation, not deficiency)."""

from __future__ import annotations

from app.schemas import AnalyzeBasketRequest, BasketItem, Nutrients, UserPreferences
from app.services.basket_analysis import analyze_basket
from app.services.pantry_insights import GAP_NOTES, relative_gaps

CURATED = [
    {"name": "lentils", "diet_ok": {"vegetarian", "vegan", "general"}, "allergens": []},
    {"name": "black beans", "diet_ok": {"vegetarian", "vegan", "general"}, "allergens": []},
    {"name": "spinach", "diet_ok": {"vegetarian", "vegan", "general"}, "allergens": []},
    {"name": "plain greek yogurt", "diet_ok": {"vegetarian", "general"}, "allergens": ["milk"]},
    {"name": "tofu", "diet_ok": {"vegetarian", "vegan", "general"}, "allergens": ["soy"]},
    {"name": "oats", "diet_ok": {"vegetarian", "vegan", "general"}, "allergens": []},
    {"name": "broccoli", "diet_ok": {"vegetarian", "vegan", "general"}, "allergens": []},
    {"name": "orange", "diet_ok": {"vegetarian", "vegan", "general"}, "allergens": []},
]


def _diet_ok(item: dict, diet: str) -> bool:
    d = (diet or "general").lower()
    if d in ("vegetarian", "vegan"):
        return d in item["diet_ok"] or "vegetarian" in item["diet_ok"]
    return True


def _allergen_ok(item: dict, allergens: list[str]) -> bool:
    bad = {a.lower() for a in allergens}
    for a in item.get("allergens", []):
        if a in bad:
            return False
    return True


async def recommend_additions(
    items: list[BasketItem],
    preferences: UserPreferences,
    focus_nutrients: list[str] | None = None,
) -> dict:
    analysis = await analyze_basket(AnalyzeBasketRequest(items=items, preferences=preferences))
    gaps = relative_gaps(analysis.totals)
    if not focus_nutrients:
        focus_nutrients = [g["nutrient"] for g in gaps[:3]] or ["protein_g", "fiber_g"]

    suggestions: list[dict] = []
    for cand in CURATED:
        if not _diet_ok(cand, preferences.diet):
            continue
        if not _allergen_ok(cand, preferences.allergens):
            continue
        probe = BasketItem(
            id="rec_probe",
            name=cand["name"],
            quantity=100,
            unit="g",
            estimated=True,
        )
        row = (await analyze_basket(AnalyzeBasketRequest(items=[probe]))).items[0]
        score = 0.0
        for field in focus_nutrients:
            val = getattr(row.nutrients, field, None)
            if val is not None:
                score += float(val)
        if score <= 0:
            continue
        suggestions.append(
            {
                "name": cand["name"],
                "reason": (
                    f"Adds relative {', '.join(focus_nutrients)} to your pantry basket. "
                    + GAP_NOTES
                ),
                "estimated_nutrients_per_serving": row.nutrients.model_dump(),
                "suggested_quantity": 100,
                "unit": "g",
                "evidence_source": analysis.data_source or "usda",
                "_score": score,
            }
        )

    suggestions.sort(key=lambda x: x["_score"], reverse=True)
    for s in suggestions:
        s.pop("_score", None)
    return {
        "suggestions": suggestions[:5],
        "focus_nutrients": focus_nutrients,
        "disclaimer": GAP_NOTES,
    }