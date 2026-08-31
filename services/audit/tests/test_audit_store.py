"""Tests for Append-Only Audit Store (T050).

Guarantees:
- Records can be appended and read chronologically.
- Any attempt to modify (UPDATE) or delete (DELETE) records raises sqlite3.DatabaseError / aborts.
"""

import sqlite3

import pytest
from ubunturemit_asco.models import AuditRecord
from ubunturemit_audit.store import (
    InMemoryAuditStore,
    SqliteAuditStore,
)
from ubunturemit_domain import TransferId


def test_in_memory_audit_store_append_and_query() -> None:
    store = InMemoryAuditStore()
    t_id = TransferId("TR-001")
    rec = AuditRecord(
        transfer_id=t_id,
        actor="compliance_sentinel",
        thought="Assessing risk",
        action="Prompting model",
        observation="Outcome PASS",
        recorded_at="2026-08-31T10:00:00Z",
    )
    store.append(rec)

    records = store.get_records(t_id)
    assert len(records) == 1
    assert records[0].actor == "compliance_sentinel"


def test_sqlite_audit_store_append_and_immutability() -> None:
    store = SqliteAuditStore(":memory:")
    t_id = TransferId("TR-002")
    rec = AuditRecord(
        transfer_id=t_id,
        actor="orchestrator",
        thought="Initiating settlement",
        action="Transition state",
        observation="VALIDATED",
        recorded_at="2026-08-31T10:00:00Z",
    )
    store.append(rec)

    records = store.get_records(t_id)
    assert len(records) == 1
    assert records[0].actor == "orchestrator"

    # Attempting SQL UPDATE directly on sqlite table must abort via database trigger
    with pytest.raises(sqlite3.DatabaseError, match="UPDATE forbidden"):
        store._conn.execute(
            "UPDATE audit_records SET actor = 'corrupt' WHERE transfer_id = 'TR-002';"
        )

    # Attempting SQL DELETE directly on sqlite table must abort via database trigger
    with pytest.raises(sqlite3.DatabaseError, match="DELETE forbidden"):
        store._conn.execute("DELETE FROM audit_records WHERE transfer_id = 'TR-002';")
