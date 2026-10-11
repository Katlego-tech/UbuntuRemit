"""Deterministic ASCO Entry Guardrail -- docs/design/asco-orchestrator.md §3, §4.

Hard Gates (deterministic, zero LLM):
1. Schema validation (pain.001 3-tier validation).
2. Sanctions and PEP screening (FIC Act s28A, UN/OFAC lists; PEP enhanced review).
3. Corridor support and KYC/SDA limits (SARB EXCON B.4, FICA Tier limits).
"""

from collections.abc import Iterable, Mapping
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


class LimitTableError(ValueError):
    """A limit table with no source, no limits, or a non-positive figure."""


@dataclass(frozen=True, slots=True)
class LimitTable:
    """The KYC/EXCON limits the entry gate applies, as published in a named, dated source.

    No figure lives in code: every limit is loaded from the document that sets it, and a
    LIMITS rejection cites that document (Non-negotiable I). Amounts are minor units of
    `currency`; a transfer in any other currency has no limit here and is refused.
    """

    source_name: str
    published: date
    currency: CurrencyCode
    single_transfer_limits: Mapping[str, int]  # by KYC tier, e.g. {"L1": ..., "L3": ...}
    cumulative_30d_limit: int  # prior 30 days' volume + this transfer
    pep_review_threshold: int  # a PEP sending above this is escalated for review

    def __post_init__(self) -> None:
        if not self.source_name.strip():
            raise LimitTableError("A limit table needs the name of the source that sets it.")
        if not self.single_transfer_limits:
            raise LimitTableError(f"Limit table '{self.source_name}' names no KYC tier.")
        figures = [
            *self.single_transfer_limits.values(),
            self.cumulative_30d_limit,
            self.pep_review_threshold,
        ]
        if any(figure <= 0 for figure in figures):
            raise LimitTableError(f"Limit table '{self.source_name}' has a non-positive limit.")

    def citation(self) -> str:
        return f"LIMITS:{self.source_name}@{self.published.isoformat()}"


class EntryGuardrail:
    """Deterministic entry gate preceding the ASCO multi-agent negotiation loop."""

    def __init__(self, sanctions_screener: SanctionsScreener, limit_table: LimitTable) -> None:
        if limit_table is None:
            raise LimitTableError(
                "EntryGuardrail needs a sourced limit table; it holds no limits of its own."
            )
        self._limits = limit_table
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

        # 4. Is there a limit for this transfer at all? The table's figures are in its own
        # currency and for the tiers it names. Anything else has no limit this gate can
        # apply, so it is refused -- never compared against a table that does not fit it.
        limits = self._limits
        send_amount_minor = transfer.quote.send.minor_units
        if transfer.quote.send.currency != limits.currency or (
            sender_profile.kyc_tier not in limits.single_transfer_limits
        ):
            return EntryGuardrailResult(
                outcome=GuardrailOutcome.REJECTED,
                stage="LIMITS",
                cited_rules=["LIMIT_TABLE_UNAVAILABLE", limits.citation()],
                rejection_reason=(
                    f"No limit for a {transfer.quote.send.currency} transfer by KYC tier "
                    f"'{sender_profile.kyc_tier}' in {limits.source_name}."
                ),
            )

        # 5. PEP Screening & Enhanced Due Diligence
        if sender_profile.is_pep and send_amount_minor > limits.pep_review_threshold:
            return EntryGuardrailResult(
                outcome=GuardrailOutcome.ESCALATE,
                stage="PEP_SCREEN",
                cited_rules=["FIC_ACT_S21H_PEP", limits.citation()],
                rejection_reason=(
                    "Sender is a Politically Exposed Person (PEP) exceeding threshold. "
                    "Escalating for human compliance review."
                ),
                transfer=transfer,
            )

        # 6. KYC Tier Single Transfer Limit
        tier_limit = limits.single_transfer_limits[sender_profile.kyc_tier]
        if send_amount_minor > tier_limit:
            return EntryGuardrailResult(
                outcome=GuardrailOutcome.REJECTED,
                stage="LIMITS",
                cited_rules=["FICA_TIER_LIMIT", "SARB_EXCON_LIMIT_EXCEEDED", limits.citation()],
                rejection_reason=(
                    f"Send amount ({send_amount_minor} minor units) exceeds KYC tier "
                    f"'{sender_profile.kyc_tier}' single transaction limit ({tier_limit})."
                ),
            )

        # 7. Cumulative 30-day limit
        cumulative_volume = sender_profile.prior_transfers_30d_minor_units + send_amount_minor
        if cumulative_volume > limits.cumulative_30d_limit:
            return EntryGuardrailResult(
                outcome=GuardrailOutcome.REJECTED,
                stage="LIMITS",
                cited_rules=["SARB_EXCON_SDA_CAP_EXCEEDED", limits.citation()],
                rejection_reason=(
                    f"Cumulative 30-day transfer volume ({cumulative_volume} minor units) "
                    f"exceeds the 30-day limit ({limits.cumulative_30d_limit}) in "
                    f"{limits.source_name}."
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
