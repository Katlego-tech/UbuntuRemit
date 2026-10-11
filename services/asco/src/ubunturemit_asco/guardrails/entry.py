"""Deterministic ASCO Entry Guardrail -- docs/design/asco-orchestrator.md §3, §4.

Hard Gates (deterministic, zero LLM):
1. Schema validation (pain.001 3-tier validation).
2. Sanctions and PEP screening (FIC Act s28A, UN/OFAC lists; PEP enhanced review).
3. Corridor support and KYC/SDA limits (SARB EXCON B.4, FICA Tier limits).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Protocol

from ubunturemit_domain import CurrencyCode, Transfer
from ubunturemit_messaging.pain001 import parse_pain001
from ubunturemit_messaging.validate import validate_pain001_message


class GuardrailOutcome(StrEnum):
    """Outcome of an entry/exit guardrail check."""

    PASS = "PASS"  # noqa: S105
    ESCALATE = "ESCALATE"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class SenderProfile:
    """Sender profile for compliance and limit evaluation."""

    kyc_tier: str  # "L1", "L2", "L3"
    country_of_residence: str
    is_pep: bool
    # No defaults: a zero is a claim about the sender's history (the SDA cumulative check
    # reads it), so the caller states it.
    prior_transfers_30d_count: int
    prior_transfers_30d_minor_units: int


@dataclass(frozen=True, slots=True)
class RecipientProfile:
    """Recipient profile for compliance and corridor evaluation."""

    country_of_residence: str
    account_age_days: int


@dataclass(frozen=True, slots=True)
class SanctionsListSource:
    """The list a screener holds: which list, as published on which date.

    A sanctions decision cites this, so a rejection names the list it matched against
    rather than claiming a list nobody loaded.
    """

    name: str  # e.g. "UN Security Council Consolidated List"
    published: date  # the list's own generation date, not the load date

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("A sanctions list source needs a name.")

    def citation(self) -> str:
        return f"SANCTIONS_LIST:{self.name}@{self.published.isoformat()}"


class EmptySanctionsListError(ValueError):
    """Raised when a screener is built over zero entries.

    Screening against nothing clears everyone and still writes an audit record saying
    the check ran -- worse than no check at all (T041a).
    """


class SanctionsScreener(Protocol):
    """Protocol for screening entities against deterministic sanctions lists."""

    @property
    def source(self) -> SanctionsListSource:
        """The named, dated list this screener holds."""
        ...

    def is_sanctioned(self, name: str, bic: str = "") -> bool:
        """Return True if the party matches any active sanctions list."""
        ...


class StaticSanctionsScreener:
    """Deterministic in-memory screener over a list loaded from a named, dated source."""

    def __init__(
        self,
        source: SanctionsListSource,
        sanctioned_names: Iterable[str],
        sanctioned_bics: Iterable[str] = (),
    ) -> None:
        self._source = source
        self._names = {n.strip().upper() for n in sanctioned_names if n.strip()}
        self._bics = {b.strip().upper() for b in sanctioned_bics if b.strip()}
        if not self._names and not self._bics:
            raise EmptySanctionsListError(
                f"Sanctions list '{source.name}' has no entries; refusing to screen against it."
            )

    @property
    def source(self) -> SanctionsListSource:
        return self._source

    def is_sanctioned(self, name: str, bic: str = "") -> bool:
        if name.strip().upper() in self._names:
            return True
        if bic and bic.strip().upper() in self._bics:
            return True
        return False


@dataclass(frozen=True, slots=True)
class EntryGuardrailResult:
    """Verdict emitted by the Entry Guardrail."""

    outcome: GuardrailOutcome
    stage: str  # "CLEAR", "SCHEMA", "SANCTIONS", "PEP_SCREEN", "LIMITS"
    cited_rules: list[str]
    transfer: Transfer | None = None
    rejection_reason: str | None = None


# Every rule ID the gates below can cite, in gate order. The compliance health endpoint
# reports this list, so it must name exactly what this file enforces -- the sanctions
# list itself is cited by its source (SanctionsListSource.citation), not listed here.
ENTRY_GATE_RULES: tuple[str, ...] = (
    "ISO_20022_PAIN001_SCHEMA",
    "ISO_20022_PARSER_ERROR",
    "FIC_ACT_S28A",
    "FIC_ACT_S21H_PEP",
    "FICA_TIER_LIMIT",
    "SARB_EXCON_LIMIT_EXCEEDED",
    "SARB_EXCON_SDA_CAP_EXCEEDED",
    "LIMIT_TABLE_UNAVAILABLE",
)

# SARB EXCON & FICA Tier limits in ZAR minor units (100 cents = 1 ZAR)
_TIER_SINGLE_LIMITS: dict[str, int] = {
    "L1": 500000,  # 5,000.00 ZAR
    "L2": 5000000,  # 50,000.00 ZAR
    "L3": 100000000,  # 1,000,000.00 ZAR (SDA annual single limit)
}

# Maximum Single Discretionary Allowance (SDA) 30d cumulative threshold
_MAX_SDA_CUMULATIVE_LIMIT: int = 100000000  # 1,000,000.00 ZAR

# PEP Enhanced Due Diligence single transaction threshold
_PEP_ENHANCED_DUE_DILIGENCE_THRESHOLD: int = 5000000  # 50,000.00 ZAR


class EntryGuardrail:
    """Deterministic entry gate preceding the ASCO multi-agent negotiation loop."""

    def __init__(self, sanctions_screener: SanctionsScreener) -> None:
        if sanctions_screener is None:
            raise EmptySanctionsListError(
                "EntryGuardrail needs a sanctions screener with a loaded list; "
                "it refuses to screen against nothing."
            )
        self._screener = sanctions_screener

    def evaluate(
        self,
        xml_input: str | bytes,
        sender_profile: SenderProfile,
        recipient_profile: RecipientProfile,
    ) -> EntryGuardrailResult:
        """Evaluate a pain.001 input against the hard entry gates."""
        # 1. Schema and Format Gate
        schema_verdict = validate_pain001_message(xml_input)
        if not schema_verdict.valid:
            return EntryGuardrailResult(
                outcome=GuardrailOutcome.REJECTED,
                stage="SCHEMA",
                cited_rules=["ISO_20022_PAIN001_SCHEMA"],
                rejection_reason=schema_verdict.reason,
            )

        # 2. Parse Canonical Transfer
        try:
            transfer = parse_pain001(xml_input)
        except Exception as err:
            return EntryGuardrailResult(
                outcome=GuardrailOutcome.REJECTED,
                stage="SCHEMA",
                cited_rules=["ISO_20022_PARSER_ERROR"],
                rejection_reason=f"Failed to parse validated pain.001: {err}",
            )

        # 3. Sanctions Screening
        if self._screener.is_sanctioned(transfer.sender.full_name, transfer.sender.bic):
            return EntryGuardrailResult(
                outcome=GuardrailOutcome.REJECTED,
                stage="SANCTIONS",
                cited_rules=["FIC_ACT_S28A", self._screener.source.citation()],
                rejection_reason=(
                    f"Sanctions match detected for sender '{transfer.sender.full_name}'"
                ),
            )

        if self._screener.is_sanctioned(transfer.recipient.full_name, transfer.recipient.bic):
            return EntryGuardrailResult(
                outcome=GuardrailOutcome.REJECTED,
                stage="SANCTIONS",
                cited_rules=["FIC_ACT_S28A", self._screener.source.citation()],
                rejection_reason=(
                    f"Sanctions match detected for recipient '{transfer.recipient.full_name}'"
                ),
            )

        # 4. PEP Screening & Enhanced Due Diligence
        send_amount_minor = transfer.quote.send.minor_units
        if sender_profile.is_pep and send_amount_minor > _PEP_ENHANCED_DUE_DILIGENCE_THRESHOLD:
            return EntryGuardrailResult(
                outcome=GuardrailOutcome.ESCALATE,
                stage="PEP_SCREEN",
                cited_rules=["FIC_ACT_S21H_PEP"],
                rejection_reason=(
                    "Sender is a Politically Exposed Person (PEP) exceeding threshold. "
                    "Escalating for human compliance review."
                ),
                transfer=transfer,
            )

        # The limit tables below are SARB figures in ZAR minor units. A transfer sent in
        # another currency, or a tier the table does not name, has no limit this gate can
        # apply -- so it is refused, never compared against a table that does not fit it.
        if transfer.quote.send.currency != CurrencyCode.ZAR or (
            sender_profile.kyc_tier not in _TIER_SINGLE_LIMITS
        ):
            return EntryGuardrailResult(
                outcome=GuardrailOutcome.REJECTED,
                stage="LIMITS",
                cited_rules=["LIMIT_TABLE_UNAVAILABLE"],
                rejection_reason=(
                    f"No limit table for a {transfer.quote.send.currency} transfer by KYC tier "
                    f"'{sender_profile.kyc_tier}'; the gate holds ZAR limits for L1-L3 only."
                ),
            )

        # 5. KYC Tier Single Transfer Limit
        tier_limit = _TIER_SINGLE_LIMITS[sender_profile.kyc_tier]
        if send_amount_minor > tier_limit:
            return EntryGuardrailResult(
                outcome=GuardrailOutcome.REJECTED,
                stage="LIMITS",
                cited_rules=["FICA_TIER_LIMIT", "SARB_EXCON_LIMIT_EXCEEDED"],
                rejection_reason=(
                    f"Send amount ({send_amount_minor} minor units) exceeds KYC tier "
                    f"'{sender_profile.kyc_tier}' single transaction limit ({tier_limit})."
                ),
            )

        # 6. Cumulative SDA Limit Check
        cumulative_volume = sender_profile.prior_transfers_30d_minor_units + send_amount_minor
        if cumulative_volume > _MAX_SDA_CUMULATIVE_LIMIT:
            return EntryGuardrailResult(
                outcome=GuardrailOutcome.REJECTED,
                stage="LIMITS",
                cited_rules=["SARB_EXCON_SDA_CAP_EXCEEDED"],
                rejection_reason=(
                    f"Cumulative 30-day transfer volume ({cumulative_volume} minor units) "
                    f"exceeds SARB SDA annual cap ({_MAX_SDA_CUMULATIVE_LIMIT} minor units)."
                ),
            )

        # All hard gates cleared
        return EntryGuardrailResult(
            outcome=GuardrailOutcome.PASS,
            stage="CLEAR",
            cited_rules=[],
            transfer=transfer,
            rejection_reason=None,
        )
