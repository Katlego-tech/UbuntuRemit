"""PAPSS (Pan-African Payment and Settlement System) rail adapter -- TASKS.md T053."""

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


class PapssRailAdapter:
    """Adapter for PAPSS central-bank-backed settlement rail."""

    def __init__(self, simulate_failure: bool = False) -> None:
        self._simulate_failure = simulate_failure

    @property
    def rail(self) -> SettlementRail:
        return SettlementRail.PAPSS

    def get_quote(self, corridor: Corridor, amount: Money) -> RailQuote:
        """PAPSS offers 11s settlement, fixed 1200 minor units fee, 8 bps spread."""
        if not corridor.papss_eligible:
            raise ValueError(
                f"Corridor {corridor.source}->{corridor.target} is not eligible for PAPSS."
            )

        return RailQuote(
            rail=SettlementRail.PAPSS,
            fee_minor_units=1200,
            spread_bps=8,
            estimated_seconds=Decimal("11.0"),
        )

    def submit_settlement(self, pacs008_xml: str, transfer: Transfer) -> RailSubmissionResult:
        """Submit settlement to PAPSS clearing system."""
        if not transfer.quote.fx.corridor.papss_eligible:
            return RailSubmissionResult(
                rail=SettlementRail.PAPSS,
                status=RailStatus.REJECTED,
                settlement_reference="",
                fee=Money(minor_units=0, currency=transfer.quote.send.currency),
                settlement_seconds=Decimal("0.0"),
                error_message="Corridor is not PAPSS eligible",
            )

        if self._simulate_failure:
            return RailSubmissionResult(
                rail=SettlementRail.PAPSS,
                status=RailStatus.FAILED,
                settlement_reference="",
                fee=Money(minor_units=1200, currency=transfer.quote.send.currency),
                settlement_seconds=Decimal("0.0"),
                error_message="PAPSS Central Bank clearing gateway timeout",
            )

        tx_ref = f"PAPSS-{uuid.uuid4().hex[:12].upper()}"
        return RailSubmissionResult(
            rail=SettlementRail.PAPSS,
            status=RailStatus.DELIVERED,
            settlement_reference=tx_ref,
            fee=Money(minor_units=1200, currency=transfer.quote.send.currency),
            settlement_seconds=Decimal("11.0"),
            error_message=None,
        )
