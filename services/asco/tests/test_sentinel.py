"""Tests for Compliance Sentinel agent (T043).

Rules per docs/design/asco-orchestrator.md §5:
- ComplianceVerdict requires outcome, riskScore, citedRules (min length 1), rationale.
- Non-negotiable I: an empty citedRules cannot be constructed.
- Malformed model output is re-asked once with schema, second failure escalates.
- Inference timeout fails closed -> ESCALATE.
"""

import json
from decimal import Decimal

import pytest
from ubunturemit_asco.agents.sentinel import (
    ComplianceSentinel,
    InferenceTimeoutError,
)
from ubunturemit_asco.models import (
    ComplianceAssessmentInput,
    ComplianceVerdict,
    VerdictOutcome,
)
from ubunturemit_domain import (
    CurrencyCode,
    Money,
    PaymentPurpose,
    SourceOfFunds,
    TransferId,
)


@pytest.fixture
def sample_input() -> ComplianceAssessmentInput:
    return ComplianceAssessmentInput(
        transfer_id=TransferId("TR-99420-001"),
        corridor_source=CurrencyCode.ZAR,
        corridor_target=CurrencyCode.KES,
        amount=Money(minor_units=1500000, currency=CurrencyCode.ZAR),
        purpose=PaymentPurpose.FAMILY_SUPPORT,
        source_of_funds=SourceOfFunds.EMPLOYMENT_SALARY,
        sender_kyc_tier="L3",
        sender_country="ZA",
        sender_is_pep=False,
        recipient_country="KE",
        recipient_account_age_days=412,
        prior_transfers_30d_count=4,
        prior_transfers_30d_minor_units=4200000,
    )


class MockLLMClient:
    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = list(responses)
        self.call_count = 0

    def complete(self, prompt: str, system_prompt: str) -> str:
        self.call_count += 1
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def test_compliance_verdict_cannot_be_constructed_with_empty_cited_rules() -> None:
    """Non-negotiable I: ComplianceVerdict with empty citedRules raises ValueError."""
    with pytest.raises(ValueError, match="cited_rules must contain at least one cited rule"):
        ComplianceVerdict(
            outcome=VerdictOutcome.PASS,
            risk_score=Decimal("0.1"),
            cited_rules=[],
            rationale="No rules cited.",
        )


def test_compliance_sentinel_valid_llm_response(sample_input: ComplianceAssessmentInput) -> None:
    """Sentinel parses valid JSON matching schema and returns ComplianceVerdict."""
    valid_json = json.dumps(
        {
            "outcome": "PASS",
            "riskScore": 0.15,
            "citedRules": ["FICA s21", "SARB EXCON B.4"],
            "rationale": "Transfer compliant with limits and verified KYC.",
            "constraints": {
                "forbiddenRails": ["SWIFT"],
                "maxSettlementSeconds": 5.0,
            },
        }
    )
    mock_client = MockLLMClient([valid_json])
    sentinel = ComplianceSentinel(llm_client=mock_client)

    verdict, thought, action = sentinel.assess(sample_input)

    assert verdict.outcome == VerdictOutcome.PASS
    assert verdict.risk_score == Decimal("0.15")
    assert verdict.cited_rules == ["FICA s21", "SARB EXCON B.4"]
    assert mock_client.call_count == 1


def test_compliance_sentinel_malformed_json_retries_once_then_escalates(
    sample_input: ComplianceAssessmentInput,
) -> None:
    """Malformed output is re-asked once; second failure escalates to human queue."""
    mock_client = MockLLMClient(["invalid json output", "still invalid json"])
    sentinel = ComplianceSentinel(llm_client=mock_client)

    verdict, thought, action = sentinel.assess(sample_input)

    assert mock_client.call_count == 2
    assert verdict.outcome == VerdictOutcome.ESCALATE
    assert "MALFORMED_OUTPUT_ESCALATE" in verdict.cited_rules


def test_compliance_sentinel_timeout_fails_closed(sample_input: ComplianceAssessmentInput) -> None:
    """Inference timeout fails closed to ESCALATE (never default allow)."""
    mock_client = MockLLMClient([InferenceTimeoutError("MI300X vLLM inference timeout")])
    sentinel = ComplianceSentinel(llm_client=mock_client)

    verdict, thought, action = sentinel.assess(sample_input)

    assert verdict.outcome == VerdictOutcome.ESCALATE
    assert "INFERENCE_TIMEOUT_FAIL_CLOSED" in verdict.cited_rules
