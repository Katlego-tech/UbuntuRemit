"""The transfer aggregate and its lifecycle -- docs/design/domain-model.md §3-§4."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import NewType

from .party import Party
from .quote import TransferQuote

__all__ = [
    "ComplianceDeclaration",
    "PaymentPurpose",
    "SettlementRail",
    "SourceOfFunds",
    "Transfer",
    "TransferId",
    "TransferState",
]

TransferId = NewType("TransferId", str)


class SettlementRail(StrEnum):
    """The rails a transfer can settle over -- domain-model.md §5."""

    RIPPLE = "RIPPLE"
    SWIFT = "SWIFT"
    PAPSS = "PAPSS"


class TransferState(StrEnum):
    """The settlement lifecycle -- domain-model.md §4."""

    INITIATED = "INITIATED"
    VALIDATED = "VALIDATED"
    SETTLING = "SETTLING"
    DELIVERED = "DELIVERED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class PaymentPurpose(StrEnum):
    """Why the money is moving -- domain-model.md §5.

    Closed, with no "Other": SARB reporting needs a fixed taxonomy, and a
    free-text purpose is not reportable.
    """

    FAMILY_SUPPORT = "FAMILY_SUPPORT"
    BUSINESS_INVESTMENT = "BUSINESS_INVESTMENT"
    GOODS_OR_SERVICES = "GOODS_OR_SERVICES"
    EDUCATION = "EDUCATION"
    MEDICAL = "MEDICAL"


class SourceOfFunds(StrEnum):
    """Where the money came from -- domain-model.md §5. Closed, as above."""

    EMPLOYMENT_SALARY = "EMPLOYMENT_SALARY"
    BUSINESS_REVENUE = "BUSINESS_REVENUE"
    SAVINGS = "SAVINGS"


# Transcribed from the stateDiagram in domain-model.md §4. Transitions absent
# from this set are impossible, not merely unimplemented -- which is why the
# lookup below refuses rather than warns.
_LEGAL_TRANSITIONS: frozenset[tuple[TransferState, TransferState]] = frozenset(
    {
        (TransferState.INITIATED, TransferState.VALIDATED),
        (TransferState.INITIATED, TransferState.REJECTED),
        (TransferState.VALIDATED, TransferState.SETTLING),
        (TransferState.VALIDATED, TransferState.REJECTED),
        (TransferState.SETTLING, TransferState.DELIVERED),
        (TransferState.SETTLING, TransferState.FAILED),
        # The only cycle in the diagram. Bounding it at 2 alternate rails is
        # T055's job and needs a retry count this aggregate does not draw --
        # legality lives here, the budget does not.
        (TransferState.FAILED, TransferState.SETTLING),
    }
)


@dataclass(frozen=True, slots=True)
class ComplianceDeclaration:
    """What the sender declared about the payment -- domain-model.md §3."""

    purpose: PaymentPurpose
    source_of_funds: SourceOfFunds

    def __post_init__(self) -> None:
        if not isinstance(self.purpose, PaymentPurpose):
            raise TypeError(f"purpose must be a PaymentPurpose, got {type(self.purpose).__name__}")
        if not isinstance(self.source_of_funds, SourceOfFunds):
            raise TypeError(
                f"source_of_funds must be a SourceOfFunds, got "
                f"{type(self.source_of_funds).__name__}"
            )


@dataclass(frozen=True, slots=True)
class Transfer:
    """One cross-border transfer -- domain-model.md §3.

    Frozen, so `transition_to` returns a new instance and the prior one stays
    intact for the audit trail. `rail` and `settlement_seconds` are absent
    until known: a transfer at INITIATED has neither, and a required field
    there could only be satisfied by inventing a value (§9).
    """

    id: TransferId
    reference: str
    sender: Party
    recipient: Party
    quote: TransferQuote
    declaration: ComplianceDeclaration
    state: TransferState
    created_at: datetime
    rail: SettlementRail | None = None
    settlement_seconds: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("id must be a non-blank identifier")
        if not isinstance(self.reference, str) or not self.reference.strip():
            raise ValueError("reference must not be blank")

        for field, expected in (
            ("sender", Party),
            ("recipient", Party),
            ("quote", TransferQuote),
            ("declaration", ComplianceDeclaration),
            ("state", TransferState),
        ):
            value = getattr(self, field)
            if not isinstance(value, expected):
                raise TypeError(f"{field} must be {expected.__name__}, got {type(value).__name__}")

        if not isinstance(self.created_at, datetime):
            raise TypeError(f"created_at must be a datetime, got {type(self.created_at).__name__}")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")

        if self.rail is not None and not isinstance(self.rail, SettlementRail):
            raise TypeError(
                f"rail must be a SettlementRail or None, got {type(self.rail).__name__}"
            )
        if self.settlement_seconds is not None and not isinstance(self.settlement_seconds, Decimal):
            raise TypeError(
                f"settlement_seconds must be a Decimal or None, got "
                f"{type(self.settlement_seconds).__name__}"
            )

    def transition_to(self, new_state: TransferState) -> Transfer:
        """Move to `new_state`, or refuse.

        Only the transitions drawn in §4 are permitted. In particular there is
        no path out of REJECTED or DELIVERED, and none that skips VALIDATED: a
        rejected transfer that needs to proceed is a *new* Transfer with a new
        id, so the audit trail of the rejection survives intact.
        """
        if not isinstance(new_state, TransferState):
            raise TypeError(f"new_state must be a TransferState, got {type(new_state).__name__}")
        if (self.state, new_state) not in _LEGAL_TRANSITIONS:
            raise ValueError(
                f"{self.state} -> {new_state} is not a transition drawn in "
                "domain-model.md §4, so it is impossible. If it should exist, "
                "change the diagram first."
            )
        return dataclasses.replace(self, state=new_state)
