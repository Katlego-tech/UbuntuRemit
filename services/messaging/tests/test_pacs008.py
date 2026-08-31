"""Tests for pacs.008.001.08 message builder and parser (T036).

Implements field mappings per docs/design/iso20022-messaging.md §5 and
validates against services/messaging/schemas/pacs.008.001.08.xsd.
"""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from lxml import etree
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
from ubunturemit_messaging.pacs008 import (
    build_pacs008,
    parse_pacs008,
)

PACS008_XSD_PATH = Path(__file__).resolve().parent.parent / "schemas" / "pacs.008.001.08.xsd"


@pytest.fixture
def canonical_transfer() -> Transfer:
    """Canonical Transfer aggregate for pacs.008 tests."""
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
        recipient_receives=Money(minor_units=83725, currency=CurrencyCode.GHS),  # 837.25 GHS
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
        state=TransferState.VALIDATED,
        created_at=datetime(2026, 8, 31, 10, 5, 0, tzinfo=UTC),
        rail=SettlementRail.PAPSS,
    )


def test_build_pacs008_validates_against_xsd(canonical_transfer: Transfer) -> None:
    """Emitted pacs.008.001.08 XML must validate cleanly against admitted schema."""
    xml_str = build_pacs008(canonical_transfer)

    schema_doc = etree.parse(str(PACS008_XSD_PATH))
    xmlschema = etree.XMLSchema(schema_doc)

    doc = etree.fromstring(xml_str.encode("utf-8"))
    assert xmlschema.validate(doc), f"pacs.008 XML failed XSD validation: {xmlschema.error_log}"


def test_pacs008_round_trip_lossless(canonical_transfer: Transfer) -> None:
    """build_pacs008 -> parse_pacs008 must round-trip all mapped fields without loss."""
    xml_str = build_pacs008(canonical_transfer)
    parsed = parse_pacs008(xml_str)

    assert parsed.reference == canonical_transfer.reference
    assert parsed.id == canonical_transfer.id

    # Sender mapping
    assert parsed.sender.full_name == canonical_transfer.sender.full_name
    assert parsed.sender.account_number == canonical_transfer.sender.account_number
    assert parsed.sender.bic == canonical_transfer.sender.bic
    assert parsed.sender.country == canonical_transfer.sender.country

    # Recipient mapping
    assert parsed.recipient.full_name == canonical_transfer.recipient.full_name
    assert parsed.recipient.account_number == canonical_transfer.recipient.account_number
    assert parsed.recipient.bic == canonical_transfer.recipient.bic
    assert parsed.recipient.country == canonical_transfer.recipient.country

    # Recipient settlement amount and currency
    expected_recipient = canonical_transfer.quote.recipient_receives
    assert parsed.quote.recipient_receives.minor_units == expected_recipient.minor_units
    assert parsed.quote.recipient_receives.currency == expected_recipient.currency

    # Compliance declaration
    assert parsed.declaration.purpose == canonical_transfer.declaration.purpose


@pytest.mark.parametrize(
    ("rail", "expected_method"),
    [
        (SettlementRail.PAPSS, "CLRG"),
        (SettlementRail.SWIFT, "INDA"),
        (SettlementRail.RIPPLE, "INDA"),
    ],
)
def test_pacs008_settlement_method_derivation(
    canonical_transfer: Transfer,
    rail: SettlementRail,
    expected_method: str,
) -> None:
    """Verify SttlmMtd derived correctly from rail (CLRG for PAPSS, INDA for SWIFT/Ripple)."""
    transfer = Transfer(
        id=canonical_transfer.id,
        reference=canonical_transfer.reference,
        sender=canonical_transfer.sender,
        recipient=canonical_transfer.recipient,
        quote=canonical_transfer.quote,
        declaration=canonical_transfer.declaration,
        state=canonical_transfer.state,
        created_at=canonical_transfer.created_at,
        rail=rail,
    )
    xml_str = build_pacs008(transfer)
    assert f"<SttlmMtd>{expected_method}</SttlmMtd>" in xml_str
    if rail == SettlementRail.PAPSS:
        assert "<ClrSys>" in xml_str
        assert "<Prtry>PAPSS</Prtry>" in xml_str


def test_pacs008_join_key_end_to_end_id(canonical_transfer: Transfer) -> None:
    """EndToEndId must carry Transfer.reference as join key across messages."""
    xml_str = build_pacs008(canonical_transfer)
    assert f"<EndToEndId>{canonical_transfer.reference}</EndToEndId>" in xml_str
    assert f"<TxId>{canonical_transfer.id}</TxId>" in xml_str


def test_pacs008_amounts_as_exact_decimal_strings(canonical_transfer: Transfer) -> None:
    """IntrBkSttlmAmt serializes as decimal string from minor units, never float."""
    xml_str = build_pacs008(canonical_transfer)
    assert 'IntrBkSttlmAmt Ccy="GHS">837.25<' in xml_str


def test_parse_pacs008_rejects_malformed_xml() -> None:
    """Reject non-XML string."""
    with pytest.raises(ValueError, match="XML syntax error"):
        parse_pacs008("not xml")


def test_parse_pacs008_rejects_wrong_namespace() -> None:
    """Reject Document in wrong namespace."""
    bad_ns_xml = "<Document xmlns='urn:iso:std:iso:20022:tech:xsd:pacs.008.001.07'/>"
    with pytest.raises(ValueError, match="Unexpected namespace"):
        parse_pacs008(bad_ns_xml)
