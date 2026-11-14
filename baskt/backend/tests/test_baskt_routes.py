def test_search_demo_banana(client):
    resp = client.get("/api/search", params={"q": "banana"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data
    assert any("banana" in x["name"].lower() for x in data)


def test_workout_fallback(client):
    resp = client.post(
        "/api/workout",
        json={"text": "45 minute run", "pantry": ["banana", "oats"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] in ("strength", "endurance", "light")
    assert isinstance(body["pre"], list)
    assert isinstance(body["post"], list)


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