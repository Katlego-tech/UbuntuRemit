"""Tests for POST /api/transfers and GET /api/transfers/{id} (T041a, T043, T044, T073)."""

from fastapi.testclient import TestClient
from gateway_fakes import TEST_LIST, configured_dependencies
from ubunturemit_gateway.app import create_app

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
        "sender_kyc_tier": "TIER_3",
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
    for name in ("quote_source", "sentinel_client", "strategist_client", "sanctions_screener"):
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

    t_id = data["transfer_id"]
    get_resp = configured.get(f"/api/transfers/{t_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["transfer_id"] == t_id


def test_sanctions_rejection_cites_the_loaded_list() -> None:
    resp = configured.post("/api/transfers", json=_payload(sender_name="Listed Test Person"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["outcome"] == "REJECTED"
    assert "FIC_ACT_S28A" in data["cited_rules"]
    assert TEST_LIST.citation() in data["cited_rules"]
