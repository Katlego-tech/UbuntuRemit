"""SWIFT GPI rail adapter -- TASKS.md T054."""

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


class SwiftRailAdapter:
    """Adapter for SWIFT correspondent banking network (ISO 20022 / pacs.008)."""

    def __init__(self, simulate_failure: bool = False) -> None:
        self._simulate_failure = simulate_failure

    @property
    def rail(self) -> SettlementRail:
        return SettlementRail.SWIFT

    def get_quote(self, corridor: Corridor, amount: Money) -> RailQuote:
        """SWIFT offers global reach, 30s settlement, 4500 minor units fee, 25 bps spread."""
        return RailQuote(
            rail=SettlementRail.SWIFT,
            fee_minor_units=4500,
            spread_bps=25,
            estimated_seconds=Decimal("30.0"),
        )

    def submit_settlement(self, pacs008_xml: str, transfer: Transfer) -> RailSubmissionResult:
        """Submit pacs.008 payload to SWIFT gateway."""
        if self._simulate_failure:
            return RailSubmissionResult(
                rail=SettlementRail.SWIFT,
                status=RailStatus.FAILED,
                settlement_reference="",
                fee=Money(minor_units=4500, currency=transfer.quote.send.currency),
                settlement_seconds=Decimal("0.0"),
                error_message="SWIFT correspondent nostro bank rejected instruction",
            )

        uetr = str(uuid.uuid4())
        return RailSubmissionResult(
            rail=SettlementRail.SWIFT,
            status=RailStatus.DELIVERED,
            settlement_reference=f"UETR-{uetr}",
            fee=Money(minor_units=4500, currency=transfer.quote.send.currency),
            settlement_seconds=Decimal("30.0"),
            error_message=None,
        )
