def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_metrics_exposed(client):
    assert "fip_http_requests_total" in client.get("/metrics").text


def test_auth_required(client):
    assert client.get("/api/v1/dashboard").status_code == 401


def test_bad_token(client):
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_login_and_duplicate(client, auth):
    assert client.post("/api/v1/auth/register", json={"email": "trader@example.com", "password": "s3cure-pass"}).status_code == 409
    r = client.post("/api/v1/auth/login", data={"username": "trader@example.com", "password": "s3cure-pass"})
    assert r.status_code == 200 and r.json()["access_token"]
    assert client.post("/api/v1/auth/login", data={"username": "trader@example.com", "password": "wrong"}).status_code == 401


def test_analysis_report_shape(client, auth):
    r = client.get("/api/v1/analysis/AAPL", headers=auth)
    assert r.status_code == 200
    j = r.json()
    assert set(j["modules"]) == {"macro", "fundamental", "institutional", "technical", "sentiment", "intermarket"}
    assert -100 <= j["decision"]["composite"] <= 100 and 0 <= j["decision"]["confidence"] <= 1
    assert j["thesis"] and j["disclaimer"]
    assert "scenarios" in j["modules"]["fundamental"]["details"]


def test_crypto_fundamental_unavailable(client, auth):
    j = client.get("/api/v1/analysis/BTC-USD", headers=auth).json()
    assert j["modules"]["fundamental"]["available"] is False
    assert "fundamental" in j["decision"]["missing"]


def test_invalid_symbol(client, auth):
    assert client.get("/api/v1/analysis/bad;symbol", headers=auth).status_code == 422


def test_dashboard(client, auth):
    j = client.get("/api/v1/dashboard", headers=auth).json()
    assert j["executive_summary"] and j["rankings"]
    assert j["sectors"]["rankings"] and j["intermarket"]["regime"]


def test_macro_and_intermarket(client, auth):
    m = client.get("/api/v1/macro/dashboard", headers=auth).json()
    assert m["inflation"]["direction"] in ("Rising", "Falling", "Stable")
    assert 0 <= m["recession_probability"]["value"] <= 1
    im = client.get("/api/v1/intermarket", headers=auth).json()
    assert len(im["correlation_matrix"]["assets"]) >= 5


def test_risk_endpoint(client, auth):
    r = client.post("/api/v1/analysis/risk", headers=auth,
                    json={"symbol": "EURUSD=X", "entry": 1.10, "stop": 1.095, "targets": [1.11, 1.115]})
    assert r.status_code == 200 and r.json()["position"]["risk_cash"] == 500
    bad = client.post("/api/v1/analysis/risk", headers=auth, json={"symbol": "EURUSD=X", "entry": 1.10, "stop": 1.12, "targets": [1.11]})
    assert bad.status_code == 422


def test_journal_r_multiple_and_stats(client, auth):
    r = client.post("/api/v1/journal", headers=auth,
                    json={"symbol": "GC=F", "direction": "long", "entry": 2000, "stop": 1990, "exit": 2030})
    assert r.status_code == 201 and r.json()["r_multiple"] == 3.0
    stats = client.get("/api/v1/journal", headers=auth).json()["stats"]
    assert stats["closed"] >= 1 and stats["win_rate"] == 1.0


def test_alerts_trigger(client, auth):
    client.post("/api/v1/alerts", headers=auth, json={"symbol": "AAPL", "condition": "above", "level": 0.01})
    alerts = client.get("/api/v1/alerts", headers=auth).json()
    assert any(a["triggered_at"] for a in alerts)


def test_watchlist_isolation(client, auth):
    other = client.post("/api/v1/auth/register", json={"email": "other@example.com", "password": "another-pass"}).json()
    oh = {"Authorization": f"Bearer {other['access_token']}"}
    mine = client.get("/api/v1/watchlists", headers=auth).json()[0]
    assert client.put(f"/api/v1/watchlists/{mine['id']}", headers=oh, json={"name": "x", "symbols": []}).status_code == 404
