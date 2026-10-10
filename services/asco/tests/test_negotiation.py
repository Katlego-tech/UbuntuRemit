"""Tests for Negotiation Coordinator and fail-closed behaviors (T046, T047).

Rules per docs/design/asco-orchestrator.md §4:
- Negotiation bounded strictly at 3 exchanges; exhaustion escalates.
- Inference timeout -> ESCALATE (never default allow).
- Kafka / audit logger down -> Refuse transfer (an unauditable settlement is refused).
- Every participant actor logs AuditRecord.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from conftest import MockLLMClient
from ubunturemit_asco.agents.sentinel import (
    ComplianceSentinel,
    InferenceTimeoutError,
)
from ubunturemit_asco.agents.strategist import LiquidityStrategist
from ubunturemit_asco.models import (
    ComplianceAssessmentInput,
    RailQuote,
)
from ubunturemit_asco.orchestrator.negotiation import (
    InMemoryAuditLogger,
    NegotiationCoordinator,
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
def transfer_and_assessment() -> tuple[Transfer, ComplianceAssessmentInput, list[RailQuote]]:
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
    transfer = Transfer(
        id=TransferId("TR-99420-001"),
        reference="UB-99420-X",
        sender=sender,
        recipient=recipient,
        quote=quote,
        declaration=declaration,
        state=TransferState.INITIATED,
        created_at=datetime(2026, 8, 31, 10, 5, 0, tzinfo=UTC),
    )
    inp = ComplianceAssessmentInput(
        transfer_id=transfer.id,
        corridor_source=CurrencyCode.ZAR,
        corridor_target=CurrencyCode.GHS,
        amount=transfer.quote.send,
        purpose=declaration.purpose,
        source_of_funds=declaration.source_of_funds,
        sender_kyc_tier="L3",
        sender_country="ZA",
        sender_is_pep=False,
        recipient_country="GH",
        recipient_account_age_days=300,
    )
    quotes = [
        RailQuote(
            rail=SettlementRail.PAPSS,
            fee_minor_units=1200,
            spread_bps=8,
            estimated_seconds=Decimal("11.0"),
        ),
        RailQuote(
            rail=SettlementRail.SWIFT,
            fee_minor_units=4500,
            spread_bps=25,
            estimated_seconds=Decimal("30.0"),
        ),
    ]
    return transfer, inp, quotes


def _passing_sentinel() -> ComplianceSentinel:
    """A Sentinel whose (mocked) model returns a cited PASS."""
    return ComplianceSentinel(
        llm_client=MockLLMClient(
            [
                json.dumps(
                    {
                        "outcome": "PASS",
                        "riskScore": 0.1,
                        "citedRules": ["FIC_ACT_S28A"],
                        "rationale": "Test verdict from a mocked model.",
                        "constraints": {"forbiddenRails": []},
                    }
                )
            ]
        )
    )


def _papss_strategist() -> LiquidityStrategist:
    """A Strategist whose (mocked) model proposes the offered PAPSS quote."""
    return LiquidityStrategist(
        llm_client=MockLLMClient(
            [
                json.dumps(
                    {
                        "rail": "PAPSS",
                        "totalCost": {"minorUnits": 1200, "currency": "ZAR"},
                        "estimatedSeconds": 11.0,
                        "rationale": "Test proposal from a mocked model.",
                    }
                )
            ]
        )
    )


def test_negotiation_happy_path(
    transfer_and_assessment: tuple[Transfer, ComplianceAssessmentInput, list[RailQuote]],
) -> None:
    """Negotiation loop executes cleanly: INITIATED -> VALIDATED -> SETTLING."""
    transfer, assessment_input, quotes = transfer_and_assessment
    audit_logger = InMemoryAuditLogger()

    coordinator = NegotiationCoordinator(
        compliance_sentinel=_passing_sentinel(),
        liquidity_strategist=_papss_strategist(),
        audit_logger=audit_logger,
    )
    result = coordinator.negotiate_and_settle(
        transfer=transfer,
        assessment_input=assessment_input,
        rail_quotes=quotes,
    )

    assert result.outcome == "SETTLING"
    assert result.transfer.state == TransferState.SETTLING
    assert result.transfer.rail == SettlementRail.PAPSS
    assert result.proposal is not None
    # Verify audit trail completeness
    # (records from Sentinel, Strategist, ExitValidator, Orchestrator)
    actors = {r.actor for r in audit_logger.records}
    assert "compliance_sentinel" in actors
    assert "liquidity_strategist" in actors
    assert "exit_validator" in actors
    assert "orchestrator" in actors


def test_negotiation_inference_timeout_fails_closed(
    transfer_and_assessment: tuple[Transfer, ComplianceAssessmentInput, list[RailQuote]],
) -> None:
    """Inference timeout causes fail-closed ESCALATE outcome."""
    transfer, assessment_input, quotes = transfer_and_assessment
    mock_sentinel_client = MockLLMClient([InferenceTimeoutError("vLLM timeout")])
    sentinel = ComplianceSentinel(llm_client=mock_sentinel_client)

    coordinator = NegotiationCoordinator(
        compliance_sentinel=sentinel,
        liquidity_strategist=_papss_strategist(),
    )
    result = coordinator.negotiate_and_settle(
        transfer=transfer,
        assessment_input=assessment_input,
        rail_quotes=quotes,
    )

    assert result.outcome == "PENDING_REVIEW"
    assert "Inference timeout" in result.reason or "Escalated" in result.reason


def test_negotiation_kafka_unavailable_refuses_transfer(
    transfer_and_assessment: tuple[Transfer, ComplianceAssessmentInput, list[RailQuote]],
) -> None:
    """If audit logger throws an error, transfer is refused (never settle without audit trail)."""
    transfer, assessment_input, quotes = transfer_and_assessment

    class BrokenKafkaLogger:
        def log_record(self, record) -> None:
            raise ConnectionError("Kafka cluster unavailable")

    coordinator = NegotiationCoordinator(
        compliance_sentinel=_passing_sentinel(),
        liquidity_strategist=_papss_strategist(),
        audit_logger=BrokenKafkaLogger(),
    )

    with pytest.raises(ConnectionError, match="Kafka cluster unavailable"):
        coordinator.negotiate_and_settle(
            transfer=transfer,
            assessment_input=assessment_input,
            rail_quotes=quotes,
        )


def test_negotiation_strategist_timeout_fails_closed(
    transfer_and_assessment: tuple[Transfer, ComplianceAssessmentInput, list[RailQuote]],
) -> None:
    """A Strategist inference timeout escalates like the Sentinel's -- never a 500, never settle."""
    transfer, assessment_input, quotes = transfer_and_assessment
    audit_logger = InMemoryAuditLogger()
    coordinator = NegotiationCoordinator(
        compliance_sentinel=_passing_sentinel(),
        liquidity_strategist=LiquidityStrategist(
            llm_client=MockLLMClient([InferenceTimeoutError("vLLM timeout")])
        ),
        audit_logger=audit_logger,
    )

    result = coordinator.negotiate_and_settle(
        transfer=transfer, assessment_input=assessment_input, rail_quotes=quotes
    )

    assert result.outcome == "PENDING_REVIEW"
    assert result.proposal is None
    assert any(r.deterministic_override for r in audit_logger.records)
