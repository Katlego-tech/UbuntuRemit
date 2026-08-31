"""Tests for Master Orchestrator state machine (T042).

Rules per docs/design/domain-model.md §4 & docs/design/asco-orchestrator.md §3, §4:
- Exhaustive verification of TransferState × TransferState (7 legal, 29 refused).
- Master Orchestrator makes zero LLM calls of its own.
- Retry on alternate rail (FAILED -> SETTLING) is bounded at 2.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ubunturemit_asco.orchestrator.master import (
    LEGAL_TRANSITIONS,
    MasterOrchestrator,
    OrchestratorStateError,
    RetryBudgetExceededError,
)
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


@pytest.fixture
def base_transfer() -> Transfer:
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


def test_exhaustive_state_transition_matrix(base_transfer: Transfer) -> None:
    """Every pair in TransferState x TransferState is tested.
    7 legal pairs must succeed; 29 illegal pairs must raise ValueError or OrchestratorStateError.
    """
    all_states = list(TransferState)
    assert len(all_states) == 6  # 6 * 6 = 36 total pairs

    legal_count = 0
    illegal_count = 0

    orchestrator = MasterOrchestrator()

    for from_state in all_states:
        for to_state in all_states:
            # Construct transfer in from_state
            t = Transfer(
                id=base_transfer.id,
                reference=base_transfer.reference,
                sender=base_transfer.sender,
                recipient=base_transfer.recipient,
                quote=base_transfer.quote,
                declaration=base_transfer.declaration,
                state=from_state,
                created_at=base_transfer.created_at,
            )

            if (from_state, to_state) in LEGAL_TRANSITIONS:
                legal_count += 1
                next_t = orchestrator.transition(t, to_state)
                assert next_t.state == to_state
            else:
                illegal_count += 1
                with pytest.raises((ValueError, OrchestratorStateError)):
                    orchestrator.transition(t, to_state)

    assert legal_count == 7
    assert illegal_count == 29
    assert legal_count + illegal_count == 36


def test_orchestrator_retry_budget_bounded_at_two(base_transfer: Transfer) -> None:
    """FAILED -> SETTLING retry is allowed at most 2 times.
    3rd retry raises RetryBudgetExceededError.
    """
    orchestrator = MasterOrchestrator()

    # Move to SETTLING
    t = orchestrator.transition(base_transfer, TransferState.VALIDATED)
    t = orchestrator.transition(t, TransferState.SETTLING)

    # 1st Failure and Retry
    t = orchestrator.transition(t, TransferState.FAILED)
    t = orchestrator.retry_settlement(t, alternate_rail=SettlementRail.SWIFT)
    assert t.state == TransferState.SETTLING
    assert t.rail == SettlementRail.SWIFT
    assert orchestrator.get_retry_count(t.id) == 1

    # 2nd Failure and Retry
    t = orchestrator.transition(t, TransferState.FAILED)
    t = orchestrator.retry_settlement(t, alternate_rail=SettlementRail.RIPPLE)
    assert t.state == TransferState.SETTLING
    assert t.rail == SettlementRail.RIPPLE
    assert orchestrator.get_retry_count(t.id) == 2

    # 3rd Failure -> Retry exhausted
    t = orchestrator.transition(t, TransferState.FAILED)
    with pytest.raises(RetryBudgetExceededError, match="Retry budget exhausted"):
        orchestrator.retry_settlement(t, alternate_rail=SettlementRail.PAPSS)

    # State remains FAILED
    assert t.state == TransferState.FAILED


def test_orchestrator_has_no_llm_dependencies() -> None:
    """Master Orchestrator has zero LLM inference dependencies."""
    orchestrator = MasterOrchestrator()
    # Confirm it does not possess any prompt generation or LLM client methods
    assert not hasattr(orchestrator, "generate_prompt")
    assert not hasattr(orchestrator, "call_model")
    assert not hasattr(orchestrator, "llm_client")
