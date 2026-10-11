"""A simulated rail -- test-only, and named as one.

No real rail adapter exists yet: T052-T054 are blocked on sandbox credentials. This
double lives in the test tree, so no production wiring can import it; its terms are
whatever a test passes in, and its references say SIMULATED so none can be mistaken
for a real confirmation.
"""

import uuid
from decimal import Decimal

from ubunturemit_asco.models import RailQuote
from ubunturemit_domain import Corridor, Money, SettlementRail, Transfer
from ubunturemit_rails.base import RailStatus, RailSubmissionResult


class SimulatedRail:
    """Quotes the terms it was given; settles, or fails, as told."""

    def __init__(
        self,
        rail: SettlementRail,
        fee_minor_units: int = 0,
        spread_bps: int = 0,
        estimated_seconds: Decimal = Decimal("1"),
        fail: bool = False,
    ) -> None:
        self._rail = rail
        self._fee = fee_minor_units
        self._spread = spread_bps
        self._seconds = estimated_seconds
        self._fail = fail

    @property
    def rail(self) -> SettlementRail:
        return self._rail

    def get_quote(self, corridor: Corridor, amount: Money) -> RailQuote:
        return RailQuote(self._rail, self._fee, self._spread, self._seconds)

    def submit_settlement(self, pacs008_xml: str, transfer: Transfer) -> RailSubmissionResult:
        fee = Money(minor_units=self._fee, currency=transfer.quote.send.currency)
        if self._fail:
            return RailSubmissionResult(
                rail=self._rail,
                status=RailStatus.FAILED,
                settlement_reference="",
                fee=fee,
                settlement_seconds=Decimal("0"),
                error_message="simulated failure",
            )
        return RailSubmissionResult(
            rail=self._rail,
            status=RailStatus.DELIVERED,
            settlement_reference=f"SIMULATED-{uuid.uuid4().hex[:12].upper()}",
            fee=fee,
            settlement_seconds=self._seconds,
        )
