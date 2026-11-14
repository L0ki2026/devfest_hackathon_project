def test_pantry_insights(client):
    payload = {
        "items": [
            {
                "id": "1",
                "name": "banana",
                "quantity": 2,
                "unit": "piece",
                "grams_per_unit": 118,
                "estimated": False,
                "ingredients": "",
            },
            {
                "id": "2",
                "name": "spinach",
                "quantity": 100,
                "unit": "g",
                "estimated": False,
                "ingredients": "",
            },
        ]
    }
    resp = client.post("/api/pantry-insights", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["analysis"]["totals"]["calories_kcal"] is not None
    assert isinstance(body["bars"], list)
    assert isinstance(body["gaps"], list)
    assert isinstance(body["pairings"], list)


def test_recommend_additions(client):
    resp = client.post(
        "/api/recommend-additions",
        json={
            "items": [
                {
                    "id": "1",
                    "name": "banana",
                    "quantity": 100,
                    "unit": "g",
                    "estimated": True,
                    "ingredients": "",
                }
            ],
            "focus_nutrients": ["protein_g"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["suggestions"]) >= 1


def test_post_workout_meal(client):
    resp = client.post(
        "/api/post-workout-meal",
        json={
            "workout_text": "45 minute run",
            "items": [
                {"id": "1", "name": "banana", "quantity": 2, "unit": "piece", "grams_per_unit": 118, "ingredients": ""},
                {"id": "2", "name": "oats", "quantity": 200, "unit": "g", "ingredients": ""},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["recovery_priorities"]
    assert body["disclaimer"]