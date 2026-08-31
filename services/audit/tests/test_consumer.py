"""Tests for Kafka audit consumer and completeness verification (T050, T051)."""

import json

from ubunturemit_asco.models import AuditRecord
from ubunturemit_audit.consumer import AuditConsumer
from ubunturemit_audit.store import InMemoryAuditStore
from ubunturemit_audit.verifier import verify_audit_completeness
from ubunturemit_domain import TransferId


def test_audit_consumer_processes_message() -> None:
    store = InMemoryAuditStore()
    consumer = AuditConsumer(store=store)

    payload = json.dumps(
        {
            "transfer_id": "TR-100",
            "actor": "exit_validator",
            "thought": "Checking pacs.008 schema",
            "action": "Validating XML",
            "observation": "Valid pacs.008",
            "recorded_at": "2026-08-31T10:05:00Z",
            "deterministic_override": False,
        }
    )

    record = consumer.process_message(payload)
    assert record.transfer_id == TransferId("TR-100")
    assert record.actor == "exit_validator"

    stored = store.get_records(TransferId("TR-100"))
    assert len(stored) == 1
    assert stored[0].actor == "exit_validator"


def test_verify_audit_completeness_settling_and_delivered() -> None:
    t_id = TransferId("TR-200")
    records = [
        AuditRecord(t_id, "compliance_sentinel", "t", "a", "o", "2026-08-31T10:00:00Z"),
        AuditRecord(t_id, "liquidity_strategist", "t", "a", "o", "2026-08-31T10:01:00Z"),
        AuditRecord(t_id, "exit_validator", "t", "a", "o", "2026-08-31T10:02:00Z"),
        AuditRecord(t_id, "orchestrator", "t", "a", "o", "2026-08-31T10:03:00Z"),
    ]

    assert verify_audit_completeness(t_id, records, "SETTLING") is True
    assert verify_audit_completeness(t_id, records, "DELIVERED") is True

    # Incomplete records (missing exit_validator) fails completeness check
    incomplete = records[:2] + [records[3]]
    assert verify_audit_completeness(t_id, incomplete, "SETTLING") is False
