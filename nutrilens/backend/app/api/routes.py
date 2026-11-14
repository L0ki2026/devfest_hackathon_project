from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.schemas import AnalyzeBasketRequest, AnalyzeBasketResponse, HealthResponse
from app.services.basket_analysis import analyze_basket
from app.services.usda_service import UsdaServiceError

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