"""Deterministic ASCO Exit Validator -- docs/design/asco-orchestrator.md §3, §4, §5.

Hard exit gates (deterministic, zero LLM):
1. Verdict citation check (ensures no uncited PASS/BLOCK).
2. Rail eligibility re-check (ensures proposed rail was in quotes and not forbidden).
3. ISO 20022 pacs.008 message validation.

If the rule-based validator overrules an LLM proposal, deterministicOverride is set to True.
"""

from dataclasses import dataclass
from pathlib import Path

from lxml import etree
from ubunturemit_asco.models import (
    ComplianceVerdict,
    LiquidityProposal,
    RailQuote,
    VerdictOutcome,
)
from ubunturemit_domain import Transfer

SCHEMAS_DIR = Path(__file__).resolve().parents[4] / "messaging" / "schemas"
PACS008_XSD_PATH = SCHEMAS_DIR / "pacs.008.001.08.xsd"


@dataclass(frozen=True, slots=True)
class ExitValidationResult:
    """Verdict emitted by the Exit Validator."""

    valid: bool
    stage: str  # "CLEAR", "CITATION_CHECK", "RAIL_ELIGIBILITY", "ISO20022_SCHEMA"
    deterministic_override: bool
    reason: str


class ExitValidator:
    """Deterministic exit gate verifying LLM negotiation conclusions before rail dispatch."""

    def validate(
        self,
        transfer: Transfer,
        verdict: ComplianceVerdict,
        proposal: LiquidityProposal | None = None,
        rail_quotes: list[RailQuote] | None = None,
        pacs008_xml: str | None = None,
    ) -> ExitValidationResult:
        """Validate agent outputs and pacs.008 payload against hard exit rules."""
        # 1. Verdict Citation Check
        if not verdict.cited_rules or len(verdict.cited_rules) == 0:
            return ExitValidationResult(
                valid=False,
                stage="CITATION_CHECK",
                deterministic_override=True,
                reason=(
                    "Compliance verdict has empty citedRules. "
                    "Uncited approvals are strictly forbidden (Non-negotiable I)."
                ),
            )

        if verdict.outcome == VerdictOutcome.BLOCK:
            return ExitValidationResult(
                valid=False,
                stage="CITATION_CHECK",
                deterministic_override=False,
                reason=f"Transfer blocked by Compliance Sentinel: {verdict.rationale}",
            )

        if verdict.outcome == VerdictOutcome.ESCALATE:
            return ExitValidationResult(
                valid=False,
                stage="CITATION_CHECK",
                deterministic_override=False,
                reason=f"Transfer escalated for human review: {verdict.rationale}",
            )

        # 2. Rail Eligibility and Constraint Check
        if proposal is not None:
            quotes = rail_quotes or []
            offered_rails = {q.rail for q in quotes}
            if offered_rails and proposal.rail not in offered_rails:
                return ExitValidationResult(
                    valid=False,
                    stage="RAIL_ELIGIBILITY",
                    deterministic_override=True,
                    reason=(
                        f"Proposed rail '{proposal.rail}' was not among offered quotes "
                        "(fabricated rail)."
                    ),
                )

            forbidden = set(verdict.constraints.forbidden_rails)
            if proposal.rail in forbidden:
                return ExitValidationResult(
                    valid=False,
                    stage="RAIL_ELIGIBILITY",
                    deterministic_override=True,
                    reason=(
                        f"Proposed rail '{proposal.rail}' violates constraint "
                        f"(forbidden rails: {list(forbidden)})."
                    ),
                )

            if verdict.constraints.max_settlement_seconds is not None:
                if proposal.estimated_seconds > verdict.constraints.max_settlement_seconds:
                    return ExitValidationResult(
                        valid=False,
                        stage="RAIL_ELIGIBILITY",
                        deterministic_override=True,
                        reason=(
                            f"Proposed latency ({proposal.estimated_seconds}s) exceeds max "
                            f"allowed seconds ({verdict.constraints.max_settlement_seconds}s)."
                        ),
                    )

        # 3. ISO 20022 pacs.008 Schema Validation
        if pacs008_xml is not None:
            try:
                doc = etree.fromstring(pacs008_xml.encode("utf-8"))
                schema_doc = etree.parse(str(PACS008_XSD_PATH))
                xmlschema = etree.XMLSchema(schema_doc)
                if not xmlschema.validate(doc):
                    return ExitValidationResult(
                        valid=False,
                        stage="ISO20022_SCHEMA",
                        deterministic_override=True,
                        reason=f"pacs.008 payload failed XSD validation: {xmlschema.error_log}",
                    )
            except Exception as err:
                return ExitValidationResult(
                    valid=False,
                    stage="ISO20022_SCHEMA",
                    deterministic_override=True,
                    reason=f"Failed to validate pacs.008 XML schema: {err}",
                )

        return ExitValidationResult(
            valid=True,
            stage="CLEAR",
            deterministic_override=False,
            reason="All exit validation checks passed successfully.",
        )
