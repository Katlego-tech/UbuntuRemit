"""Tests for Ripple, PAPSS, and SWIFT rail adapters (T052, T053, T054)."""

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
from ubunturemit_messaging.pacs008 import build_pacs008
from ubunturemit_rails.base import RailStatus
from ubunturemit_rails.papss import PapssRailAdapter
from ubunturemit_rails.ripple import RippleRailAdapter
from ubunturemit_rails.swift import SwiftRailAdapter


@pytest.fixture
def transfer() -> Transfer:
    corridor = Corridor(
        source=CurrencyCode.ZAR,
        target=CurrencyCode.GHS,
        papss_eligible=True,
    )
    quote = TransferQuote(
        send=Money(minor_units=100000, currency=CurrencyCode.ZAR),
        fee=Money(minor_units=1500, currency=CurrencyCode.ZAR),
        recipient_receives=Money(minor_units=83725, currency=CurrencyCode.GHS),
        fx=FxQuote(
            corridor=corridor,
            rate=Decimal("0.8500"),
            guaranteed=True,
            captured_at=datetime(2026, 8, 31, 10, 0, 0, tzinfo=UTC),
            expires_at=datetime(2026, 8, 31, 10, 15, 0, tzinfo=UTC),
            source=RateSource.LIVE_INTERBANK,
        ),
    )
    return Transfer(
        id=TransferId("TR-RAILS-001"),
        reference="UB-RAILS-001",
        sender=Party("Sender Name", "123", "SBICZAJJXXX", CountryCode("ZA")),
        recipient=Party("Recipient Name", "456", "GHBKGHACXXX", CountryCode("GH")),
        quote=quote,
        declaration=ComplianceDeclaration(
            purpose=PaymentPurpose.FAMILY_SUPPORT,
            source_of_funds=SourceOfFunds.EMPLOYMENT_SALARY,
        ),
        state=TransferState.SETTLING,
        created_at=datetime(2026, 8, 31, 10, 5, 0, tzinfo=UTC),
    )


def test_ripple_adapter(transfer: Transfer) -> None:
    adapter = RippleRailAdapter()
    quote = adapter.get_quote(transfer.quote.fx.corridor, transfer.quote.send)
    assert quote.rail == SettlementRail.RIPPLE
    assert quote.fee_minor_units == 0

    pacs_xml = build_pacs008(transfer)
    result = adapter.submit_settlement(pacs_xml, transfer)
    assert result.status == RailStatus.DELIVERED
    assert result.rail == SettlementRail.RIPPLE
    assert result.settlement_reference.startswith("XRPL-")


def test_papss_adapter(transfer: Transfer) -> None:
    adapter = PapssRailAdapter()
    quote = adapter.get_quote(transfer.quote.fx.corridor, transfer.quote.send)
    assert quote.rail == SettlementRail.PAPSS
    assert quote.fee_minor_units == 1200

    pacs_xml = build_pacs008(transfer)
    result = adapter.submit_settlement(pacs_xml, transfer)
    assert result.status == RailStatus.DELIVERED
    assert result.rail == SettlementRail.PAPSS
    assert result.settlement_reference.startswith("PAPSS-")


def test_swift_adapter(transfer: Transfer) -> None:
    adapter = SwiftRailAdapter()
    quote = adapter.get_quote(transfer.quote.fx.corridor, transfer.quote.send)
    assert quote.rail == SettlementRail.SWIFT
    assert quote.fee_minor_units == 4500

    pacs_xml = build_pacs008(transfer)
    result = adapter.submit_settlement(pacs_xml, transfer)
    assert result.status == RailStatus.DELIVERED
    assert result.rail == SettlementRail.SWIFT
    assert result.settlement_reference.startswith("UETR-")
