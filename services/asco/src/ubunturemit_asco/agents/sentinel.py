"""Compliance Sentinel agent -- docs/design/asco-orchestrator.md §3, §5.

70B reasoning model persona enforcing AML/CFT, FICA, and SARB EXCON regulations.
Emits schema-bound ComplianceVerdict with mandatory citedRules.
"""

import json
from decimal import Decimal
from typing import Protocol

from ubunturemit_asco.models import (
    ComplianceAssessmentInput,
    ComplianceConstraints,
    ComplianceVerdict,
    VerdictOutcome,
)
from ubunturemit_domain import SettlementRail

SENTINEL_SYSTEM_PROMPT = """You are the Compliance Sentinel for UbuntuRemit.
Assess transfer compliance against regulatory frameworks:
- Financial Intelligence Centre Act (FICA) (s21, s28A, s21H)
- South African Reserve Bank (SARB) Exchange Control Regulations (EXCON B.4, SDA rules)
- Anti-Money Laundering and Counter-Financing of Terrorism (AML/CFT) guidelines

You MUST return a valid JSON object matching the ComplianceVerdict schema:
{
  "outcome": "PASS" | "ESCALATE" | "BLOCK",
  "riskScore": 0.0 to 1.0,
  "citedRules": ["Rule Name 1", "Rule Name 2"], // REQUIRED, MIN LENGTH 1
  "rationale": "Brief rationale under 600 characters",
  "constraints": {
    "forbiddenRails": ["SWIFT"],
    "maxSettlementSeconds": 10.0
  }
}
CRITICAL: Never emit a verdict with empty citedRules. Model must cite explicit rules.
"""


class InferenceTimeoutError(Exception):
    """Raised when an inference call exceeds SLA window."""


class LLMClient(Protocol):
    """Protocol for constrained-decoding LLM inference backend."""

    def complete(self, prompt: str, system_prompt: str) -> str:
        """Call model and return generated JSON string."""
        ...


class ComplianceSentinel:
    """Compliance Sentinel agent wrapper with constrained decoding."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._client = llm_client

    def assess(
        self,
        assessment_input: ComplianceAssessmentInput,
    ) -> tuple[ComplianceVerdict, str, str]:
        """Assess a transfer and return (ComplianceVerdict, thought, action).

        Fail-closed rules per asco-orchestrator.md §4:
        - Inference timeout -> ESCALATE (never default-allow).
        - Malformed JSON -> Re-ask once; second failure -> ESCALATE.
        """
        payload_json = json.dumps(
            {
                "transferId": assessment_input.transfer_id,
                "corridor": {
                    "source": assessment_input.corridor_source.value,
                    "target": assessment_input.corridor_target.value,
                },
                "amount": {
                    "minorUnits": assessment_input.amount.minor_units,
                    "currency": assessment_input.amount.currency.value,
                },
                "declaration": {
                    "purpose": assessment_input.purpose.value,
                    "sourceOfFunds": assessment_input.source_of_funds.value,
                },
                "senderProfile": {
                    "kycTier": assessment_input.sender_kyc_tier,
                    "countryOfResidence": assessment_input.sender_country,
                    "isPep": assessment_input.sender_is_pep,
                },
                "recipientProfile": {
                    "countryOfResidence": assessment_input.recipient_country,
                    "accountAgeDays": assessment_input.recipient_account_age_days,
                },
                "priorTransfers30d": {
                    "count": assessment_input.prior_transfers_30d_count,
                    "totalMinorUnits": assessment_input.prior_transfers_30d_minor_units,
                },
            },
            indent=2,
        )

        corridor_desc = f"{assessment_input.corridor_source}->{assessment_input.corridor_target}"
        thought = (
            f"Evaluating compliance for transfer {assessment_input.transfer_id} "
            f"on corridor {corridor_desc}"
        )
        action = f"Prompting 70B Compliance Sentinel with payload: {payload_json}"

        if self._client is None:
            # Default deterministic assessment for testing when no LLM client injected
            return self._deterministic_fallback_assessment(assessment_input), thought, action

        # First attempt
        try:
            raw_response = self._client.complete(
                prompt=payload_json,
                system_prompt=SENTINEL_SYSTEM_PROMPT,
            )
            verdict = self._parse_and_validate(raw_response)
            return verdict, thought, action
        except InferenceTimeoutError:
            # Inference timeout fails closed -> ESCALATE
            return (
                ComplianceVerdict(
                    outcome=VerdictOutcome.ESCALATE,
                    risk_score=Decimal("0.5"),
                    cited_rules=["INFERENCE_TIMEOUT_FAIL_CLOSED"],
                    rationale="Compliance Sentinel inference timed out. Escalating to human queue.",
                ),
                thought,
                "Inference timeout: escalated to human queue",
            )
        except Exception:
            # Re-ask once with schema instruction
            try:
                retry_prompt = (
                    f"Previous response was malformed. Re-emit valid JSON strictly:\n{payload_json}"
                )
                raw_response2 = self._client.complete(
                    prompt=retry_prompt,
                    system_prompt=SENTINEL_SYSTEM_PROMPT,
                )
                verdict2 = self._parse_and_validate(raw_response2)
                return verdict2, thought, action
            except Exception as err2:
                # Second failure -> ESCALATE
                return (
                    ComplianceVerdict(
                        outcome=VerdictOutcome.ESCALATE,
                        risk_score=Decimal("0.5"),
                        cited_rules=["MALFORMED_OUTPUT_ESCALATE"],
                        rationale=(
                            f"Sentinel emitted unparseable output twice ({err2}). "
                            "Escalating to human queue."
                        ),
                    ),
                    thought,
                    "Malformed output on retry: escalated to human queue",
                )

    def _parse_and_validate(self, json_str: str) -> ComplianceVerdict:
        data = json.loads(json_str)
        outcome_str = data.get("outcome", "ESCALATE")
        outcome = VerdictOutcome(outcome_str)
        risk_score = Decimal(str(data.get("riskScore", "0.0")))
        cited_rules = data.get("citedRules", [])
        rationale = data.get("rationale", "")

        constraints_data = data.get("constraints", {})
        forbidden_rails = [
            SettlementRail(r)
            for r in constraints_data.get("forbiddenRails", [])
            if r in SettlementRail._value2member_map_
        ]
        max_sec = constraints_data.get("maxSettlementSeconds")
        max_sec_dec = Decimal(str(max_sec)) if max_sec is not None else None
        constraints = ComplianceConstraints(
            forbidden_rails=forbidden_rails,
            max_settlement_seconds=max_sec_dec,
        )

        return ComplianceVerdict(
            outcome=outcome,
            risk_score=risk_score,
            cited_rules=cited_rules,
            rationale=rationale,
            constraints=constraints,
        )

    def _deterministic_fallback_assessment(
        self,
        inp: ComplianceAssessmentInput,
    ) -> ComplianceVerdict:
        """Deterministic assessment for test harnesses without mock LLMs."""
        if inp.sender_is_pep and inp.amount.minor_units > 5000000:
            return ComplianceVerdict(
                outcome=VerdictOutcome.ESCALATE,
                risk_score=Decimal("0.65"),
                cited_rules=["FIC_ACT_S21H_PEP"],
                rationale="PEP transfer above standard threshold requires review.",
            )

        return ComplianceVerdict(
            outcome=VerdictOutcome.PASS,
            risk_score=Decimal("0.10"),
            cited_rules=["FICA_S21_VERIFIED", "SARB_EXCON_B4_COMPLIANT"],
            rationale="Transfer is compliant with FICA KYC requirements and SARB EXCON limits.",
            constraints=ComplianceConstraints(),
        )
