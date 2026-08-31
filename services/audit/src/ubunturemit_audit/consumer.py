"""Kafka asco.audit consumer -- docs/design/asco-orchestrator.md §3, §4."""

import json

from ubunturemit_asco.models import AuditRecord
from ubunturemit_domain import TransferId

from ubunturemit_audit.store import AuditStore


class AuditConsumer:
    """Consumes serialized AuditRecord payloads from Kafka asco.audit and appends to the store."""

    def __init__(self, store: AuditStore) -> None:
        self._store = store

    def process_message(self, message_payload: str | bytes) -> AuditRecord:
        """Process a single Kafka message payload and append to the store."""
        if isinstance(message_payload, bytes):
            message_payload = message_payload.decode("utf-8")

        data = json.loads(message_payload)
        record = AuditRecord(
            transfer_id=TransferId(data["transfer_id"]),
            actor=data["actor"],
            thought=data["thought"],
            action=data["action"],
            observation=data["observation"],
            recorded_at=data["recorded_at"],
            deterministic_override=bool(data.get("deterministic_override", False)),
        )
        self._store.append(record)
        return record
