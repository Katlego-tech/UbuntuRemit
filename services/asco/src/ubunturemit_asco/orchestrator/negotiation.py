"""Multi-Agent Negotiation Coordinator -- docs/design/asco-orchestrator.md §4.

Coordinates the negotiation between Compliance Sentinel and Liquidity Strategist,
bounded strictly at 3 exchanges, with fail-closed error handling and audit logging.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ubunturemit_asco.agents.sentinel import ComplianceSentinel
from ubunturemit_asco.agents.strategist import LiquidityStrategist
from ubunturemit_asco.guardrails.exit import ExitValidator
from ubunturemit_asco.models import (
    AuditRecord,
    ComplianceAssessmentInput,
    LiquidityProposal,
    LiquidityRequestInput,
    RailQuote,
    VerdictOutcome,
)
from ubunturemit_asco.orchestrator.master import MasterOrchestrator
from ubunturemit_domain import Transfer, TransferState
from ubunturemit_messaging.pacs008 import build_pacs008

MAX_NEGOTIATION_EXCHANGES: int = 3


class AuditLogger(Protocol):
    """Protocol for append-only audit record logging (e.g. Kafka asco.audit)."""

    def log_record(self, record: AuditRecord) -> None:
        """Log an audit record to the audit store."""
        ...


class InMemoryAuditLogger:
    """In-memory audit logger for testing and simulation."""

    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def log_record(self, record: AuditRecord) -> None:
        self.records.append(record)


@dataclass(frozen=True, slots=True)
class NegotiationResult:
    """Final outcome of the ASCO negotiation loop."""

    transfer: Transfer
    outcome: str  # "SETTLING", "PENDING_REVIEW", "REJECTED", "FAILED"
    pacs008_xml: str | None = None
    proposal: LiquidityProposal | None = None
    audit_records: list[AuditRecord] = ()
    reason: str = ""


class NegotiationCoordinator:
    """Coordinates the 3-party negotiation (MO <-> CS <-> LS) under strict budgets."""

    def __init__(
        self,
        master_orchestrator: MasterOrchestrator | None = None,
        compliance_sentinel: ComplianceSentinel | None = None,
        liquidity_strategist: LiquidityStrategist | None = None,
        exit_validator: ExitValidator | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self._mo = master_orchestrator or MasterOrchestrator()
        self._cs = compliance_sentinel or ComplianceSentinel()
        self._ls = liquidity_strategist or LiquidityStrategist()
        self._xv = exit_validator or ExitValidator()
        self._audit = audit_logger or InMemoryAuditLogger()

    def negotiate_and_settle(
        self,
        transfer: Transfer,
        assessment_input: ComplianceAssessmentInput,
        rail_quotes: list[RailQuote],
    ) -> NegotiationResult:
        """Run the ASCO negotiation loop per sequence diagram in asco-orchestrator.md §4."""
        audit_trail: list[AuditRecord] = []

        def _record(
            actor: str,
            thought: str,
            action: str,
            observation: str,
            override: bool = False,
        ) -> None:
            rec = AuditRecord(
                transfer_id=transfer.id,
                actor=actor,
                thought=thought,
                action=action,
                observation=observation,
                recorded_at=datetime.now(UTC).isoformat(),
                deterministic_override=override,
            )
            audit_trail.append(rec)
            # Log to Kafka / audit sink immediately; fail-closed if audit sink fails
            self._audit.log_record(rec)

        current_transfer = transfer
        exchanges = 0

        # Round 1: Compliance Sentinel initial assessment
        exchanges += 1
        verdict, cs_thought, cs_action = self._cs.assess(assessment_input)
        obs = (
            f"Verdict outcome: {verdict.outcome}, riskScore: {verdict.risk_score}, "
            f"citedRules: {verdict.cited_rules}"
        )
        _record(
            actor="compliance_sentinel",
            thought=cs_thought,
            action=cs_action,
            observation=obs,
        )

        if verdict.outcome == VerdictOutcome.BLOCK:
            current_transfer = self._mo.transition(current_transfer, TransferState.REJECTED)
            _record(
                actor="orchestrator",
                thought="Compliance Sentinel blocked transfer",
                action="Transition transfer to REJECTED",
                observation=f"Rejection cited: {verdict.cited_rules}",
            )
            return NegotiationResult(
                transfer=current_transfer,
                outcome="REJECTED",
                audit_records=audit_trail,
                reason=f"Blocked by Compliance Sentinel: {verdict.rationale}",
            )

        if verdict.outcome == VerdictOutcome.ESCALATE:
            # ESCALATE is terminal for agent loop -> routes to human queue
            _record(
                actor="orchestrator",
                thought="Compliance Sentinel requested human escalation",
                action="Route transfer to human review queue",
                observation=f"Escalation rationale: {verdict.rationale}",
            )
            return NegotiationResult(
                transfer=current_transfer,
                outcome="PENDING_REVIEW",
                audit_records=audit_trail,
                reason=f"Escalated for human review: {verdict.rationale}",
            )

        # Verdict is PASS -> Move to VALIDATED
        current_transfer = self._mo.transition(current_transfer, TransferState.VALIDATED)
        _record(
            actor="orchestrator",
            thought="Compliance check passed; evaluating liquidity proposals",
            action="Transition transfer to VALIDATED",
            observation=f"Transfer {current_transfer.reference} is VALIDATED",
        )

        # Liquidity Strategist Proposal Loop
        active_constraints = verdict.constraints
        proposal: LiquidityProposal | None = None

        while exchanges < MAX_NEGOTIATION_EXCHANGES:
            exchanges += 1
            req_input = LiquidityRequestInput(
                transfer_id=current_transfer.id,
                corridor_source=current_transfer.quote.send.currency,
                corridor_target=current_transfer.quote.recipient_receives.currency,
                amount=current_transfer.quote.send,
                rail_quotes=rail_quotes,
                constraints=active_constraints,
            )
            proposal, ls_thought, ls_action = self._ls.propose(req_input)
            ls_obs = (
                f"Proposed rail: {proposal.rail}, cost: {proposal.total_cost.minor_units}, "
                f"estSec: {proposal.estimated_seconds}"
            )
            _record(
                actor="liquidity_strategist",
                thought=ls_thought,
                action=ls_action,
                observation=ls_obs,
            )
            break

        if proposal is None or exchanges > MAX_NEGOTIATION_EXCHANGES:
            # Budget exhausted -> ESCALATE
            _record(
                actor="orchestrator",
                thought="Negotiation exceeded 3 exchanges budget",
                action="Escalate to human review",
                observation="Exchange budget exhausted",
                override=True,
            )
            return NegotiationResult(
                transfer=current_transfer,
                outcome="PENDING_REVIEW",
                audit_records=audit_trail,
                reason="Negotiation exchange budget exhausted. Escalating to human queue.",
            )

        # Build pacs.008 instruction with chosen rail
        updated_transfer = Transfer(
            id=current_transfer.id,
            reference=current_transfer.reference,
            sender=current_transfer.sender,
            recipient=current_transfer.recipient,
            quote=current_transfer.quote,
            declaration=current_transfer.declaration,
            state=current_transfer.state,
            created_at=current_transfer.created_at,
            rail=proposal.rail,
        )
        pacs008_xml = build_pacs008(updated_transfer)

        # Exit Validator Gate
        exit_result = self._xv.validate(
            transfer=updated_transfer,
            verdict=verdict,
            proposal=proposal,
            rail_quotes=rail_quotes,
            pacs008_xml=pacs008_xml,
        )
        _record(
            actor="exit_validator",
            thought="Validating citations, rail constraints, and pacs.008 schema",
            action="Run deterministic exit validation",
            observation=f"Exit verdict valid={exit_result.valid}, stage={exit_result.stage}",
            override=exit_result.deterministic_override,
        )

        if not exit_result.valid:
            rejected_t = self._mo.transition(updated_transfer, TransferState.REJECTED)
            return NegotiationResult(
                transfer=rejected_t,
                outcome="REJECTED",
                proposal=proposal,
                pacs008_xml=pacs008_xml,
                audit_records=audit_trail,
                reason=f"Exit validation failed: {exit_result.reason}",
            )

        # Move to SETTLING
        settling_t = self._mo.transition(updated_transfer, TransferState.SETTLING)
        _record(
            actor="orchestrator",
            thought="Exit validation clear; submitting pacs.008 to rail adapter",
            action="Transition transfer to SETTLING",
            observation=f"Submitted to {proposal.rail}",
        )

        return NegotiationResult(
            transfer=settling_t,
            outcome="SETTLING",
            proposal=proposal,
            pacs008_xml=pacs008_xml,
            audit_records=audit_trail,
            reason="Transfer successfully negotiated and submitted for settlement.",
        )
