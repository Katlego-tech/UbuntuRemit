"""Master Orchestrator deterministic state machine.
Docs: docs/design/domain-model.md §4 & asco-orchestrator.md §3, §4.

Operates purely deterministically with ZERO LLM calls of its own.
Manages transfer lifecycle and bounds alternate rail retries at 2.
"""

import dataclasses

from ubunturemit_domain import (
    SettlementRail,
    Transfer,
    TransferId,
    TransferState,
)
from ubunturemit_domain.transfer import _LEGAL_TRANSITIONS

LEGAL_TRANSITIONS: frozenset[tuple[TransferState, TransferState]] = _LEGAL_TRANSITIONS
MAX_SETTLEMENT_RETRIES: int = 2


class OrchestratorStateError(Exception):
    """Raised when an illegal or unsupported state transition is attempted."""


class RetryBudgetExceededError(Exception):
    """Raised when the alternate rail retry budget (max 2) is exhausted."""


class MasterOrchestrator:
    """Deterministic Master Orchestrator managing transfer lifecycles and negotiations."""

    def __init__(self) -> None:
        self._retry_counts: dict[TransferId, int] = {}

    def get_retry_count(self, transfer_id: TransferId) -> int:
        """Return the number of settlement retries attempted for a transfer."""
        return self._retry_counts.get(transfer_id, 0)

    def transition(self, transfer: Transfer, to_state: TransferState) -> Transfer:
        """Execute a deterministic state transition over the Transfer aggregate."""
        if not isinstance(to_state, TransferState):
            raise TypeError(f"to_state must be a TransferState, got {type(to_state).__name__}")

        if (transfer.state, to_state) not in LEGAL_TRANSITIONS:
            raise OrchestratorStateError(
                f"Illegal state transition {transfer.state} -> {to_state}. "
                "Only transitions drawn in domain-model.md §4 are permitted."
            )

        return transfer.transition_to(to_state)

    def retry_settlement(
        self,
        transfer: Transfer,
        alternate_rail: SettlementRail,
    ) -> Transfer:
        """Retry a failed settlement on an alternate rail, bounded at 2 retries."""
        if transfer.state != TransferState.FAILED:
            raise OrchestratorStateError(
                f"Cannot retry settlement from state {transfer.state}. Must be in FAILED state."
            )

        current_retries = self.get_retry_count(transfer.id)
        if current_retries >= MAX_SETTLEMENT_RETRIES:
            raise RetryBudgetExceededError(
                f"Retry budget exhausted ({current_retries}/{MAX_SETTLEMENT_RETRIES}) "
                f"for transfer '{transfer.reference}'."
            )

        self._retry_counts[transfer.id] = current_retries + 1

        # FAILED -> SETTLING is a legal transition drawn in domain-model.md §4
        updated = transfer.transition_to(TransferState.SETTLING)
        return dataclasses.replace(updated, rail=alternate_rail)
