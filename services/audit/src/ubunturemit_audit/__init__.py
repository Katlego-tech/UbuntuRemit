"""UbuntuRemit Audit Service."""

from ubunturemit_audit.consumer import AuditConsumer, parse_audit_record
from ubunturemit_audit.kafka import (
    AUDIT_TOPIC,
    AuditLogUnavailableError,
    KafkaAuditConsumer,
    KafkaAuditLogger,
    serialize_audit_record,
)
from ubunturemit_audit.postgres_store import (
    LogPosition,
    OverPrivilegedAuditStoreError,
    PostgresAuditStore,
)
from ubunturemit_audit.schema import WRITER_ROLE, install_schema
from ubunturemit_audit.store import (
    AuditStore,
    AuditStoreImmutableError,
    InMemoryAuditStore,
    SqliteAuditStore,
)
from ubunturemit_audit.verifier import verify_audit_completeness

__all__ = [
    "AUDIT_TOPIC",
    "AuditLogUnavailableError",
    "KafkaAuditConsumer",
    "KafkaAuditLogger",
    "LogPosition",
    "OverPrivilegedAuditStoreError",
    "PostgresAuditStore",
    "WRITER_ROLE",
    "install_schema",
    "parse_audit_record",
    "serialize_audit_record",
    "AuditConsumer",
    "AuditStore",
    "AuditStoreImmutableError",
    "InMemoryAuditStore",
    "SqliteAuditStore",
    "verify_audit_completeness",
]
