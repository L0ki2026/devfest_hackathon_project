from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


ACCEPTED_UNITS = frozenset({"g", "kg", "oz", "lb", "piece", "cup", "ml", "l"})


class BasketItem(BaseModel):
    id: str
    name: str
    quantity: float | None = None
    unit: str
    grams_per_unit: float | None = None
    estimated: bool = False

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, v: str) -> str:
        if v not in ACCEPTED_UNITS:
            raise ValueError(f"unit must be one of {sorted(ACCEPTED_UNITS)}")
        return v


class WorkoutInput(BaseModel):
    type: str
    duration_minutes: float
    intensity: Literal["low", "moderate", "high", "unknown"] = "unknown"
    active_calories_kcal: float | None = None


class UserPreferences(BaseModel):
    diet: str = "general"
    allergens: list[str] = Field(default_factory=list)
    goal: Literal[
        "general_wellness",
        "muscle_gain",
        "endurance_recovery",
        "weight_management",
    ] = "general_wellness"
    servings: int = 1
    budget_usd: float | None = None


class Nutrients(BaseModel):
    calories_kcal: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    calcium_mg: float | None = None
    iron_mg: float | None = None
    potassium_mg: float | None = None
    vitamin_c_mg: float | None = None


class MatchStatus(str, Enum):
    matched = "matched"
    needs_confirmation = "needs_confirmation"
    unmatched = "unmatched"


class AnalyzedBasketItem(BaseModel):
    id: str
    input_name: str
    matched_name: str | None = None
    fdc_id: int | None = None
    match_status: MatchStatus
    match_confidence: float | None = None
    mass_g: float | None = None
    nutrients: Nutrients = Field(default_factory=Nutrients)
    warnings: list[str] = Field(default_factory=list)


class AnalyzeBasketRequest(BaseModel):
    items: list[BasketItem]
    preferences: UserPreferences = Field(default_factory=UserPreferences)


class AnalyzeBasketResponse(BaseModel):
    items: list[AnalyzedBasketItem]
    totals: Nutrients
    warnings: list[str]
    unmatched_items: list[str]
    disclaimer: str = (
        "Estimated nutrients available in this grocery basket, not nutrients consumed."
    )
    data_source: Literal["usda", "demo"] | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "nutrilens-backend"
    demo_mode: bool = False
    gemini_configured: bool = False
    usda_configured: bool = False


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody