"""Tests for GET /api/wallet and GET /api/session endpoints."""

from fastapi.testclient import TestClient
from ubunturemit_gateway.app import create_app

client = TestClient(create_app())


def test_wallet_overview() -> None:
    resp = client.get("/api/wallet")
    assert resp.status_code == 200
    data = resp.json()
    assert "accounts" in data
    assert len(data["accounts"]) >= 3


def test_session() -> None:
    resp = client.get("/api/session")
    assert resp.status_code == 200
    data = resp.json()
    assert data["institution_id"] == "INST-ZA-001"
    assert data["status"] == "ACTIVE_PARTICIPANT"
