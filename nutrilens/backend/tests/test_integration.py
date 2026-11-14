"""Integration-style flow: manual basket -> nutrition (stubbed demo USDA)."""


def test_manual_basket_nutrition_contract(client):
    basket = {
        "items": [
            {
                "id": "item_1",
                "name": "oats",
                "quantity": 200,
                "unit": "g",
                "grams_per_unit": None,
                "estimated": False,
            },
            {
                "id": "item_2",
                "name": "spinach",
                "quantity": 100,
                "unit": "g",
                "grams_per_unit": None,
                "estimated": False,
            },
        ],
        "preferences": {
            "diet": "vegetarian",
            "allergens": ["peanuts"],
            "goal": "general_wellness",
            "servings": 1,
            "budget_usd": None,
        },
    }
    resp = client.post("/api/analyze-basket", json=basket)
    assert resp.status_code == 200
    body = resp.json()

    required_top = {"items", "totals", "warnings", "unmatched_items", "disclaimer"}
    assert required_top <= set(body.keys())

    item = body["items"][0]
    for field in (
        "id",
        "input_name",
        "matched_name",
        "fdc_id",
        "match_status",
        "match_confidence",
        "mass_g",
        "nutrients",
    ):
        assert field in item

    nutrients = item["nutrients"]
    for nfield in (
        "calories_kcal",
        "protein_g",
        "carbs_g",
        "fat_g",
        "fiber_g",
        "calcium_mg",
        "iron_mg",
        "potassium_mg",
        "vitamin_c_mg",
    ):
        assert nfield in nutrients

    # 200g oats @ ~16.9g protein/100g -> ~33.8g
    oats = next(i for i in body["items"] if "oat" in i["input_name"].lower())
    assert oats["nutrients"]["protein_g"] is not None
    assert oats["nutrients"]["protein_g"] > 30