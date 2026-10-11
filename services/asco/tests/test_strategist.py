"""Tests for Liquidity Strategist agent (T044).

Rules per docs/design/asco-orchestrator.md §5:
- LiquidityProposal requires rail, totalCost, estimatedSeconds, rationale.
- Model must select from provided railQuotes.
- A proposal naming an absent or forbidden rail is rejected.
"""

import json
from decimal import Decimal

import pytest
from conftest import MockLLMClient
from ubunturemit_asco.agents.sentinel import InferenceBackendMissingError
from ubunturemit_asco.agents.strategist import LiquidityStrategist
from ubunturemit_asco.models import (
    ComplianceConstraints,
    LiquidityRequestInput,
    RailQuote,
)
from ubunturemit_domain import (
    CurrencyCode,
    Money,
    SettlementRail,
    TransferId,
)


@pytest.fixture
def sample_request() -> LiquidityRequestInput:
    quotes = [
        RailQuote(
            rail=SettlementRail.RIPPLE,
            fee_minor_units=0,
            spread_bps=12,
            estimated_seconds=Decimal("3.2"),
        ),
        RailQuote(
            rail=SettlementRail.PAPSS,
            fee_minor_units=1200,
            spread_bps=8,
            estimated_seconds=Decimal("11.0"),
        ),
    ]
    return LiquidityRequestInput(
        transfer_id=TransferId("TR-99420-001"),
        corridor_source=CurrencyCode.ZAR,
        corridor_target=CurrencyCode.KES,
        amount=Money(minor_units=1500000, currency=CurrencyCode.ZAR),
        rail_quotes=quotes,
        constraints=ComplianceConstraints(forbidden_rails=[SettlementRail.SWIFT]),
    )


def test_liquidity_strategist_valid_proposal(sample_request: LiquidityRequestInput) -> None:
    """Strategist emits valid LiquidityProposal selecting an offered rail."""
    valid_json = json.dumps(
        {
            "rail": "RIPPLE",
            "totalCost": {"minorUnits": 1800, "currency": "ZAR"},
            "estimatedSeconds": 3.2,
            "rationale": "Selected Ripple for lowest total fee and fastest settlement under 5s.",
        }
    )
    mock_client = MockLLMClient([valid_json])
    strategist = LiquidityStrategist(llm_client=mock_client)

    proposal, thought, action = strategist.propose(sample_request)

    assert proposal.rail == SettlementRail.RIPPLE
    assert proposal.total_cost.minor_units == 1800
    assert proposal.estimated_seconds == Decimal("3.2")


def test_liquidity_strategist_without_inference_backend_refuses() -> None:
    """No model attached -> no Strategist. It never synthesises a proposal (Non-negotiable I)."""
    with pytest.raises(InferenceBackendMissingError):
        LiquidityStrategist(llm_client=None)  # type: ignore[arg-type]


def test_liquidity_strategist_missing_cost_is_never_defaulted(
    sample_request: LiquidityRequestInput,
) -> None:
    """A proposal with no totalCost is re-asked once, then raises -- never becomes cost 0."""
    no_cost = json.dumps({"rail": "RIPPLE", "estimatedSeconds": 3.2, "rationale": "Cheapest rail."})
    strategist = LiquidityStrategist(llm_client=MockLLMClient([no_cost, no_cost]))

    with pytest.raises(KeyError):
        strategist.propose(sample_request)
