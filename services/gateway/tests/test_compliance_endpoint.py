"""Tests for GET /api/compliance/health endpoint."""

from fastapi.testclient import TestClient
from ubunturemit_gateway.app import create_app

client = TestClient(create_app())


def test_compliance_health() -> None:
    resp = client.get("/api/compliance/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "OPERATIONAL"
    assert len(data["rules_enforced"]) >= 5
    assert "UN" in data["sanctions_list_status"]
