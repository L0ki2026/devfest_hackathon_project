"""End-to-end grocery basket nutrition analysis."""

from app.schemas import (
    AnalyzeBasketRequest,
    AnalyzeBasketResponse,
    AnalyzedBasketItem,
    BasketItem,
    MatchStatus,
    Nutrients,
)
from app.services.matching import pick_best_candidate
from app.services.nutrition import nutrients_for_mass, resolve_mass_g, sum_nutrients
from app.services.usda_service import UsdaService, UsdaServiceError, get_usda_service


async def analyze_basket(
    request: AnalyzeBasketRequest,
    usda: UsdaService | None = None,
) -> AnalyzeBasketResponse:
    usda = usda or get_usda_service()
    warnings: list[str] = []
    unmatched: list[str] = []
    analyzed: list[AnalyzedBasketItem] = []
    nutrient_parts: list[Nutrients] = []

    if usda.use_demo():
        warnings.append(
            "Using offline demo nutrient dataset (source: demo); values are approximate."
        )

    for item in request.items:
        result = await _analyze_item(item, usda)
        analyzed.append(result)
        for w in result.warnings:
            warnings.append(w)
        if result.match_status == MatchStatus.unmatched:
            unmatched.append(item.name)
        elif result.nutrients and result.mass_g is not None:
            nutrient_parts.append(result.nutrients)

    totals, incomplete = sum_nutrients(nutrient_parts)
    if incomplete:
        warnings.append(
            "Some nutrients are incomplete in totals because one or more items lack data for those fields."
        )

    return AnalyzeBasketResponse(
        items=analyzed,
        totals=totals,
        warnings=warnings,
        unmatched_items=unmatched,
        data_source=usda.data_source,
    )


async def _analyze_item(item: BasketItem, usda: UsdaService) -> AnalyzedBasketItem:
    item_warnings: list[str] = []

    if item.quantity is not None and item.quantity <= 0:
        item_warnings.append(f"{item.name}: quantity must be positive.")
        return AnalyzedBasketItem(
            id=item.id,
            input_name=item.name,
            match_status=MatchStatus.unmatched,
            warnings=item_warnings,
        )

    try:
        search_results = await usda.search_foods(item.name)
    except UsdaServiceError as exc:
        item_warnings.append(exc.message)
        return AnalyzedBasketItem(
            id=item.id,
            input_name=item.name,
            match_status=MatchStatus.unmatched,
            warnings=item_warnings,
        )

    candidates = usda.build_candidates(item.name, search_results)
    best, needs_confirmation = pick_best_candidate(item.name, candidates)

    if best is None:
        item_warnings.append(f"No USDA match found for '{item.name}'.")
        return AnalyzedBasketItem(
            id=item.id,
            input_name=item.name,
            match_status=MatchStatus.unmatched,
            warnings=item_warnings,
        )

    try:
        detail = await usda.get_food_detail(best.fdc_id)
    except UsdaServiceError as exc:
        item_warnings.append(exc.message)
        return AnalyzedBasketItem(
            id=item.id,
            input_name=item.name,
            matched_name=best.description,
            fdc_id=best.fdc_id,
            match_status=MatchStatus.needs_confirmation,
            match_confidence=round(best.score, 2),
            warnings=item_warnings,
        )

    default_gpp = usda.default_grams_per_piece(detail)
    mass_g, mass_warnings = resolve_mass_g(item, default_grams_per_piece=default_gpp)
    item_warnings.extend(mass_warnings)

    status = MatchStatus.matched
    if needs_confirmation or mass_g is None:
        status = MatchStatus.needs_confirmation
    if mass_g is None:
        return AnalyzedBasketItem(
            id=item.id,
            input_name=item.name,
            matched_name=best.description,
            fdc_id=best.fdc_id,
            match_status=status,
            match_confidence=round(best.score, 2),
            mass_g=None,
            nutrients=Nutrients(),
            warnings=item_warnings,
        )

    per_100 = usda.nutrients_from_detail(detail)
    scaled = nutrients_for_mass(per_100, mass_g)

    return AnalyzedBasketItem(
        id=item.id,
        input_name=item.name,
        matched_name=best.description,
        fdc_id=best.fdc_id,
        match_status=status,
        match_confidence=round(best.score, 2),
        mass_g=round(mass_g, 2),
        nutrients=scaled,
        warnings=item_warnings,
    )