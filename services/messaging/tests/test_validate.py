"""Tests for 3-tier runtime validation gates (T039).

Rules per docs/design/iso20022-messaging.md §6B:
- Gate 1: XSD validation against admitted schema.
- Gate 2: Field rules (mandatory fields, valid enums, valid ISO 4217 currencies).
- Gate 3: Business rules (amount > 0, corridor support, EndToEndId uniqueness / reuse rejection).
- Fully deterministic, no model participates.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ubunturemit_domain import (
    ComplianceDeclaration,
    Corridor,
    CountryCode,
    CurrencyCode,
    FxQuote,
    Money,
    Party,
    PaymentPurpose,
    RateSource,
    SettlementRail,
    SourceOfFunds,
    Transfer,
    TransferId,
    TransferQuote,
    TransferState,
)
from ubunturemit_messaging.pain001 import build_pain001
from ubunturemit_messaging.validate import (
    InMemoryEndToEndIdStore,
    validate_pain001_message,
)


@pytest.fixture
def valid_transfer() -> Transfer:
    """Canonical valid Transfer aggregate."""
    sender = Party(
        full_name="Amara Okafor",
        account_number="1002938475",
        bic="SBICZAJJXXX",
        country=CountryCode("ZA"),
    )
    recipient = Party(
        full_name="Kofi Mensah",
        account_number="2003948576",
        bic="GHBKGHACXXX",
        country=CountryCode("GH"),
    )
    corridor = Corridor(
        source=CurrencyCode.ZAR,
        target=CurrencyCode.GHS,
        papss_eligible=True,
    )
    fx = FxQuote(
        corridor=corridor,
        rate=Decimal("0.8500"),
        guaranteed=True,
        captured_at=datetime(2026, 8, 31, 10, 0, 0, tzinfo=UTC),
        expires_at=datetime(2026, 8, 31, 10, 15, 0, tzinfo=UTC),
        source=RateSource.LIVE_INTERBANK,
    )
    quote = TransferQuote(
        send=Money(minor_units=100000, currency=CurrencyCode.ZAR),
        fee=Money(minor_units=1500, currency=CurrencyCode.ZAR),
        recipient_receives=Money(minor_units=83725, currency=CurrencyCode.GHS),
        fx=fx,
    )
    declaration = ComplianceDeclaration(
        purpose=PaymentPurpose.FAMILY_SUPPORT,
        source_of_funds=SourceOfFunds.EMPLOYMENT_SALARY,
    )
    return Transfer(
        id=TransferId("TR-99420-001"),
        reference="UB-99420-X",
        sender=sender,
        recipient=recipient,
        quote=quote,
        declaration=declaration,
        state=TransferState.INITIATED,
        created_at=datetime(2026, 8, 31, 10, 5, 0, tzinfo=UTC),
        rail=SettlementRail.PAPSS,
    )


def test_validation_gate_success(valid_transfer: Transfer) -> None:
    """A fully compliant message passes all 3 validation gates."""
    xml_str = build_pain001(valid_transfer)
    id_store = InMemoryEndToEndIdStore()

    verdict = validate_pain001_message(xml_str, id_store=id_store)
    assert verdict.valid is True
    assert verdict.stage == "ACCEPTED"
    assert "All validation gates passed" in verdict.reason


def test_gate1_xsd_validation_fails_on_malformed_xml() -> None:
    """Tier 1: Syntax errors and non-XML payloads rejected at XSD stage."""
    verdict = validate_pain001_message("not xml at all")
    assert verdict.valid is False
    assert verdict.stage == "XSD"
    assert "XML syntax error" in verdict.reason


def test_gate1_xsd_validation_fails_on_schema_violation(valid_transfer: Transfer) -> None:
    """Tier 1: Schema element violations rejected at XSD stage."""
    xml_str = build_pain001(valid_transfer)
    # Introduce an illegal XML tag inside GrpHdr
    corrupted_xml = xml_str.replace("</GrpHdr>", "<IllegalTag>foo</IllegalTag></GrpHdr>")

    verdict = validate_pain001_message(corrupted_xml)
    assert verdict.valid is False
    assert verdict.stage == "XSD"
    assert "XSD validation failed" in verdict.reason


def test_gate2_field_rules_fails_on_unsupported_purpose_code(valid_transfer: Transfer) -> None:
    """Tier 2: Purpose code outside mapped taxonomy rejected at Field Rules stage."""
    xml_str = build_pain001(valid_transfer).replace("<Cd>FAMI</Cd>", "<Cd>OTHR</Cd>")

    verdict = validate_pain001_message(xml_str)
    assert verdict.valid is False
    assert verdict.stage == "FIELD_RULES"
    assert "Unsupported purpose code" in verdict.reason


def test_gate2_field_rules_fails_on_unsupported_currency(valid_transfer: Transfer) -> None:
    """Tier 2: Currency code outside supported CurrencyCode rejected."""
    xml_str = build_pain001(valid_transfer).replace('Ccy="ZAR"', 'Ccy="EUR"')

    verdict = validate_pain001_message(xml_str)
    assert verdict.valid is False
    assert verdict.stage == "FIELD_RULES"
    assert "Unsupported currency" in verdict.reason


def test_gate3_business_rules_fails_on_zero_amount(valid_transfer: Transfer) -> None:
    """Tier 3: Non-positive amounts rejected at Business Rules stage."""
    xml_str = build_pain001(valid_transfer).replace(">1000.00<", ">0.00<")

    verdict = validate_pain001_message(xml_str)
    assert verdict.valid is False
    assert verdict.stage == "BUSINESS_RULES"
    assert "Amount must be greater than zero" in verdict.reason


def test_gate3_business_rules_fails_on_end_to_end_id_reuse(valid_transfer: Transfer) -> None:
    """Tier 3: EndToEndId reuse is a hard rejection rather than a warning (§6B)."""
    xml_str = build_pain001(valid_transfer)
    id_store = InMemoryEndToEndIdStore()

    # First submission passes and records the ID
    first_verdict = validate_pain001_message(xml_str, id_store=id_store)
    assert first_verdict.valid is True
    assert first_verdict.stage == "ACCEPTED"

    # Second submission with same EndToEndId fails hard
    second_verdict = validate_pain001_message(xml_str, id_store=id_store)
    assert second_verdict.valid is False
    assert second_verdict.stage == "BUSINESS_RULES"
    assert "reused" in second_verdict.reason
