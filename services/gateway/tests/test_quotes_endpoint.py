"""Tests for GET /api/fx/quote endpoint."""

from fastapi.testclient import TestClient
from ubunturemit_gateway.app import create_app

client = TestClient(create_app())


def test_get_quote_success() -> None:
    resp = client.get("/api/fx/quote?source=ZAR&target=GHS&amount=500000")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_currency"] == "ZAR"
    assert data["target_currency"] == "GHS"
    assert data["send_amount_minor_units"] == 500000
    assert data["recipient_receives_minor_units"] == 425000
    assert "PAPSS" in data["available_rails"]
    assert "RIPPLE" in data["available_rails"]


def test_get_quote_unsupported_corridor() -> None:
    resp = client.get("/api/fx/quote?source=USD&target=KES&amount=10000")
    assert resp.status_code == 404


def test_get_quote_invalid_currency() -> None:
    resp = client.get("/api/fx/quote?source=ZAR&target=XYZ&amount=10000")
    assert resp.status_code == 400
