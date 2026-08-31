"""Tests for POST /api/transfers and GET /api/transfers/{id} endpoints."""

from fastapi.testclient import TestClient
from ubunturemit_gateway.app import create_app

client = TestClient(create_app())


def test_initiate_transfer_flow() -> None:
    payload = {
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
    }

    resp = client.post("/api/transfers", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["outcome"] == "DELIVERED"
    assert data["status"] == "DELIVERED"
    assert data["selected_rail"] in ("RIPPLE", "PAPSS", "SWIFT")
    assert "transfer_id" in data

    t_id = data["transfer_id"]
    get_resp = client.get(f"/api/transfers/{t_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["transfer_id"] == t_id


def test_initiate_transfer_sanctions_rejection() -> None:
    payload = {
        "source_currency": "ZAR",
        "target_currency": "GHS",
        "send_amount_minor_units": 200000,
        "sender_name": "Sanctioned Person",
        "sender_account": "1002345678",
        "sender_bic": "SBICZAJJXXX",
        "sender_country": "ZA",
        "sender_national_id": "SANCTIONED-001",
        "sender_kyc_tier": "TIER_3",
        "sender_is_pep": False,
        "recipient_name": "Kwame Mensah",
        "recipient_account": "2009876543",
        "recipient_bic": "GHBKGHACXXX",
        "recipient_country": "GH",
        "recipient_national_id": "GH-990202-6000",
        "purpose": "FAMILY_SUPPORT",
        "source_of_funds": "EMPLOYMENT_SALARY",
    }

    resp = client.post("/api/transfers", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["outcome"] == "REJECTED"
    assert "FIC_ACT_S28A" in data["cited_rules"]
