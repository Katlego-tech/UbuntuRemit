"""Ripple rail adapter -- docs/design/asco-orchestrator.md §3 & TASKS.md T052."""

import uuid
from decimal import Decimal

from ubunturemit_asco.models import RailQuote
from ubunturemit_domain import (
    Corridor,
    Money,
    SettlementRail,
    Transfer,
)

from ubunturemit_rails.base import RailStatus, RailSubmissionResult


class RippleRailAdapter:
    """Adapter for XRPL / RippleNet cross-border settlement rail."""

    def __init__(self, simulate_failure: bool = False) -> None:
        self._simulate_failure = simulate_failure

    @property
    def rail(self) -> SettlementRail:
        return SettlementRail.RIPPLE

    def get_quote(self, corridor: Corridor, amount: Money) -> RailQuote:
        """Ripple offers near-instant settlement with 0 fee and 12 bps spread."""
        return RailQuote(
            rail=SettlementRail.RIPPLE,
            fee_minor_units=0,
            spread_bps=12,
            estimated_seconds=Decimal("3.2"),
        )

    def submit_settlement(self, pacs008_xml: str, transfer: Transfer) -> RailSubmissionResult:
        """Submit settlement to Ripple network."""
        if self._simulate_failure:
            return RailSubmissionResult(
                rail=SettlementRail.RIPPLE,
                status=RailStatus.FAILED,
                settlement_reference="",
                fee=Money(minor_units=0, currency=transfer.quote.send.currency),
                settlement_seconds=Decimal("0.0"),
                error_message="RippleNet node liquidity pool unavailable",
            )

        tx_hash = f"XRPL-{uuid.uuid4().hex[:12].upper()}"
        return RailSubmissionResult(
            rail=SettlementRail.RIPPLE,
            status=RailStatus.DELIVERED,
            settlement_reference=tx_hash,
            fee=Money(minor_units=0, currency=transfer.quote.send.currency),
            settlement_seconds=Decimal("3.2"),
            error_message=None,
        )
