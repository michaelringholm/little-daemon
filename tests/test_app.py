from pathlib import Path

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

import app as app_module
import config
from config import AppConfig


@pytest.fixture
def client(monkeypatch):
    config = AppConfig("admin", PasswordHasher().hash("correct"), "test-secret")

    async def fake_public_ip(_: str) -> str:
        return "203.0.113.10"

    monkeypatch.setattr(app_module, "public_ip", fake_public_ip)
    return TestClient(app_module.create_app(config))


def login(client: TestClient):
    return client.post("/login", data={"username": "admin", "password": "correct"}, follow_redirects=False)


def test_health_is_public_and_minimal(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_dashboard_and_status_require_login(client):
    assert client.get("/", follow_redirects=False).status_code == 303
    assert client.get("/api/status").status_code == 401

    response = login(client)
    assert response.status_code == 303
    assert "little_daemon_session" in response.headers["set-cookie"]
    assert client.get("/").status_code == 200
    status = client.get("/api/status")
    assert status.status_code == 200
    assert status.json()["public_ip"] == "203.0.113.10"


def test_bad_password_does_not_create_session(client):
    response = client.post(
        "/login", data={"username": "admin", "password": "wrong"}, follow_redirects=False
    )
    assert response.status_code == 401
    assert "little_daemon_session" not in response.cookies


def test_session_cookie_is_http_only_and_strict(client):
    response = login(client)
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie


def test_status_does_not_expose_secrets(client):
    login(client)
    body = client.get("/api/status").text
    assert "test-secret" not in body


def test_allowlisted_actions_require_login_and_execute(client):
    assert client.get("/api/actions").status_code == 401
    login(client)
    actions = client.get("/api/actions").json()
    assert {action["id"] for action in actions} == {
        "machine_info",
        "local_ip",
        "public_ip",
        "disk_free",
        "memory",
        "uptime",
        "network_config",
        "running_processes",
        "listening_ports",
        "restart_pc",
        "shutdown_pc",
    }
    result = client.post("/api/actions/machine_info")
    assert result.status_code == 200
    assert result.json()["ok"] is True
    assert "hostname=" in result.json()["output"]


def test_unknown_action_is_rejected(client):
    login(client)
    response = client.post("/api/actions/not-configured")
    assert response.status_code == 404


def test_local_env_loader_does_not_override_environment(monkeypatch):
    env_file = Path(__file__).with_name(".env.test")
    try:
        env_file.write_text("LD_TEST=value\nLD_EXIST=file-value\n", encoding="utf-8")
        monkeypatch.delenv("LD_TEST", raising=False)
        monkeypatch.setenv("LD_EXIST", "environment-value")

        config._load_local_env(env_file)

        assert config.os.environ["LD_TEST"] == "value"
        assert config.os.environ["LD_EXIST"] == "environment-value"
    finally:
        env_file.unlink(missing_ok=True)
