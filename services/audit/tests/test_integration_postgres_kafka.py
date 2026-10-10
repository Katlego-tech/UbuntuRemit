"""T050a integration tests -- the compose Postgres and Kafka, never mocks.

Run by the gate's integration check, which starts both (`docker compose up --wait`):
    pytest -m integration
Excluded from the default run, where no broker or database is guaranteed to exist.
"""

import os
import time
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from confluent_kafka.admin import (  # NewTopic: documented path, no __all__ re-export
    AdminClient,
    NewTopic,  # pyright: ignore[reportPrivateImportUsage]
)
from psycopg import errors as pg_errors
from ubunturemit_asco.models import AuditRecord
from ubunturemit_audit import (
    AuditLogUnavailableError,
    AuditPositionConflictError,
    KafkaAuditConsumer,
    KafkaAuditLogger,
    LogPosition,
    OverPrivilegedAuditStoreError,
    PostgresAuditStore,
    install_schema,
)
from ubunturemit_domain import TransferId

pytestmark = pytest.mark.integration

PG_PORT = os.environ.get("UBUNTUREMIT_PG_PORT", "55432")
OWNER_DSN = os.environ.get(
    "UBUNTUREMIT_PG_OWNER_DSN",
    f"postgresql://ubunturemit:ubunturemit@localhost:{PG_PORT}/ubunturemit",
)
KAFKA = os.environ.get("UBUNTUREMIT_KAFKA_BOOTSTRAP", "localhost:29092")
# A login role for the tests, made a member of audit_writer -- the shape a deployment
# uses, where the service logs in as its own user and inherits only SELECT + INSERT.
APP_ROLE = "audit_app_integration"
APP_DSN = f"postgresql://{APP_ROLE}:{APP_ROLE}@localhost:{PG_PORT}/ubunturemit"


@pytest.fixture(scope="module")
def writer_dsn() -> str:
    with psycopg.connect(OWNER_DSN, autocommit=True) as owner:
        install_schema(owner)
        owner.execute(
            f"""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                    CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_ROLE}';
                END IF;
            END $$
            """  # noqa: S608 -- APP_ROLE is a module constant
        )
        owner.execute(f"GRANT audit_writer TO {APP_ROLE}")
    return APP_DSN


@pytest.fixture
def store(writer_dsn: str) -> Iterator[PostgresAuditStore]:
    s = PostgresAuditStore(writer_dsn)
    yield s
    s.close()


def _record(transfer_id: str, actor: str = "orchestrator") -> AuditRecord:
    return AuditRecord(
        transfer_id=TransferId(transfer_id),
        actor=actor,
        thought="integration",
        action="append",
        observation="ok",
        recorded_at="2026-10-10T10:00:00+00:00",
    )


def test_writer_role_cannot_update_or_delete(writer_dsn: str, store: PostgresAuditStore) -> None:
    t_id = f"TR-INT-{uuid.uuid4().hex[:8]}"
    store.append(_record(t_id))
    with psycopg.connect(writer_dsn, autocommit=True) as conn:
        with pytest.raises(pg_errors.InsufficientPrivilege):
            conn.execute(
                "UPDATE audit_records SET actor = 'forged' WHERE transfer_id = %s", (t_id,)
            )
        with pytest.raises(pg_errors.InsufficientPrivilege):
            conn.execute("DELETE FROM audit_records WHERE transfer_id = %s", (t_id,))
        with pytest.raises(pg_errors.InsufficientPrivilege):
            conn.execute("TRUNCATE audit_records")
    assert [r.actor for r in store.get_records(TransferId(t_id))] == ["orchestrator"]


def test_triggers_hold_even_for_the_owner(store: PostgresAuditStore) -> None:
    t_id = f"TR-INT-{uuid.uuid4().hex[:8]}"
    store.append(_record(t_id))
    with psycopg.connect(OWNER_DSN, autocommit=True) as owner:
        with pytest.raises(pg_errors.RaiseException, match="append-only"):
            owner.execute(
                "UPDATE audit_records SET actor = 'forged' WHERE transfer_id = %s", (t_id,)
            )
        with pytest.raises(pg_errors.RaiseException, match="append-only"):
            owner.execute("DELETE FROM audit_records WHERE transfer_id = %s", (t_id,))


def test_store_refuses_an_over_privileged_role(writer_dsn: str) -> None:
    with pytest.raises(OverPrivilegedAuditStoreError):
        PostgresAuditStore(OWNER_DSN)


def test_redelivered_message_is_stored_once(store: PostgresAuditStore) -> None:
    t_id = f"TR-INT-{uuid.uuid4().hex[:8]}"
    position = LogPosition(topic=f"redelivery-{t_id}", partition=0, offset=7)
    assert store.append_from_log(_record(t_id), position) is True
    assert store.append_from_log(_record(t_id), position) is False
    assert len(store.get_records(TransferId(t_id))) == 1


def test_record_published_on_the_bus_lands_in_the_store(store: PostgresAuditStore) -> None:
    # A topic per run: the production `asco.audit` topic is created by operations with the
    # SARB-mandated retention, which this project does not have yet -- tests never create it.
    topic = f"asco.audit.it-{uuid.uuid4().hex[:8]}"
    admin = AdminClient({"bootstrap.servers": KAFKA})
    admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)])[topic].result(
        timeout=30
    )

    t_id = f"TR-INT-{uuid.uuid4().hex[:8]}"
    KafkaAuditLogger({"bootstrap.servers": KAFKA}, topic=topic).log_record(
        _record(t_id, actor="compliance_sentinel")
    )

    consumer = KafkaAuditConsumer(
        store, {"bootstrap.servers": KAFKA, "group.id": f"it-{t_id}"}, topic=topic
    )
    try:
        deadline = time.monotonic() + 30
        landed = None
        while landed is None and time.monotonic() < deadline:
            landed = consumer.poll_once(1.0)
    finally:
        consumer.close()
        admin.delete_topics([topic])

    assert landed is not None
    assert [r.actor for r in store.get_records(TransferId(t_id))] == ["compliance_sentinel"]


def test_logger_fails_closed_when_the_broker_is_unreachable() -> None:
    logger = KafkaAuditLogger(
        {"bootstrap.servers": "localhost:1", "message.timeout.ms": 1000},
        topic="asco.audit.unreachable",
        delivery_timeout_s=3.0,
    )
    with pytest.raises(AuditLogUnavailableError):
        logger.log_record(_record("TR-INT-UNREACHABLE"))


def test_a_different_record_at_a_taken_position_is_never_dropped(
    store: PostgresAuditStore,
) -> None:
    """A recreated topic reuses offsets; a new record there must raise, not vanish."""
    t_id = f"TR-INT-{uuid.uuid4().hex[:8]}"
    position = LogPosition(topic=f"recreated-{t_id}", partition=0, offset=0)
    store.append_from_log(_record(t_id, actor="orchestrator"), position)
    with pytest.raises(AuditPositionConflictError):
        store.append_from_log(_record(t_id, actor="exit_validator"), position)
