import pytest
from fastapi.testclient import TestClient

from plant_memory.config import Settings
from plant_memory.main import app
from plant_memory.routers import auth


@pytest.mark.parametrize("environment,backend", [("production", "dev"), ("production", "session"), ("development", "session")])
def test_dev_token_disabled(environment, backend, monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(_env_file=None, environment=environment, auth_backend=backend))
    response = TestClient(app).post("/v1/auth/dev-token", json={"email": "test@example.com"})
    assert response.status_code == 404


@pytest.mark.parametrize("provided", [None, "incorrect"])
def test_session_exchange_requires_server_credential(provided, monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(_env_file=None, session_exchange_secret="s" * 40))
    response = TestClient(app).post("/v1/auth/session", json={"subject": "user_test", "email": "test@example.com", "name": "Test"},
                                   headers={"X-Session-Exchange": provided} if provided else {})
    assert response.status_code == 401


def test_production_signer_must_be_configured(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(_env_file=None, environment="production", session_exchange_secret="s" * 40))
    response = TestClient(app).post("/v1/auth/session", json={"subject": "user_test", "email": "test@example.com", "name": "Test"},
                                   headers={"X-Session-Exchange": "s" * 40})
    assert response.status_code == 503
