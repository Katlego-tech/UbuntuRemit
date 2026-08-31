"""Tests for Bounded alternate rail retry on FAILED state (T055).

Rules per docs/design/domain-model.md §4:
- FAILED -> SETTLING retry bounded at 2 alternate rails.
- If primary rail fails, retries up to 2 alternate rails.
- If all 3 rails fail, raises SettlementExhaustionError.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ubunturemit_asco.orchestrator.master import MasterOrchestrator
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
from ubunturemit_rails.papss import PapssRailAdapter
from ubunturemit_rails.ripple import RippleRailAdapter
from ubunturemit_rails.router import RailRouter, SettlementExhaustionError
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
        id=TransferId("TR-RETRY-001"),
        reference="UB-RETRY-001",
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


def test_retry_fallback_to_second_rail(transfer: Transfer) -> None:
    """When primary rail fails, fallback to second rail succeeds within retry budget."""
    adapters = {
        SettlementRail.RIPPLE: RippleRailAdapter(simulate_failure=True),
        SettlementRail.PAPSS: PapssRailAdapter(simulate_failure=False),
        SettlementRail.SWIFT: SwiftRailAdapter(simulate_failure=False),
    }
    router = RailRouter(adapters=adapters)
    orchestrator = MasterOrchestrator()
    pacs_xml = build_pacs008(transfer)

    settled_transfer, result, attempts = router.execute_settlement_with_retry(
        transfer=transfer,
        pacs008_xml=pacs_xml,
        preferred_rail=SettlementRail.RIPPLE,
        orchestrator=orchestrator,
    )

    assert settled_transfer.state == TransferState.DELIVERED
    assert settled_transfer.rail == SettlementRail.PAPSS
    assert len(attempts) == 2
    assert attempts[0].rail == SettlementRail.RIPPLE
    assert attempts[1].rail == SettlementRail.PAPSS
    assert orchestrator.get_retry_count(transfer.id) == 1


def test_retry_exhaustion_when_all_rails_fail(transfer: Transfer) -> None:
    """When all candidate rails fail, retry budget of 2 is exhausted.
    Raises SettlementExhaustionError.
    """
    adapters = {
        SettlementRail.RIPPLE: RippleRailAdapter(simulate_failure=True),
        SettlementRail.PAPSS: PapssRailAdapter(simulate_failure=True),
        SettlementRail.SWIFT: SwiftRailAdapter(simulate_failure=True),
    }
    router = RailRouter(adapters=adapters)
    orchestrator = MasterOrchestrator()
    pacs_xml = build_pacs008(transfer)

    with pytest.raises(SettlementExhaustionError, match="Retry budget exhausted"):
        router.execute_settlement_with_retry(
            transfer=transfer,
            pacs008_xml=pacs_xml,
            preferred_rail=SettlementRail.RIPPLE,
            orchestrator=orchestrator,
        )

    # Retry count reached 2
    assert orchestrator.get_retry_count(transfer.id) == 2
