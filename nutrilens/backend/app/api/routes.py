from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import get_settings
from app.schemas import AnalyzeBasketRequest, AnalyzeBasketResponse, HealthResponse
from app.services.basket_analysis import analyze_basket
from app.services.eatclean_compat import (
    identify_from_base64,
    pantry_to_analyze,
    search_foods_eatclean,
    workout_suggestion,
)
from app.services.usda_service import UsdaServiceError


class IdentifyBody(BaseModel):
    image: str
    mime: str = "image/jpeg"


class WorkoutBody(BaseModel):
    text: str = ""
    pantry: list[str] = Field(default_factory=list)


class PantryAnalyzeBody(BaseModel):
    names: list[str] = Field(default_factory=list)

router = APIRouter(prefix="/api")


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
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "too_many_items",
                    "message": f"Maximum {settings.max_basket_items} items allowed.",
                }
            },
        )
    if not body.items:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "empty_basket",
                    "message": "At least one basket item is required.",
                }
            },
        )

    if not settings.usda_configured() and not settings.demo_mode:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "usda_unavailable",
                    "message": (
                        "FDC_API_KEY is not configured. Set FDC_API_KEY or enable DEMO_MODE=true."
                    ),
                }
            },
        )

    try:
        return await analyze_basket(body)
    except UsdaServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc


@router.get("/search")
async def search_foods(q: str = Query("", max_length=80)) -> list[dict]:
    """eatclean-compatible food search (USDA + Open Food Facts)."""
    if not q.strip():
        return []
    return await search_foods_eatclean(q)


@router.post("/identify")
async def identify_foods(body: IdentifyBody) -> dict:
    if not body.image:
        raise HTTPException(status_code=400, detail={"error": "No image received"})
    try:
        return await identify_from_base64(body.image, body.mime)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail={"error": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc


@router.post("/workout")
async def workout_api(body: WorkoutBody) -> dict:
    try:
        return await workout_suggestion(body.text, body.pantry)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc


@router.post("/pantry-analyze", response_model=AnalyzeBasketResponse)
async def pantry_analyze(body: PantryAnalyzeBody) -> AnalyzeBasketResponse:
    """Analyze pantry item names as a 100 g grocery basket (NutriLens)."""
    settings = get_settings()
    if not body.names:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "empty_pantry", "message": "No pantry names provided."}},
        )
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
    data = await pantry_to_analyze(body.names)
    return AnalyzeBasketResponse(**data)