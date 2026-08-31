"""Append-only audit store -- domain-model.md §3, §4 & SARB PEM compliance.

Guarantees:
- Strictly append-only: INSERT and SELECT operations only.
- No UPDATE or DELETE path exists in application code or DB schema.
"""

import sqlite3
from typing import Protocol

from ubunturemit_asco.models import AuditRecord
from ubunturemit_domain import TransferId


class AuditStoreImmutableError(Exception):
    """Raised if any modification or deletion of existing audit records is attempted."""


class AuditStore(Protocol):
    """Protocol for append-only audit storage."""

    def append(self, record: AuditRecord) -> None:
        """Append a single AuditRecord to the store."""
        ...

    def get_records(self, transfer_id: TransferId) -> list[AuditRecord]:
        """Fetch all chronological AuditRecords for a given transfer."""
        ...


class InMemoryAuditStore:
    """In-memory append-only audit store."""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    def append(self, record: AuditRecord) -> None:
        if not isinstance(record, AuditRecord):
            raise TypeError(f"Expected AuditRecord, got {type(record).__name__}")
        self._records.append(record)

    def get_records(self, transfer_id: TransferId) -> list[AuditRecord]:
        return [r for r in self._records if r.transfer_id == transfer_id]

    def all_records(self) -> list[AuditRecord]:
        return list(self._records)


class SqliteAuditStore:
    """SQLite-backed append-only audit store with database-level immutability triggers."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._create_schema()

    def _create_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transfer_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    thought TEXT NOT NULL,
                    action TEXT NOT NULL,
                    observation TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    deterministic_override INTEGER NOT NULL
                );
                """
            )
            # Immutability triggers: hard abort on any UPDATE or DELETE attempt
            self._conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS abort_audit_update
                BEFORE UPDATE ON audit_records
                BEGIN
                    SELECT RAISE(ABORT, 'Audit records are append-only: UPDATE forbidden.');
                END;
                """
            )
            self._conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS abort_audit_delete
                BEFORE DELETE ON audit_records
                BEGIN
                    SELECT RAISE(ABORT, 'Audit records are append-only: DELETE forbidden.');
                END;
                """
            )

    def append(self, record: AuditRecord) -> None:
        if not isinstance(record, AuditRecord):
            raise TypeError(f"Expected AuditRecord, got {type(record).__name__}")

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO audit_records (
                    transfer_id, actor, thought, action,
                    observation, recorded_at, deterministic_override
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    str(record.transfer_id),
                    record.actor,
                    record.thought,
                    record.action,
                    record.observation,
                    record.recorded_at,
                    1 if record.deterministic_override else 0,
                ),
            )

    def get_records(self, transfer_id: TransferId) -> list[AuditRecord]:
        cursor = self._conn.execute(
            """
            SELECT
                transfer_id, actor, thought, action,
                observation, recorded_at, deterministic_override
            FROM audit_records
            WHERE transfer_id = ?
            ORDER BY id ASC;
            """,
            (str(transfer_id),),
        )
        rows = cursor.fetchall()
        return [
            AuditRecord(
                transfer_id=TransferId(row[0]),
                actor=row[1],
                thought=row[2],
                action=row[3],
                observation=row[4],
                recorded_at=row[5],
                deterministic_override=bool(row[6]),
            )
            for row in rows
        ]

    def close(self) -> None:
        self._conn.close()
