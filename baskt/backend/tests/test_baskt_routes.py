def test_search_demo_banana(client):
    resp = client.get("/api/search", params={"q": "banana"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data
    assert any("banana" in x["name"].lower() for x in data)


def test_post_workout_route(client):
    resp = client.post(
        "/api/post-workout-meal",
        json={
            "workout_text": "45 minute run",
            "items": [
                {"id": "1", "name": "banana", "quantity": 100, "unit": "g", "ingredients": ""},
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["meals"] is not None


def test_pantry_analyze(client):
    resp = client.post(
        "/api/pantry-analyze",
        json={"names": ["banana", "oats"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totals"]["calories_kcal"] is not None
    assert len(body["items"]) == 2


def test_serve_frontend(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Baskt" in resp.text