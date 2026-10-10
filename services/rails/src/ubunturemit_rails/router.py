"""Rail router and bounded alternate rail retry coordinator.
Docs: domain-model.md §4 & TASKS.md T055.
"""

import dataclasses
from collections.abc import Mapping

from ubunturemit_asco.models import RailQuote
from ubunturemit_asco.orchestrator.master import MasterOrchestrator, RetryBudgetExceededError
from ubunturemit_domain import (
    Corridor,
    Money,
    SettlementRail,
    Transfer,
    TransferState,
)

from ubunturemit_rails.base import RailAdapter, RailStatus, RailSubmissionResult


class SettlementExhaustionError(Exception):
    """Raised when all rail retries (max 2) are exhausted."""


class RailRouter:
    """Routes settlements across registered rail adapters and manages bounded retries on failure."""

    def __init__(self, adapters: Mapping[SettlementRail, RailAdapter]) -> None:
        # No defaults: the adapters a router used to build for itself returned invented
        # quotes and invented settlement confirmations (T052-T054).
        if not adapters:
            raise ValueError("RailRouter needs at least one rail adapter.")
        self._adapters = dict(adapters)

    def get_quotes(self, corridor: Corridor, amount: Money) -> list[RailQuote]:
        """Collect live quotes from all eligible rail adapters."""
        quotes: list[RailQuote] = []
        for rail, adapter in self._adapters.items():
            if rail == SettlementRail.PAPSS and not corridor.papss_eligible:
                continue
            try:
                quotes.append(adapter.get_quote(corridor, amount))
            except ValueError:
                continue
        return quotes

    def execute_settlement_with_retry(
        self,
        transfer: Transfer,
        pacs008_xml: str,
        preferred_rail: SettlementRail,
        orchestrator: MasterOrchestrator,
    ) -> tuple[Transfer, RailSubmissionResult, list[RailSubmissionResult]]:
        """Submit settlement with automatic fallback on alternate rails, bounded at 2 retries."""
        attempts: list[RailSubmissionResult] = []
        current_transfer = transfer

        # Build priority queue of candidate rails
        corridor = current_transfer.quote.fx.corridor
        alternate_candidates = [
            r
            for r in [SettlementRail.RIPPLE, SettlementRail.PAPSS, SettlementRail.SWIFT]
            if r != preferred_rail and (r != SettlementRail.PAPSS or corridor.papss_eligible)
        ]
        # Only rails with a registered adapter are candidates. Skipping one mid-loop
        # used to count a retry against the budget for a rail never attempted.
        all_candidate_rails = [
            r for r in [preferred_rail, *alternate_candidates] if r in self._adapters
        ]

        for attempt_index, rail_candidate in enumerate(all_candidate_rails):
            adapter = self._adapters[rail_candidate]

            result = adapter.submit_settlement(pacs008_xml, current_transfer)
            attempts.append(result)

            if result.status == RailStatus.DELIVERED:
                # Succeeded! Transition to DELIVERED
                settled = orchestrator.transition(current_transfer, TransferState.DELIVERED)
                final_transfer = dataclasses.replace(
                    settled,
                    rail=rail_candidate,
                    settlement_seconds=result.settlement_seconds,
                )
                return final_transfer, result, attempts

            # Rail failed! Move current transfer to FAILED
            current_transfer = orchestrator.transition(current_transfer, TransferState.FAILED)

            # Check if we have another alternate rail candidate and budget allows retry
            if attempt_index + 1 < len(all_candidate_rails):
                next_rail = all_candidate_rails[attempt_index + 1]
                try:
                    current_transfer = orchestrator.retry_settlement(
                        current_transfer,
                        alternate_rail=next_rail,
                    )
                except RetryBudgetExceededError:
                    break

        raise SettlementExhaustionError(
            f"Settlement failed across all attempted rails ({[a.rail for a in attempts]}). "
            "Retry budget exhausted."
        )
