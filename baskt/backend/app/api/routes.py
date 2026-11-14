from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.config import get_settings
from app.schemas import (
    AnalyzeBasketRequest,
    AnalyzeBasketResponse,
    HealthResponse,
    PantryInsightsResponse,
    PantryItem,
    UserPreferences,
    WorkoutInput,
)
from app.services.basket_analysis import analyze_basket
from app.services.baskt_compat import (
    identify_from_base64,
    search_foods_baskt,
)
from app.services.meal_planner import parse_workout_text, post_workout_meal
from app.services.pantry_insights import (
    nutrient_bars,
    pairing_tips,
    quality_report,
    relative_gaps,
)
from app.services.recommendation import recommend_additions
from app.services.usda_service import UsdaServiceError


class IdentifyBody(BaseModel):
    image: str
    mime: str = "image/jpeg"


class PantryBody(BaseModel):
    items: list[PantryItem] = Field(default_factory=list)
    preferences: UserPreferences = Field(default_factory=UserPreferences)


class RecommendBody(BaseModel):
    items: list[PantryItem]
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    focus_nutrients: list[str] = Field(default_factory=list)


class PostWorkoutBody(BaseModel):
    workout_text: str = ""
    workout: WorkoutInput | None = None
    items: list[PantryItem]
    preferences: UserPreferences = Field(default_factory=UserPreferences)


router = APIRouter(prefix="/api")


def _require_usda(settings) -> None:
    if not settings.usda_configured() and not settings.demo_mode:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "usda_unavailable",
                    "message": "Set FDC_API_KEY or DEMO_MODE=true.",
                }
            },
        )


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        demo_mode=settings.demo_mode,
        gemini_configured=settings.gemini_configured(),
        usda_configured=settings.usda_configured(),
    )


@router.post("/analyze-basket", response_model=AnalyzeBasketResponse)
async def analyze_basket_endpoint(body: AnalyzeBasketRequest) -> AnalyzeBasketResponse:
    settings = get_settings()
    if len(body.items) > settings.max_basket_items:
        raise HTTPException(status_code=400, detail={"error": {"code": "too_many_items", "message": "Too many items."}})
    if not body.items:
        raise HTTPException(status_code=422, detail={"error": {"code": "empty_basket", "message": "Empty basket."}})
    _require_usda(settings)
    try:
        return await analyze_basket(body)
    except UsdaServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc


@router.post("/pantry-insights", response_model=PantryInsightsResponse)
async def pantry_insights(body: PantryBody) -> PantryInsightsResponse:
    settings = get_settings()
    _require_usda(settings)
    if not body.items:
        raise HTTPException(status_code=422, detail={"error": {"code": "empty_pantry", "message": "Pantry is empty."}})
    req = AnalyzeBasketRequest(
        items=[BasketItem_from_pantry(i) for i in body.items],
        preferences=body.preferences,
    )
    analysis = await analyze_basket(req)
    return PantryInsightsResponse(
        analysis=analysis,
        bars=nutrient_bars(analysis.totals),
        gaps=relative_gaps(analysis.totals),
        quality=quality_report(body.items),
        pairings=pairing_tips(analysis),
    )


def BasketItem_from_pantry(p: PantryItem):
    from app.schemas import BasketItem

    return BasketItem(
        id=p.id,
        name=p.name,
        quantity=p.quantity,
        unit=p.unit,
        grams_per_unit=p.grams_per_unit,
        estimated=p.estimated,
    )


@router.get("/search")
async def search_foods(q: str = Query("", max_length=80)) -> list[dict]:
    if not q.strip():
        return []
    return await search_foods_baskt(q)


@router.post("/identify")
async def identify_foods(body: IdentifyBody) -> dict:
    if not body.image:
        raise HTTPException(status_code=400, detail={"error": "No image received"})
    try:
        return await identify_from_base64(body.image, body.mime)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail={"error": str(exc)}) from exc


@router.post("/parse-groceries")
async def parse_groceries(file: UploadFile = File(...)) -> dict:
    settings = get_settings()
    if not settings.gemini_configured():
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "gemini_unavailable", "message": "GEMINI_API_KEY required."}},
        )
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail={"error": {"code": "file_too_large", "message": "Max 10MB."}})
    mime = file.content_type or "image/jpeg"
    if mime not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail={"error": {"code": "invalid_type", "message": "JPEG/PNG/WebP only."}})
    import base64

    from app.services.gemini_service import parse_groceries_from_image

    try:
        return await parse_groceries_from_image(base64.b64encode(content).decode(), mime)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc


@router.post("/recommend-additions")
async def recommend_additions_endpoint(body: RecommendBody) -> dict:
    _require_usda(get_settings())
    if not body.items:
        raise HTTPException(status_code=422, detail={"error": "empty_pantry"})
    items = [BasketItem_from_pantry(i) for i in body.items]
    return await recommend_additions(items, body.preferences, body.focus_nutrients or None)


@router.post("/post-workout-meal")
async def post_workout_endpoint(body: PostWorkoutBody) -> dict:
    _require_usda(get_settings())
    if not body.items:
        raise HTTPException(status_code=422, detail={"error": "empty_pantry"})
    workout = body.workout or parse_workout_text(body.workout_text or "general 30 min")
    items = [BasketItem_from_pantry(i) for i in body.items]
    return await post_workout_meal(workout, items, body.preferences, body.workout_text)


# Legacy routes
class PantryAnalyzeBody(BaseModel):
    names: list[str] = Field(default_factory=list)


@router.post("/pantry-analyze", response_model=AnalyzeBasketResponse)
async def pantry_analyze(body: PantryAnalyzeBody) -> AnalyzeBasketResponse:
    _require_usda(get_settings())
    items = [
        PantryItem(id=f"p{i}", name=n, quantity=100, unit="g", estimated=True)
        for i, n in enumerate(body.names)
    ]
    return (await pantry_insights(PantryBody(items=items))).analysis