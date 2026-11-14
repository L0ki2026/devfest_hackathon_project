from app.schemas import BasketItem, Nutrients
from app.services.nutrition import nutrients_for_mass, resolve_mass_g, sum_nutrients


def test_protein_scaling_per_100g():
    per_100 = Nutrients(protein_g=10.0)
    scaled = nutrients_for_mass(per_100, 250.0)
    assert scaled.protein_g == 25.0


def test_missing_nutrient_stays_null_not_zero():
    per_100 = Nutrients(protein_g=10.0, fiber_g=None)
    scaled = nutrients_for_mass(per_100, 100.0)
    assert scaled.protein_g == 10.0
    assert scaled.fiber_g is None


def test_sum_incomplete_when_any_part_missing_field():
    a = Nutrients(protein_g=5.0, fiber_g=2.0)
    b = Nutrients(protein_g=3.0, fiber_g=None)
    total, incomplete = sum_nutrients([a, b])
    assert total.protein_g == 8.0
    assert total.fiber_g is None
    assert incomplete is True


def test_piece_requires_grams_per_unit():
    item = BasketItem(
        id="x",
        name="banana",
        quantity=3,
        unit="piece",
        grams_per_unit=None,
        estimated=True,
    )
    mass, warnings = resolve_mass_g(item)
    assert mass is None
    assert any("needs confirmation" in w.lower() for w in warnings)


def test_grams_canonical_mass():
    item = BasketItem(
        id="x",
        name="yogurt",
        quantity=250,
        unit="g",
        grams_per_unit=None,
        estimated=False,
    )
    mass, _ = resolve_mass_g(item)
    assert mass == 250.0