"""Base abstractions for payment rail adapters -- docs/design/asco-orchestrator.md §3, §4."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from ubunturemit_asco.models import RailQuote
from ubunturemit_domain import (
    Corridor,
    Money,
    SettlementRail,
    Transfer,
)


class RailStatus(StrEnum):
    """Status returned by a rail adapter upon settlement submission."""

    DELIVERED = "DELIVERED"
    SETTLING = "SETTLING"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class RailSubmissionResult:
    """Outcome of submitting a pacs.008 instruction to a payment rail."""

    rail: SettlementRail
    status: RailStatus
    settlement_reference: str
    fee: Money
    settlement_seconds: Decimal
    error_message: str | None = None


class RailAdapter(Protocol):
    """Protocol for interacting with a specific settlement rail."""

    @property
    def rail(self) -> SettlementRail:
        """The settlement rail enum handled by this adapter."""
        ...

    def get_quote(self, corridor: Corridor, amount: Money) -> RailQuote:
        """Generate a real quote for settling this transfer on this rail."""
        ...

    def submit_settlement(self, pacs008_xml: str, transfer: Transfer) -> RailSubmissionResult:
        """Submit a pacs.008 payment payload to the rail."""
        ...
