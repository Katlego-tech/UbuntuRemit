"""Tests for Bounded alternate rail retry on FAILED state (T055).

Rules per docs/design/domain-model.md §4:
- FAILED -> SETTLING retry bounded at 2 alternate rails.
- If primary rail fails, retries up to 2 alternate rails.
- If all 3 rails fail, raises SettlementExhaustionError.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from simulated_rails import SimulatedRail
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
from ubunturemit_rails.router import RailRouter, SettlementExhaustionError


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
        SettlementRail.RIPPLE: SimulatedRail(SettlementRail.RIPPLE, fail=True),
        SettlementRail.PAPSS: SimulatedRail(SettlementRail.PAPSS, fail=False),
        SettlementRail.SWIFT: SimulatedRail(SettlementRail.SWIFT, fail=False),
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
        SettlementRail.RIPPLE: SimulatedRail(SettlementRail.RIPPLE, fail=True),
        SettlementRail.PAPSS: SimulatedRail(SettlementRail.PAPSS, fail=True),
        SettlementRail.SWIFT: SimulatedRail(SettlementRail.SWIFT, fail=True),
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


def test_router_refuses_to_build_without_adapters() -> None:
    with pytest.raises(ValueError, match="at least one"):
        RailRouter(adapters={})


def test_retry_never_counts_a_rail_with_no_adapter(transfer: Transfer) -> None:
    """RIPPLE fails, PAPSS has no adapter: the one retry is SWIFT's, recorded as SWIFT."""
    submitted: list[Transfer] = []

    class RecordingSwift(SimulatedRail):
        def submit_settlement(self, pacs008_xml: str, transfer: Transfer):  # noqa: ANN201
            submitted.append(transfer)
            return super().submit_settlement(pacs008_xml, transfer)

    router = RailRouter(
        adapters={
            SettlementRail.RIPPLE: SimulatedRail(SettlementRail.RIPPLE, fail=True),
            SettlementRail.SWIFT: RecordingSwift(SettlementRail.SWIFT),
        }
    )
    orchestrator = MasterOrchestrator()
    settled, result, attempts = router.execute_settlement_with_retry(
        transfer=transfer,
        pacs008_xml=build_pacs008(transfer),
        preferred_rail=SettlementRail.RIPPLE,
        orchestrator=orchestrator,
    )
    assert [a.rail for a in attempts] == [SettlementRail.RIPPLE, SettlementRail.SWIFT]
    assert settled.state == TransferState.DELIVERED
    assert orchestrator.get_retry_count(transfer.id) == 1
    # The retry was recorded against the rail actually attempted, not a skipped one.
    assert submitted[0].rail == SettlementRail.SWIFT
    assert submitted[0].state == TransferState.SETTLING


def test_get_quotes_skips_papss_on_an_ineligible_corridor(transfer: Transfer) -> None:
    router = RailRouter(
        adapters={
            SettlementRail.PAPSS: SimulatedRail(SettlementRail.PAPSS),
            SettlementRail.SWIFT: SimulatedRail(SettlementRail.SWIFT),
        }
    )
    corridor = Corridor(source=CurrencyCode.ZAR, target=CurrencyCode.GHS, papss_eligible=False)
    quotes = router.get_quotes(corridor, transfer.quote.send)
    assert [q.rail for q in quotes] == [SettlementRail.SWIFT]


def test_settlement_refuses_when_the_approved_rail_has_no_adapter(transfer: Transfer) -> None:
    router = RailRouter(adapters={SettlementRail.SWIFT: SimulatedRail(SettlementRail.SWIFT)})
    with pytest.raises(ValueError, match="approved rail"):
        router.execute_settlement_with_retry(
            transfer=transfer,
            pacs008_xml=build_pacs008(transfer),
            preferred_rail=SettlementRail.PAPSS,
            orchestrator=MasterOrchestrator(),
        )
