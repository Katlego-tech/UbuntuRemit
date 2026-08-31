"""Tests for pain.001.001.09 message builder and parser (T034/T035).

Implements field mappings per docs/design/iso20022-messaging.md §5 and
validates against services/messaging/schemas/pain.001.001.09.xsd.
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
    SourceOfFunds,
    Transfer,
    TransferId,
    TransferQuote,
    TransferState,
)
from ubunturemit_messaging.pain001 import (
    PURPOSE_TO_ISO,
    build_pain001,
    parse_pain001,
)

PAIN001_XSD_PATH = Path(__file__).resolve().parent.parent / "schemas" / "pain.001.001.09.xsd"


@pytest.fixture
def canonical_transfer() -> Transfer:
    """Canonical Transfer instance for test suite."""
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
        send=Money(minor_units=100000, currency=CurrencyCode.ZAR),  # 1,000.00 ZAR
        fee=Money(minor_units=1500, currency=CurrencyCode.ZAR),  # 15.00 ZAR
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
    )


def test_build_pain001_validates_against_xsd(canonical_transfer: Transfer) -> None:
    """Emitted pain.001.001.09 XML must validate cleanly against admitted schema."""
    xml_str = build_pain001(canonical_transfer)

    schema_doc = etree.parse(str(PAIN001_XSD_PATH))
    xmlschema = etree.XMLSchema(schema_doc)

    doc = etree.fromstring(xml_str.encode("utf-8"))
    assert xmlschema.validate(doc), f"pain.001 XML failed XSD validation: {xmlschema.error_log}"


def test_pain001_round_trip_lossless(canonical_transfer: Transfer) -> None:
    """build_pain001 -> parse_pain001 must round-trip all mapped fields without loss."""
    xml_str = build_pain001(canonical_transfer)
    parsed = parse_pain001(xml_str)

    assert parsed.reference == canonical_transfer.reference
    assert parsed.created_at == canonical_transfer.created_at

    # Sender mapping (§5)
    assert parsed.sender.full_name == canonical_transfer.sender.full_name
    assert parsed.sender.account_number == canonical_transfer.sender.account_number
    assert parsed.sender.bic == canonical_transfer.sender.bic
    assert parsed.sender.country == canonical_transfer.sender.country

    # Recipient mapping (§5)
    assert parsed.recipient.full_name == canonical_transfer.recipient.full_name
    assert parsed.recipient.account_number == canonical_transfer.recipient.account_number
    assert parsed.recipient.bic == canonical_transfer.recipient.bic
    assert parsed.recipient.country == canonical_transfer.recipient.country

    # Quote send amount and currency (§5)
    assert parsed.quote.send.minor_units == canonical_transfer.quote.send.minor_units
    assert parsed.quote.send.currency == canonical_transfer.quote.send.currency

    # Compliance declaration (§5)
    assert parsed.declaration.purpose == canonical_transfer.declaration.purpose
    assert parsed.declaration.source_of_funds == canonical_transfer.declaration.source_of_funds


@pytest.mark.parametrize("purpose", list(PaymentPurpose))
def test_all_payment_purpose_mappings(
    canonical_transfer: Transfer,
    purpose: PaymentPurpose,
) -> None:
    """Every PaymentPurpose variant must map to its specified ExternalPurpose1Code."""
    decl = ComplianceDeclaration(purpose=purpose, source_of_funds=SourceOfFunds.SAVINGS)
    transfer = Transfer(
        id=canonical_transfer.id,
        reference=canonical_transfer.reference,
        sender=canonical_transfer.sender,
        recipient=canonical_transfer.recipient,
        quote=canonical_transfer.quote,
        declaration=decl,
        state=canonical_transfer.state,
        created_at=canonical_transfer.created_at,
    )
    xml_str = build_pain001(transfer)

    # Check XML contains the mapped purpose code
    expected_iso_code = PURPOSE_TO_ISO[purpose]
    assert f"<Cd>{expected_iso_code}</Cd>" in xml_str

    # Round trip
    parsed = parse_pain001(xml_str)
    assert parsed.declaration.purpose == purpose


@pytest.mark.parametrize("source_of_funds", list(SourceOfFunds))
def test_source_of_funds_in_supplementary_data(
    canonical_transfer: Transfer,
    source_of_funds: SourceOfFunds,
) -> None:
    """SourceOfFunds rides in SplmtryData, never in Purp/Cd (§5)."""
    decl = ComplianceDeclaration(
        purpose=PaymentPurpose.GOODS_OR_SERVICES,
        source_of_funds=source_of_funds,
    )
    transfer = Transfer(
        id=canonical_transfer.id,
        reference=canonical_transfer.reference,
        sender=canonical_transfer.sender,
        recipient=canonical_transfer.recipient,
        quote=canonical_transfer.quote,
        declaration=decl,
        state=canonical_transfer.state,
        created_at=canonical_transfer.created_at,
    )
    xml_str = build_pain001(transfer)

    assert "<SplmtryData>" in xml_str
    expected_sof_tag = (
        f'<SourceOfFunds xmlns="urn:sarb:excon:v1">{source_of_funds.value}</SourceOfFunds>'
    )
    assert expected_sof_tag in xml_str

    parsed = parse_pain001(xml_str)
    assert parsed.declaration.source_of_funds == source_of_funds


def test_pain001_amounts_as_exact_decimal_strings(canonical_transfer: Transfer) -> None:
    """Amounts serialize as decimal strings derived from minor units, never float literals."""
    xml_str = build_pain001(canonical_transfer)
    assert 'InstdAmt Ccy="ZAR">1000.00<' in xml_str


def test_pain001_charge_bearer_mandatory(canonical_transfer: Transfer) -> None:
    """ChrgBr is emitted as SLEV unconditionally (§5)."""
    xml_str = build_pain001(canonical_transfer)
    assert "<ChrgBr>SLEV</ChrgBr>" in xml_str


def test_parse_pain001_rejects_malformed_xml() -> None:
    """Reject non-XML string."""
    with pytest.raises(ValueError, match="XML syntax error"):
        parse_pain001("not xml")


def test_parse_pain001_rejects_wrong_namespace() -> None:
    """Reject Document in wrong namespace."""
    bad_ns_xml = "<Document xmlns='urn:iso:std:iso:20022:tech:xsd:pain.001.001.08'/>"
    with pytest.raises(ValueError, match="Unexpected namespace"):
        parse_pain001(bad_ns_xml)


def test_parse_pain001_rejects_unmapped_purpose_code(canonical_transfer: Transfer) -> None:
    """Reject XML containing an unknown or unsupported Purpose code."""
    xml_str = build_pain001(canonical_transfer).replace("<Cd>FAMI</Cd>", "<Cd>XXXX</Cd>")
    with pytest.raises(ValueError, match="Unsupported or unmapped ISO purpose code 'XXXX'"):
        parse_pain001(xml_str)
