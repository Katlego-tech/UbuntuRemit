"""Postgres-backed append-only audit store (T050a) -- see schema.py for the grants."""

from dataclasses import dataclass

import psycopg
from ubunturemit_asco.models import AuditRecord
from ubunturemit_domain import TransferId


class OverPrivilegedAuditStoreError(RuntimeError):
    """The store's database role can change or remove audit records, so it refuses to run."""


@dataclass(frozen=True, slots=True)
class LogPosition:
    """A record's position on the bus: what makes a redelivery recognisable."""

    topic: str
    partition: int
    offset: int


class PostgresAuditStore:
    """Appends and reads audit records as a role that holds only SELECT and INSERT."""

    def __init__(self, conninfo: str) -> None:
        self._conn = psycopg.connect(conninfo, autocommit=True)
        try:
            self._refuse_if_mutable()
        except BaseException:
            self._conn.close()
            raise

    def _refuse_if_mutable(self) -> None:
        # Append-only is a property of the role, checked rather than assumed: a store
        # connected as the owner or a superuser could rewrite history, so it does not start.
        row = self._conn.execute(
            "SELECT has_table_privilege('audit_records', 'UPDATE'),"
            " has_table_privilege('audit_records', 'DELETE'),"
            " has_table_privilege('audit_records', 'TRUNCATE')"
        ).fetchone()
        if row is None or any(row):
            raise OverPrivilegedAuditStoreError(
                "This role can UPDATE, DELETE or TRUNCATE audit_records. Connect as a "
                "member of the audit_writer role, which holds only SELECT and INSERT."
            )

    def append(self, record: AuditRecord) -> None:
        self.append_from_log(record, None)

    def append_from_log(self, record: AuditRecord, position: LogPosition | None) -> bool:
        """Append a record; returns False when that bus position was already stored."""
        if not isinstance(record, AuditRecord):
            raise TypeError(f"Expected AuditRecord, got {type(record).__name__}")
        cursor = self._conn.execute(
            """
            INSERT INTO audit_records (
                transfer_id, actor, thought, action, observation, recorded_at,
                deterministic_override, source_topic, source_partition, source_offset
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_topic, source_partition, source_offset) DO NOTHING
            """,
            (
                str(record.transfer_id),
                record.actor,
                record.thought,
                record.action,
                record.observation,
                record.recorded_at,
                record.deterministic_override,
                position.topic if position else None,
                position.partition if position else None,
                position.offset if position else None,
            ),
        )
        return cursor.rowcount == 1

    def get_records(self, transfer_id: TransferId) -> list[AuditRecord]:
        rows = self._conn.execute(
            """
            SELECT transfer_id, actor, thought, action, observation, recorded_at,
                   deterministic_override
            FROM audit_records WHERE transfer_id = %s ORDER BY id
            """,
            (str(transfer_id),),
        ).fetchall()
        return [
            AuditRecord(
                transfer_id=TransferId(row[0]),
                actor=row[1],
                thought=row[2],
                action=row[3],
                observation=row[4],
                recorded_at=row[5],
                deterministic_override=row[6],
            )
            for row in rows
        ]

    def close(self) -> None:
        self._conn.close()
