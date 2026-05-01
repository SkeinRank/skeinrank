def test_healthz_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("ok", "degraded")
    assert data["service"]["name"] == "skeinrank-server"
    assert "elasticsearch" in data and "ok" in data["elasticsearch"]


def test_diagnostics_shape(client):
    r = client.get("/diagnostics")
    assert r.status_code == 200
    data = r.json()
    assert "config" in data
    assert "elasticsearch" in data
    assert "core" in data
