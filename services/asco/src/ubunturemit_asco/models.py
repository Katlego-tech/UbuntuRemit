"""Data models and JSON contracts for ASCO agents and guardrails.
Docs: docs/design/asco-orchestrator.md §5.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from ubunturemit_domain import (
    CurrencyCode,
    Money,
    PaymentPurpose,
    SettlementRail,
    SourceOfFunds,
    TransferId,
)


class VerdictOutcome(StrEnum):
    """Compliance verdict outcome -- domain-model.md §5."""

    PASS = "PASS"  # noqa: S105
    ESCALATE = "ESCALATE"
    BLOCK = "BLOCK"


@dataclass(frozen=True, slots=True)
class ComplianceConstraints:
    """Constraints imposed by Compliance Sentinel on Liquidity Strategist."""

    forbidden_rails: list[SettlementRail] = field(default_factory=list)
    max_settlement_seconds: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ComplianceAssessmentInput:
    """Input payload from Master Orchestrator to Compliance Sentinel."""

    transfer_id: TransferId
    corridor_source: CurrencyCode
    corridor_target: CurrencyCode
    amount: Money
    purpose: PaymentPurpose
    source_of_funds: SourceOfFunds
    sender_kyc_tier: str
    sender_country: str
    sender_is_pep: bool
    recipient_country: str
    recipient_account_age_days: int
    prior_transfers_30d_count: int = 0
    prior_transfers_30d_minor_units: int = 0


@dataclass(frozen=True, slots=True)
class ComplianceVerdict:
    """Verdict emitted by Compliance Sentinel -- asco-orchestrator.md §5.

    Non-negotiable I: cited_rules MUST NOT be empty.
    """

    outcome: VerdictOutcome
    risk_score: Decimal
    cited_rules: list[str]
    rationale: str
    constraints: ComplianceConstraints = field(default_factory=ComplianceConstraints)

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, VerdictOutcome):
            raise TypeError(f"outcome must be a VerdictOutcome, got {type(self.outcome).__name__}")
        if not isinstance(self.risk_score, Decimal):
            raise TypeError(f"risk_score must be a Decimal, got {type(self.risk_score).__name__}")
        if not (Decimal("0.0") <= self.risk_score <= Decimal("1.0")):
            raise ValueError(f"risk_score must be between 0.0 and 1.0, got {self.risk_score}")

        if not self.cited_rules or len(self.cited_rules) == 0:
            raise ValueError(
                "cited_rules must contain at least one cited rule. "
                "An uncited compliance verdict cannot be constructed (Non-negotiable I)."
            )
        for rule in self.cited_rules:
            if not isinstance(rule, str) or not rule.strip():
                raise ValueError("Each cited rule must be a non-blank string.")

        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise ValueError("rationale must not be blank.")
        if len(self.rationale) > 600:
            raise ValueError(f"rationale exceeds 600 chars ({len(self.rationale)} chars).")


@dataclass(frozen=True, slots=True)
class RailQuote:
    """Real market quote for a specific settlement rail."""

    rail: SettlementRail
    fee_minor_units: int
    spread_bps: int
    estimated_seconds: Decimal


@dataclass(frozen=True, slots=True)
class LiquidityRequestInput:
    """Input payload from Master Orchestrator to Liquidity Strategist."""

    transfer_id: TransferId
    corridor_source: CurrencyCode
    corridor_target: CurrencyCode
    amount: Money
    rail_quotes: list[RailQuote]
    constraints: ComplianceConstraints = field(default_factory=ComplianceConstraints)

    def __post_init__(self) -> None:
        if not self.rail_quotes:
            raise ValueError("rail_quotes must not be empty.")


@dataclass(frozen=True, slots=True)
class LiquidityProposal:
    """Proposal emitted by Liquidity Strategist -- asco-orchestrator.md §5."""

    rail: SettlementRail
    total_cost: Money
    estimated_seconds: Decimal
    rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.rail, SettlementRail):
            raise TypeError(f"rail must be a SettlementRail, got {type(self.rail).__name__}")
        if not isinstance(self.total_cost, Money):
            raise TypeError(f"total_cost must be Money, got {type(self.total_cost).__name__}")
        if not isinstance(self.estimated_seconds, Decimal) or self.estimated_seconds <= 0:
            raise ValueError(
                f"estimated_seconds must be a positive Decimal, got {self.estimated_seconds}"
            )
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise ValueError("rationale must not be blank.")
        if len(self.rationale) > 400:
            raise ValueError(f"rationale exceeds 400 chars ({len(self.rationale)} chars).")


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """Append-only audit record per agent turn -- domain-model.md §3 & SARB PEM."""

    transfer_id: TransferId
    # actor: "entry_guardrail" | "compliance_sentinel" | "liquidity_strategist"
    #        | "exit_validator" | "orchestrator"
    actor: str
    thought: str
    action: str
    observation: str
    recorded_at: str
    deterministic_override: bool = False
