def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "baskt-backend"
    assert "gemini_configured" in data
    assert "usda_configured" in data
    assert data["demo_mode"] is True