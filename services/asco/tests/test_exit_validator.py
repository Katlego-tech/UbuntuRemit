"""Tests for Exit Validator guardrail (T045).

Rules per docs/design/asco-orchestrator.md §3, §5:
- Guardrail bypass test: crafted approval with empty citedRules rejected.
- Fabricated rail test: rail absent from quotes rejected with deterministicOverride=True.
- Forbidden rail test: rail violating constraints rejected with deterministicOverride=True.
- pacs.008 schema validation.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ubunturemit_asco.guardrails.exit import ExitValidator
from ubunturemit_asco.models import (
    ComplianceConstraints,
    ComplianceVerdict,
    LiquidityProposal,
    RailQuote,
    VerdictOutcome,
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
from ubunturemit_messaging.pacs008 import build_pacs008


@pytest.fixture
def canonical_transfer() -> Transfer:
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
            purpose=PaymentPurpose.FAMILY_SUPPORT,
            source_of_funds=SourceOfFunds.EMPLOYMENT_SALARY,
        ),
        state=TransferState.VALIDATED,
        created_at=datetime(2026, 8, 31, 10, 5, 0, tzinfo=UTC),
        rail=SettlementRail.PAPSS,
    )


def test_exit_validator_passes_compliant_transfer(canonical_transfer: Transfer) -> None:
    """Exit validator passes when all citation, rail, and pacs.008 schema checks pass."""
    validator = ExitValidator()
    verdict = ComplianceVerdict(
        outcome=VerdictOutcome.PASS,
        risk_score=Decimal("0.1"),
        cited_rules=["FICA_S21", "SARB_EXCON_B4"],
        rationale="Compliant transfer.",
    )
    proposal = LiquidityProposal(
        rail=SettlementRail.PAPSS,
        total_cost=Money(minor_units=1200, currency=CurrencyCode.ZAR),
        estimated_seconds=Decimal("11.0"),
        rationale="PAPSS selected.",
    )
    quotes = [
        RailQuote(
            rail=SettlementRail.PAPSS,
            fee_minor_units=1200,
            spread_bps=8,
            estimated_seconds=Decimal("11.0"),
        )
    ]
    pacs_xml = build_pacs008(canonical_transfer)

    result = validator.validate(
        transfer=canonical_transfer,
        verdict=verdict,
        proposal=proposal,
        rail_quotes=quotes,
        pacs008_xml=pacs_xml,
    )

    assert result.valid is True
    assert result.deterministic_override is False
    assert result.stage == "CLEAR"


def test_exit_validator_rejects_fabricated_rail(canonical_transfer: Transfer) -> None:
    """Proposal naming a rail absent from railQuotes is rejected with deterministicOverride=True."""
    validator = ExitValidator()
    verdict = ComplianceVerdict(
        outcome=VerdictOutcome.PASS,
        risk_score=Decimal("0.1"),
        cited_rules=["FICA_S21"],
        rationale="Compliant.",
    )
    # Model proposes RIPPLE, but only PAPSS was offered
    proposal = LiquidityProposal(
        rail=SettlementRail.RIPPLE,
        total_cost=Money(minor_units=0, currency=CurrencyCode.ZAR),
        estimated_seconds=Decimal("3.0"),
        rationale="Invented ripple rail.",
    )
    quotes = [
        RailQuote(
            rail=SettlementRail.PAPSS,
            fee_minor_units=1200,
            spread_bps=8,
            estimated_seconds=Decimal("11.0"),
        )
    ]

    result = validator.validate(
        transfer=canonical_transfer,
        verdict=verdict,
        proposal=proposal,
        rail_quotes=quotes,
    )

    assert result.valid is False
    assert result.deterministic_override is True
    assert result.stage == "RAIL_ELIGIBILITY"
    assert "fabricated rail" in result.reason


def test_exit_validator_rejects_forbidden_rail(canonical_transfer: Transfer) -> None:
    """Proposal selecting a rail forbidden by compliance constraints is rejected."""
    validator = ExitValidator()
    verdict = ComplianceVerdict(
        outcome=VerdictOutcome.PASS,
        risk_score=Decimal("0.1"),
        cited_rules=["FICA_S21"],
        rationale="Compliant.",
        constraints=ComplianceConstraints(forbidden_rails=[SettlementRail.SWIFT]),
    )
    proposal = LiquidityProposal(
        rail=SettlementRail.SWIFT,
        total_cost=Money(minor_units=5000, currency=CurrencyCode.ZAR),
        estimated_seconds=Decimal("20.0"),
        rationale="Selected SWIFT.",
    )
    quotes = [
        RailQuote(
            rail=SettlementRail.SWIFT,
            fee_minor_units=5000,
            spread_bps=20,
            estimated_seconds=Decimal("20.0"),
        )
    ]

    result = validator.validate(
        transfer=canonical_transfer,
        verdict=verdict,
        proposal=proposal,
        rail_quotes=quotes,
    )

    assert result.valid is False
    assert result.deterministic_override is True
    assert "violates constraint" in result.reason
