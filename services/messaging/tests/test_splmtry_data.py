"""Tests for SplmtryData handling and SARB envelope compliance (T038).

Rules per docs/design/iso20022-messaging.md §5:
- SourceOfFunds rides in SplmtryData under PlcAndNm and Envlp, NEVER in Purp/Cd.
- No local requirement is implemented by modifying base ISO 20022 XML elements.
- Uses processContents="skip" / "lax" standard envelope behavior.
"""

from datetime import UTC, datetime
from decimal import Decimal

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
from ubunturemit_messaging.pain001 import (
    PAIN001_NS,
    build_pain001,
    parse_pain001,
)


@pytest.fixture
def base_transfer() -> Transfer:
    """Base Transfer for supplementary data tests."""
    return Transfer(
        id=TransferId("TR-99420-001"),
        reference="UB-99420-X",
        sender=Party(
            full_name="Amara Okafor",
            account_number="1002938475",
            bic="SBICZAJJXXX",
            country=CountryCode("ZA"),
        ),
        recipient=Party(
            full_name="Kofi Mensah",
            account_number="2003948576",
            bic="GHBKGHACXXX",
            country=CountryCode("GH"),
        ),
        quote=TransferQuote(
            send=Money(minor_units=100000, currency=CurrencyCode.ZAR),
            fee=Money(minor_units=1500, currency=CurrencyCode.ZAR),
            recipient_receives=Money(minor_units=83725, currency=CurrencyCode.GHS),
            fx=FxQuote(
                corridor=Corridor(
                    source=CurrencyCode.ZAR,
                    target=CurrencyCode.GHS,
                    papss_eligible=True,
                ),
                rate=Decimal("0.8500"),
                guaranteed=True,
                captured_at=datetime(2026, 8, 31, 10, 0, 0, tzinfo=UTC),
                expires_at=datetime(2026, 8, 31, 10, 15, 0, tzinfo=UTC),
                source=RateSource.LIVE_INTERBANK,
            ),
        ),
        declaration=ComplianceDeclaration(
            purpose=PaymentPurpose.GOODS_OR_SERVICES,
            source_of_funds=SourceOfFunds.BUSINESS_REVENUE,
        ),
        state=TransferState.VALIDATED,
        created_at=datetime(2026, 8, 31, 10, 5, 0, tzinfo=UTC),
        rail=SettlementRail.PAPSS,
    )


def test_source_of_funds_not_in_purpose_code(base_transfer: Transfer) -> None:
    """SourceOfFunds must never be encoded in Purp/Cd."""
    xml_str = build_pain001(base_transfer)
    root = etree.fromstring(xml_str.encode("utf-8"))
    ns = {"p": PAIN001_NS}

    purp_elem = root.find(".//p:CdtTrfTxInf/p:Purp/p:Cd", namespaces=ns)
    assert purp_elem is not None
    # Purp/Cd must be the ISO ExternalPurpose1Code GDDS, not BUSINESS_REVENUE
    assert purp_elem.text == "GDDS"
    assert "BUSINESS_REVENUE" not in purp_elem.text


def test_supplementary_data_structure_and_namespace(base_transfer: Transfer) -> None:
    """SplmtryData must contain standard PlcAndNm and Envlp with excon namespace."""
    xml_str = build_pain001(base_transfer)
    root = etree.fromstring(xml_str.encode("utf-8"))
    ns = {"p": PAIN001_NS, "ex": "urn:sarb:excon:v1"}

    plc = root.find(".//p:CdtTrfTxInf/p:SplmtryData/p:PlcAndNm", namespaces=ns)
    assert plc is not None
    assert plc.text == "/Document/CstmrCdtTrfInitn/PmtInf/CdtTrfTxInf"

    sof = root.find(".//p:CdtTrfTxInf/p:SplmtryData/p:Envlp/ex:SourceOfFunds", namespaces=ns)
    assert sof is not None
    assert sof.text == "BUSINESS_REVENUE"


def test_supplementary_data_round_trips_all_source_of_funds_variants(
    base_transfer: Transfer,
) -> None:
    """Every SourceOfFunds enum value round-trips accurately via SplmtryData."""
    for sof in SourceOfFunds:
        decl = ComplianceDeclaration(purpose=PaymentPurpose.FAMILY_SUPPORT, source_of_funds=sof)
        transfer = Transfer(
            id=base_transfer.id,
            reference=base_transfer.reference,
            sender=base_transfer.sender,
            recipient=base_transfer.recipient,
            quote=base_transfer.quote,
            declaration=decl,
            state=base_transfer.state,
            created_at=base_transfer.created_at,
        )
        xml = build_pain001(transfer)
        parsed = parse_pain001(xml)
        assert parsed.declaration.source_of_funds == sof
