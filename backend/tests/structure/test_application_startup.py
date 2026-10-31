from fastapi.testclient import TestClient

from app.application import create_app
from app.config import settings


def test_startup_compatibility_routes_and_analysis_job_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "api.db"))
    monkeypatch.setattr(settings, "paper_ledger_dir", str(tmp_path / "ledgers"))
    monkeypatch.setattr(settings, "paper_ledger_path", str(tmp_path / "ledger.json"))
    monkeypatch.setattr(settings, "trading_mode", "paper")
    monkeypatch.setattr(settings, "live_trading_enabled", False)
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "app_debug", False)
    monkeypatch.setattr(settings, "admin_username", "structural-admin")
    monkeypatch.setattr(settings, "admin_password", "structural-password")
    monkeypatch.setattr(settings, "session_secret", "structure-test-session-secret")
    monkeypatch.setattr(settings, "dhan_client_id", "")
    monkeypatch.setattr(settings, "dhan_access_token", "")
    monkeypatch.setattr(settings, "groq_api_key", "")

    async def no_network_holidays():
        return set()

    monkeypatch.setattr("app.market.nse_public.load_holidays", no_network_holidays)
    app = create_app()

    with TestClient(app) as client:
        assert client.get("/api/v1/auth/session").status_code == 401
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "structural-admin", "password": "structural-password"},
            headers={"X-Request-ID": "structure-test-request"},
        )
        assert login.status_code == 200
        assert login.headers["x-request-id"] == "structure-test-request"
        assert login.json()["user"]["role"] == "admin"
        assert client.get("/api/v1/users").status_code == 200
        paths = client.get("/openapi.json").json()["paths"]
        assert {
            "/api/v1/auth/login",
            "/api/v1/users",
            "/api/v1/automation/status",
            "/api/v1/account/funds",
            "/api/v1/screener/nifty50",
            "/api/v1/orders/intraday",
            "/api/v1/suggestions",
            "/api/v1/events",
        } <= set(paths)
        assert client.post(
            "/api/v1/orders/intraday",
            json={"symbol": "TESTCO", "side": "BUY", "quantity": 1},
        ).status_code == 403

        created = client.post(
            "/api/v1/analysis/jobs",
            json={
                "idempotency_key": "same-analysis-request",
                "request_payload": {"symbol": "TESTCO", "api_key": "never-persist"},
            },
        )
        duplicate = client.post(
            "/api/v1/analysis/jobs",
            json={"idempotency_key": "same-analysis-request", "request_payload": {"symbol": "TESTCO"}},
        )
        assert created.status_code == 202
        assert duplicate.status_code == 202
        assert created.json()["analysis_id"] == duplicate.json()["analysis_id"]
        assert created.json()["status"] == "PENDING"
        assert "never-persist" not in created.text
        job = client.get(f"/api/v1/analysis/jobs/{created.json()['analysis_id']}")
        assert job.status_code == 200
        assert job.json()["attempt_count"] == 0

        viewer = client.post(
            "/api/v1/users",
            json={"username": "structural-viewer", "password": "viewer-password", "role": "viewer"},
        )
        assert viewer.status_code == 200
        client.post("/api/v1/auth/logout")
        client.post(
            "/api/v1/auth/login",
            json={"username": "structural-viewer", "password": "viewer-password"},
        )
        assert client.get("/api/v1/users").status_code == 403
        assert client.post(
            "/api/v1/automation/enable", json={"methods": ["intraday_long"]}
        ).status_code == 403
        assert client.get(f"/api/v1/analysis/jobs/{created.json()['analysis_id']}").status_code == 404

        preflight = client.options(
            "/api/v1/auth/session",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"
