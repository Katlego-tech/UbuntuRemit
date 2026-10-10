"""The Postgres audit table and its grants -- docs/design/asco-orchestrator.md §6 (T050a).

Append-only is enforced twice. The grant is the contract: the writer role is given
SELECT and INSERT and nothing else, so an UPDATE or DELETE fails on privilege before
any trigger runs. The triggers are the second wall, against a role that was granted
too much by mistake (including the table owner).
"""

from typing import LiteralString

import psycopg

WRITER_ROLE = "audit_writer"

# Plain literals throughout -- the role name is spelled out rather than interpolated, so
# no statement here is built from a string at runtime.
SCHEMA_STATEMENTS: tuple[LiteralString, ...] = (
    """
    CREATE TABLE IF NOT EXISTS audit_records (
        id BIGSERIAL PRIMARY KEY,
        transfer_id TEXT NOT NULL,
        actor TEXT NOT NULL,
        thought TEXT NOT NULL,
        action TEXT NOT NULL,
        observation TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        deterministic_override BOOLEAN NOT NULL,
        -- Where a record came from on the bus. A redelivered message carries the same
        -- position, so it is stored once; a record appended directly has none.
        source_topic TEXT,
        source_partition INTEGER,
        source_offset BIGINT,
        UNIQUE (source_topic, source_partition, source_offset)
    )
    """,
    "CREATE INDEX IF NOT EXISTS audit_records_by_transfer ON audit_records (transfer_id, id)",
    """
    CREATE OR REPLACE FUNCTION audit_records_append_only() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'Audit records are append-only: % forbidden.', TG_OP;
    END;
    $$
    """,
    "DROP TRIGGER IF EXISTS audit_records_no_update ON audit_records",
    """
    CREATE TRIGGER audit_records_no_update BEFORE UPDATE OR DELETE ON audit_records
    FOR EACH ROW EXECUTE FUNCTION audit_records_append_only()
    """,
    "DROP TRIGGER IF EXISTS audit_records_no_truncate ON audit_records",
    """
    CREATE TRIGGER audit_records_no_truncate BEFORE TRUNCATE ON audit_records
    FOR EACH STATEMENT EXECUTE FUNCTION audit_records_append_only()
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'audit_writer') THEN
            CREATE ROLE audit_writer NOLOGIN;
        END IF;
    END
    $$
    """,
    "REVOKE ALL ON audit_records FROM PUBLIC",
    "REVOKE ALL ON audit_records FROM audit_writer",
    "GRANT SELECT, INSERT ON audit_records TO audit_writer",
    "GRANT USAGE ON SEQUENCE audit_records_id_seq TO audit_writer",
)


def install_schema(owner: psycopg.Connection) -> None:
    """Create the table, its triggers and the writer role's grants. Idempotent.

    Run as the table's owner -- a migration step, never by the service itself, which
    connects as a member of WRITER_ROLE.
    """
    with owner.transaction():
        for statement in SCHEMA_STATEMENTS:
            owner.execute(statement)
