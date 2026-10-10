"""Tests for POST /api/transfers and GET /api/transfers/{id} (T041a, T043, T044, T073)."""

import dataclasses

from fastapi.testclient import TestClient
from gateway_fakes import (
    TEST_LIST,
    ScriptedTestLLMClient,
    SimulatedTestRail,
    configured_dependencies,
)
from ubunturemit_domain import SettlementRail
from ubunturemit_gateway.app import create_app
from ubunturemit_rails import RailRouter

unconfigured = TestClient(create_app())
configured = TestClient(create_app(configured_dependencies()))


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_currency": "ZAR",
        "target_currency": "GHS",
        "send_amount_minor_units": 200000,
        "sender_name": "Katlego Ndlovu",
        "sender_account": "1002345678",
        "sender_bic": "SBICZAJJXXX",
        "sender_country": "ZA",
        "sender_national_id": "ZA-880101-5000",
        "sender_kyc_tier": "L3",
        "sender_is_pep": False,
        "recipient_name": "Kwame Mensah",
        "recipient_account": "2009876543",
        "recipient_bic": "GHBKGHACXXX",
        "recipient_country": "GH",
        "recipient_national_id": "GH-990202-6000",
        "purpose": "FAMILY_SUPPORT",
        "source_of_funds": "EMPLOYMENT_SALARY",
        "sender_prior_transfers_30d_count": 1,
        "sender_prior_transfers_30d_minor_units": 50000,
        "recipient_account_age_days": 412,
    }
    payload.update(overrides)
    return payload


def test_transfer_without_sources_is_refused_and_names_them() -> None:
    resp = unconfigured.post("/api/transfers", json=_payload())
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    for name in (
        "quote_source",
        "sentinel_client",
        "strategist_client",
        "sanctions_screener",
        "rail_router",
        "audit_logger",
    ):
        assert name in detail


def test_compliance_inputs_have_no_defaults() -> None:
    payload = _payload()
    del payload["recipient_account_age_days"]
    assert configured.post("/api/transfers", json=payload).status_code == 422


def test_transfer_cites_the_verdict_it_rests_on() -> None:
    resp = configured.post("/api/transfers", json=_payload())
    assert resp.status_code == 200
    data = resp.json()
    assert data["cited_rules"] == ["TEST_RULE_FROM_MOCKED_MODEL"]

    get_resp = configured.get(f"/api/transfers/{data['transfer_id']}")
    assert get_resp.status_code == 200
    assert get_resp.json() == data  # the GET keeps the citations the POST returned


def test_sanctions_rejection_cites_the_loaded_list() -> None:
    resp = configured.post("/api/transfers", json=_payload(sender_name="Listed Test Person"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["outcome"] == "REJECTED"
    assert data["status"] == "REJECTED"
    assert "FIC_ACT_S28A" in data["cited_rules"]
    assert TEST_LIST.citation() in data["cited_rules"]


def test_partial_configuration_names_only_what_is_missing() -> None:
    deps = dataclasses.replace(configured_dependencies(), sanctions_screener=None)
    resp = TestClient(create_app(deps)).post("/api/transfers", json=_payload())
    assert resp.status_code == 503
    assert "sanctions_screener" in resp.json()["detail"]
    assert "quote_source" not in resp.json()["detail"]


def test_kyc_tier_is_never_coerced() -> None:
    assert (
        configured.post("/api/transfers", json=_payload(sender_kyc_tier="TIER_3")).status_code
        == 422
    )
    payload = _payload()
    del payload["sender_kyc_tier"]
    assert configured.post("/api/transfers", json=payload).status_code == 422


def test_l1_sender_gets_the_l1_limit() -> None:
    """5,000.01 ZAR is over the L1 single-transfer limit; L1 must not be read as L2."""
    resp = configured.post(
        "/api/transfers", json=_payload(sender_kyc_tier="L1", send_amount_minor_units=500001)
    )
    data = resp.json()
    assert data["outcome"] == "REJECTED"
    assert "FICA_TIER_LIMIT" in data["cited_rules"]


def test_sentinel_block_is_returned_with_its_citations() -> None:
    blocking = ScriptedTestLLMClient(
        {
            "outcome": "BLOCK",
            "riskScore": 0.9,
            "citedRules": ["TEST_BLOCK_RULE"],
            "rationale": "Scripted block.",
        }
    )
    deps = dataclasses.replace(configured_dependencies(), sentinel_client=blocking)
    data = TestClient(create_app(deps)).post("/api/transfers", json=_payload()).json()
    assert data["outcome"] == "REJECTED"
    assert data["selected_rail"] is None
    assert data["cited_rules"] == ["TEST_BLOCK_RULE"]


def test_apps_do_not_share_transfers() -> None:
    first = TestClient(create_app(configured_dependencies()))
    t_id = first.post("/api/transfers", json=_payload()).json()["transfer_id"]
    other = TestClient(create_app(configured_dependencies()))
    assert other.get(f"/api/transfers/{t_id}").status_code == 404


def test_exhausted_settlement_is_stored_as_failed() -> None:
    failing = RailRouter(adapters={SettlementRail.PAPSS: SimulatedTestRail(fail=True)})
    client = TestClient(
        create_app(dataclasses.replace(configured_dependencies(), rail_router=failing))
    )
    data = client.post("/api/transfers", json=_payload()).json()
    assert data["status"] == "FAILED"
    assert data["selected_rail"] is None
    assert client.get(f"/api/transfers/{data['transfer_id']}").json() == data


def test_missing_rail_router_alone_is_named() -> None:
    deps = dataclasses.replace(configured_dependencies(), rail_router=None)
    client = TestClient(create_app(deps))
    for resp in (
        client.post("/api/transfers", json=_payload()),
        client.get("/api/fx/quote?source=ZAR&target=GHS&amount=500000"),
    ):
        assert resp.status_code == 503
        assert "rail_router" in resp.json()["detail"]
        assert "quote_source" not in resp.json()["detail"]
