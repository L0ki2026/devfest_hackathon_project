"""Meal planning and post-workout meals from confirmed inventory."""

from __future__ import annotations

import re

from app.schemas import (
    AnalyzeBasketRequest,
    BasketItem,
    Nutrients,
    UserPreferences,
    WorkoutInput,
)
from app.services.basket_analysis import analyze_basket
from app.services.gemini_service import suggest_workout_meals
from app.services.nutrition import sum_nutrients


def _inventory_names(items: list[BasketItem]) -> set[str]:
    return {i.name.lower().strip() for i in items}


def _filter_pantry_only(names: list[str], inventory: set[str]) -> list[str]:
    return [n for n in names if any(n.lower() in inv or inv in n.lower() for inv in inventory)]


def recovery_priorities(workout: WorkoutInput, goal: str) -> list[str]:
    prio = ["fluids"]
    t = workout.type.lower()
    if workout.intensity in ("moderate", "high") or workout.duration_minutes >= 45:
        prio.extend(["carbs", "protein"])
    else:
        prio.append("balanced meal")
    if "run" in t or "cycl" in t or "swim" in t:
        if "carbs" not in prio:
            prio.append("carbs")
    if goal == "muscle_gain" or "strength" in t or "lift" in t:
        if "protein" not in prio:
            prio.append("protein")
    return list(dict.fromkeys(prio))


async def _meal_nutrition(ingredients: list[BasketItem]) -> Nutrients:
    if not ingredients:
        return Nutrients()
    analysis = await analyze_basket(AnalyzeBasketRequest(items=ingredients))
    return analysis.totals


async def plan_meal_from_inventory(
    items: list[BasketItem],
    preferences: UserPreferences,
    meal_type: str,
    focus_nutrients: list[str] | None = None,
) -> dict:
    if not items:
        return {"meals": [], "warnings": ["Pantry is empty."]}

    inv = _inventory_names(items)
    # Deterministic template using first matching pantry items by keyword.
    templates = {
        "breakfast": (["oats", "banana", "yogurt"], "Oat bowl with fruit and yogurt"),
        "lunch": (["lentils", "spinach", "rice"], "Lentils with greens"),
        "dinner": (["tofu", "broccoli", "rice"], "Tofu and broccoli plate"),
        "snack": (["banana", "yogurt"], "Fruit and yogurt snack"),
    }
    keys, title = templates.get(meal_type, templates["lunch"])
    chosen: list[BasketItem] = []
    for key in keys:
        hit = next((i for i in items if key in i.name.lower()), None)
        if hit:
            portion = BasketItem(
                id=f"meal_{hit.id}",
                name=hit.name,
                quantity=hit.quantity or 100,
                unit=hit.unit,
                grams_per_unit=hit.grams_per_unit,
                estimated=hit.estimated,
            )
            if portion.quantity and portion.quantity > 0:
                chosen.append(portion)

    if not chosen:
        chosen = items[:2]

    nutrients = await _meal_nutrition(chosen)
    return {
        "meals": [
            {
                "title": title,
                "ingredients": [
                    {"name": c.name, "amount": c.quantity, "unit": c.unit} for c in chosen
                ],
                "instructions": [
                    "Combine available pantry items.",
                    "Adjust portions to match what you have on hand.",
                ],
                "nutrition": nutrients.model_dump(),
                "why_this_meal": (
                    f"Built only from your pantry for {meal_type}. "
                    "General wellness suggestion—not a medical meal plan."
                ),
                "missing_ingredients": [],
                "warnings": [],
            }
        ]
    }


async def post_workout_meal(
    workout: WorkoutInput,
    items: list[BasketItem],
    preferences: UserPreferences,
    workout_text: str | None = None,
) -> dict:
    inventory = _inventory_names(items)
    pantry_names = [i.name for i in items]

    pre: list[str] = []
    post: list[str] = []
    if workout_text:
        try:
            gem = await suggest_workout_meals(workout_text[:300], pantry_names)
            pre = _filter_pantry_only(gem.get("pre", []), inventory)
            post = _filter_pantry_only(gem.get("post", []), inventory)
        except Exception:
            pass

    prios = recovery_priorities(workout, preferences.goal)
    meals = []

    async def build_meal(title: str, names: list[str]) -> dict | None:
        picked: list[BasketItem] = []
        for name in names[:3]:
            hit = next((i for i in items if name.lower() in i.name.lower()), None)
            if hit:
                picked.append(hit)
        if not picked:
            return None
        nutrients = await _meal_nutrition(picked)
        return {
            "title": title,
            "ingredients": [
                {"name": c.name, "amount": c.quantity, "unit": c.unit} for c in picked
            ],
            "instructions": ["Prepare using only items from your pantry."],
            "nutrition": nutrients.model_dump(),
            "why_this_meal": (
                "Recovery-oriented combo from inventory. General wellness only."
            ),
            "missing_ingredients": [n for n in names if not any(n.lower() in p.name.lower() for p in picked)],
            "warnings": [],
        }

    pre_meal = await build_meal("Pre-workout (from pantry)", pre)
    post_meal = await build_meal("Post-workout (from pantry)", post)
    if pre_meal:
        meals.append(pre_meal)
    if post_meal:
        meals.append(post_meal)

    if not meals:
        fallback = await plan_meal_from_inventory(items, preferences, "snack", [])
        meals = fallback.get("meals", [])

    summary = (
        f"{workout.type} · {workout.duration_minutes} min · {workout.intensity} intensity"
    )
    return {
        "workout_summary": summary,
        "recovery_priorities": prios,
        "meals": meals,
        "assumptions": [
            "Meal suggestions use your pantry only; portions are not personalized prescriptions.",
            "Workout text parsing is approximate.",
        ],
        "disclaimer": (
            "General wellness suggestions, not medical advice. Nutrients are calculated "
            "from USDA data in Python, not estimated by Gemini."
        ),
    }


def parse_workout_text(text: str) -> WorkoutInput:
    s = text.lower()
    m = re.search(r"(\d+)\s*(hours?|hrs?|h|minutes?|mins?|m)\b", s)
    minutes = float(m.group(1)) * (60 if m and m.group(2).startswith("h") else 1) if m else 30.0
    if re.search(r"lift|strength|weight|gym|resist", s):
        wtype = "strength"
    elif re.search(r"run|cycl|bike|swim|row|cardio|hiit", s):
        wtype = "running"
    else:
        wtype = "general"
    intensity = "high" if re.search(r"hiit|sprint|hard|intense", s) else "moderate"
    return WorkoutInput(type=wtype, duration_minutes=minutes, intensity=intensity)