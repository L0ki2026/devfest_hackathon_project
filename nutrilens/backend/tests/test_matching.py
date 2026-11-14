from app.services.matching import FoodCandidate, normalize_name, pick_best_candidate, score_match


def test_normalize_name():
    assert normalize_name("  Bananas, raw! ") == "bananas raw"


def test_prefers_foundation_over_branded():
    foundation = score_match("banana", "Bananas, raw", "Foundation")
    branded = score_match("banana", "Banana Chips Brand X", "Branded")
    assert foundation >= branded


def test_pick_best_low_confidence_needs_confirmation():
    cands = [
        FoodCandidate(fdc_id=1, description="Unknown food", data_type="Branded", score=0.2)
    ]
    best, needs = pick_best_candidate("banana", cands)
    assert best is not None
    assert needs is True