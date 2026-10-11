"""Tests for GET /api/fx/quote (T073)."""

from fastapi.testclient import TestClient
from gateway_fakes import TEST_FEE_MINOR_UNITS, configured_dependencies
from ubunturemit_gateway.app import create_app

unconfigured = TestClient(create_app())
configured = TestClient(create_app(configured_dependencies()))


def test_quote_without_a_rate_source_is_refused() -> None:
    resp = unconfigured.get("/api/fx/quote?source=ZAR&target=GHS&amount=500000")
    assert resp.status_code == 503
    assert "quote_source" in resp.json()["detail"]


def test_quote_comes_from_the_rate_source() -> None:
    resp = configured.get("/api/fx/quote?source=ZAR&target=GHS&amount=500000")
    assert resp.status_code == 200
    data = resp.json()
    assert data["send_amount_minor_units"] == 500000
    assert data["recipient_receives_minor_units"] == 425000
    assert data["exchange_rate"] == "0.8500"
    assert data["fee_minor_units"] == TEST_FEE_MINOR_UNITS


def test_quote_unsupported_corridor() -> None:
    resp = configured.get("/api/fx/quote?source=ZAR&target=KES&amount=10000")
    assert resp.status_code == 404


def test_quote_invalid_currency() -> None:
    resp = unconfigured.get("/api/fx/quote?source=ZAR&target=XYZ&amount=10000")
    assert resp.status_code == 400
