"""Audit trail completeness verifier.
SARB PEM compliance & docs/design/asco-orchestrator.md §8.
"""

from ubunturemit_asco.models import AuditRecord
from ubunturemit_domain import TransferId


def verify_audit_completeness(
    transfer_id: TransferId,
    records: list[AuditRecord],
    terminal_state: str,
) -> bool:
    """Verify that every participating actor has at least one AuditRecord for a terminal state.

    Required actors per terminal state:
    - "SETTLING" / "DELIVERED": Sentinel, Strategist, Exit Validator, Orchestrator
    - "PENDING_REVIEW": Sentinel, Orchestrator
    - "REJECTED": Orchestrator
    """
    matching_records = [r for r in records if r.transfer_id == transfer_id]
    if not matching_records:
        return False

    actors = {r.actor for r in matching_records}

    if terminal_state in ("SETTLING", "DELIVERED"):
        required = {
            "compliance_sentinel",
            "liquidity_strategist",
            "exit_validator",
            "orchestrator",
        }
        return required.issubset(actors)

    if terminal_state == "PENDING_REVIEW":
        required = {"compliance_sentinel", "orchestrator"}
        return required.issubset(actors)

    if terminal_state == "REJECTED":
        return "orchestrator" in actors

    return True
