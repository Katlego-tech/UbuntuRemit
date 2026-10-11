"""Tests for GET /api/compliance/health (T073)."""

from fastapi.testclient import TestClient
from gateway_fakes import TEST_LIST, configured_dependencies
from ubunturemit_asco.guardrails.entry import ENTRY_GATE_RULES
from ubunturemit_gateway.app import create_app


def test_health_reports_unavailable_when_nothing_is_wired() -> None:
    resp = TestClient(create_app()).get("/api/compliance/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "UNAVAILABLE"
    assert data["missing_dependencies"] == [
        "quote_source",
        "sentinel_client",
        "strategist_client",
        "sanctions_screener",
        "limit_table",
        "rail_router",
        "audit_logger",
    ]
    assert data["sanctions_list"] is None
    assert data["audit_log"] is None
    assert data["rejection_rate_24h"] is None
    assert data["total_screened_24h"] is None


def test_health_names_no_hardware() -> None:
    body = TestClient(create_app()).get("/api/compliance/health").text
    for claim in ("MI300X", "70B", "32B", "OPERATIONAL"):
        assert claim not in body


def test_health_reports_what_is_wired() -> None:
    data = TestClient(create_app(configured_dependencies())).get("/api/compliance/health").json()
    assert data["status"] == "OPERATIONAL"
    assert data["missing_dependencies"] == []
    assert data["sanctions_list"] == TEST_LIST.citation()
    assert data["rules_enforced"] == list(ENTRY_GATE_RULES)
