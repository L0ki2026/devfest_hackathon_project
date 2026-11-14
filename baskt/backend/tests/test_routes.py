import os

from app.config import get_settings


def test_analyze_basket_demo_e2e(client):
    payload = {
        "items": [
            {
                "id": "item_1",
                "name": "banana",
                "quantity": 3,
                "unit": "piece",
                "grams_per_unit": 118,
                "estimated": True,
            },
            {
                "id": "item_2",
                "name": "plain greek yogurt",
                "quantity": 500,
                "unit": "g",
                "grams_per_unit": None,
                "estimated": False,
            },
        ],
        "preferences": {
            "diet": "vegetarian",
            "allergens": [],
            "goal": "general_wellness",
            "servings": 1,
            "budget_usd": None,
        },
    }
    resp = client.post("/api/analyze-basket", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["disclaimer"]
    assert data["data_source"] == "demo"
    assert data["items"][0]["match_status"] in ("matched", "needs_confirmation")
    assert data["items"][0]["nutrients"]["calories_kcal"] is not None
    assert data["totals"]["calories_kcal"] is not None


def test_analyze_basket_empty_422(client):
    resp = client.post("/api/analyze-basket", json={"items": []})
    assert resp.status_code == 422


def test_analyze_basket_usda_unconfigured_no_demo(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.delenv("FDC_API_KEY", raising=False)
    get_settings.cache_clear()

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        resp = c.post(
            "/api/analyze-basket",
            json={
                "items": [
                    {
                        "id": "1",
                        "name": "banana",
                        "quantity": 1,
                        "unit": "g",
                        "grams_per_unit": None,
                        "estimated": False,
                    }
                ]
            },
        )
        assert resp.status_code == 503
        assert resp.json()["detail"]["error"]["code"] == "usda_unavailable"

    os.environ["DEMO_MODE"] = "true"
    get_settings.cache_clear()


def test_invalid_unit_422(client):
    resp = client.post(
        "/api/analyze-basket",
        json={
            "items": [
                {
                    "id": "1",
                    "name": "banana",
                    "quantity": 1,
                    "unit": "bunch",
                    "grams_per_unit": None,
                    "estimated": False,
                }
            ]
        },
    )
    assert resp.status_code == 422