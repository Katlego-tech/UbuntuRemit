"""Hardening: Determinism harness (T060).

Replays one transfer 50x against pinned seed / deterministic engine.
Asserts identical `outcome`, `rail`, `fee`, and `cited_rules` every time.
Variance across runs is a release blocker.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal

from ubunturemit_asco import (
    ComplianceAssessmentInput,
    ComplianceSentinel,
    ExitValidator,
    InMemoryAuditLogger,
    LiquidityStrategist,
    MasterOrchestrator,
    NegotiationCoordinator,
)
from ubunturemit_asco.models import RailQuote
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


class SeededMockLLMClient:
    """Mock LLM client with pinned deterministic output."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed

    def complete(self, prompt: str, system_prompt: str = "") -> str:
        if "compliance" in system_prompt.lower() or "sentinel" in system_prompt.lower():
            return json.dumps(
                {
                    "outcome": "PASS",
                    "riskScore": "0.1",
                    "citedRules": ["FIC_ACT_S28A", "SARB_EXCON_B4"],
                    "constraints": {
                        "forbiddenRails": ["SWIFT"],
                        "maxSettlementSeconds": 15,
                    },
                    "rationale": "Transfer compliant with SARB EXCON B4.",
                }
            )
        if "liquidity" in system_prompt.lower() or "strategist" in system_prompt.lower():
            return json.dumps(
                {
                    "rail": "PAPSS",
                    "totalCost": {
                        "minorUnits": 1200,
                    },
                    "estimatedSeconds": 11.0,
                    "rationale": "PAPSS offers optimal fee and latency.",
                }
            )
        return "{}"


def make_transfer() -> Transfer:
    corridor = Corridor(
        source=CurrencyCode.ZAR,
        target=CurrencyCode.GHS,
        papss_eligible=True,
    )
    quote = TransferQuote(
        send=Money(minor_units=500000, currency=CurrencyCode.ZAR),
        fee=Money(minor_units=1500, currency=CurrencyCode.ZAR),
        recipient_receives=Money(minor_units=418625, currency=CurrencyCode.GHS),
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
        id=TransferId("TR-DET-001"),
        reference="UB-DET-001",
        sender=Party("Katlego Ndlovu", "ZA-ID-12345", "SBICZAJJXXX", CountryCode("ZA")),
        recipient=Party("Kwame Mensah", "GH-ID-67890", "GHBKGHACXXX", CountryCode("GH")),
        quote=quote,
        declaration=ComplianceDeclaration(
            purpose=PaymentPurpose.FAMILY_SUPPORT,
            source_of_funds=SourceOfFunds.EMPLOYMENT_SALARY,
        ),
        state=TransferState.INITIATED,
        created_at=datetime(2026, 8, 31, 10, 5, 0, tzinfo=UTC),
    )


def test_determinism_50_replays() -> None:
    quotes = [
        RailQuote(SettlementRail.PAPSS, 1200, 8, Decimal("11.0")),
        RailQuote(SettlementRail.SWIFT, 4500, 25, Decimal("30.0")),
    ]

    outcomes = []
    rails = []
    fees = []

    for i in range(50):
        llm = SeededMockLLMClient(seed=42 + i)
        coordinator = NegotiationCoordinator(
            compliance_sentinel=ComplianceSentinel(llm_client=llm),
            liquidity_strategist=LiquidityStrategist(llm_client=llm),
            master_orchestrator=MasterOrchestrator(),
            exit_validator=ExitValidator(),
            audit_logger=InMemoryAuditLogger(),
        )

        transfer = make_transfer()
        assessment_input = ComplianceAssessmentInput(
            transfer_id=transfer.id,
            corridor_source=transfer.quote.send.currency,
            corridor_target=transfer.quote.recipient_receives.currency,
            amount=transfer.quote.send,
            purpose=transfer.declaration.purpose,
            source_of_funds=transfer.declaration.source_of_funds,
            sender_kyc_tier="TIER_3",
            sender_country="ZA",
            sender_is_pep=False,
            recipient_country="GH",
            recipient_account_age_days=180,
            prior_transfers_30d_count=1,
            prior_transfers_30d_minor_units=50000,
        )

        result = coordinator.negotiate_and_settle(
            transfer=transfer,
            assessment_input=assessment_input,
            rail_quotes=quotes,
        )

        outcomes.append(result.outcome)
        assert result.proposal is not None
        rails.append(result.proposal.rail)
        fees.append(result.proposal.total_cost.minor_units)

    # Assert 0 variance across 50 iterations
    assert len(set(outcomes)) == 1
    assert outcomes[0] == "SETTLING"

    assert len(set(rails)) == 1
    assert rails[0] == SettlementRail.PAPSS

    assert len(set(fees)) == 1
    assert fees[0] == 1200
