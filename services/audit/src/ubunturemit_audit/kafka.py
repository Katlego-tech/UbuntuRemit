"""The `asco.audit` transport -- docs/design/asco-orchestrator.md §3, §4 (T050a).

KafkaAuditLogger is what the negotiation loop writes through: it returns only once the
broker has acknowledged the record, and raises otherwise, so the loop refuses the
transfer (an unauditable settlement is worse than a failed one). KafkaAuditConsumer
moves records from the topic into the Postgres store, committing each offset only after
the row is written.
"""

import dataclasses
import json
from collections.abc import Callable, Mapping

from confluent_kafka import Consumer, KafkaError, KafkaException, Message, Producer
from ubunturemit_asco.models import AuditRecord

from ubunturemit_audit.consumer import parse_audit_record
from ubunturemit_audit.postgres_store import LogPosition, PostgresAuditStore

AUDIT_TOPIC = "asco.audit"


class AuditLogUnavailableError(ConnectionError):
    """The broker did not acknowledge an audit record."""


class MalformedAuditMessageError(ValueError):
    """A message on the audit topic is not a valid AuditRecord.

    Its offset is never committed, so the consumer stops at it rather than skipping an
    audit record. There is deliberately no dead-letter path: an operator decides what an
    unreadable audit record means.
    """


def serialize_audit_record(record: AuditRecord) -> bytes:
    return json.dumps(dataclasses.asdict(record)).encode("utf-8")


class KafkaAuditLogger:
    """Implements ubunturemit_asco's AuditLogger over Kafka, failing closed."""

    def __init__(
        self,
        config: Mapping[str, str | int | bool],
        topic: str = AUDIT_TOPIC,
        delivery_timeout_s: float = 10.0,
    ) -> None:
        # acks=all + idempotence: a record is acknowledged only once every in-sync
        # replica has it, and a retried send is never written twice.
        # message.timeout.ms is pinned to the delivery timeout, after the caller's config:
        # left at librdkafka's 300 s default, a record this call reported as undelivered
        # could still reach the broker later, for a transfer that was already refused.
        self._producer = Producer(
            {
                "acks": "all",
                "enable.idempotence": True,
                **config,
                "message.timeout.ms": int(delivery_timeout_s * 1000),
            }
        )
        self._topic = topic
        self._timeout = delivery_timeout_s

    def log_record(self, record: AuditRecord) -> None:
        errors: list[KafkaError] = []

        def on_delivery(err: KafkaError | None, _msg: Message) -> None:
            if err is not None:
                errors.append(err)

        try:
            self._producer.produce(
                self._topic,
                key=str(record.transfer_id).encode("utf-8"),
                value=serialize_audit_record(record),
                on_delivery=on_delivery,
            )
        except (KafkaException, BufferError) as err:
            raise AuditLogUnavailableError(f"Audit record not sent: {err}") from err
        if self._producer.flush(self._timeout) > 0:
            raise AuditLogUnavailableError(
                f"Audit record not acknowledged within {self._timeout}s."
            )
        if errors:
            raise AuditLogUnavailableError(f"Audit record rejected by the broker: {errors[0]}")


class KafkaAuditConsumer:
    """Consumes `asco.audit` into the append-only store, at least once, stored once."""

    def __init__(
        self,
        store: PostgresAuditStore,
        config: Mapping[str, str | int | bool],
        topic: str = AUDIT_TOPIC,
    ) -> None:
        self._store = store
        self._consumer = Consumer(
            {"enable.auto.commit": False, "auto.offset.reset": "earliest", **config}
        )
        self._consumer.subscribe([topic])

    def poll_once(self, timeout_s: float = 1.0) -> AuditRecord | None:
        """Store at most one record; None when nothing arrived within the timeout."""
        msg = self._consumer.poll(timeout_s)
        if msg is None:
            return None
        if msg.error() is not None:
            raise KafkaException(msg.error())
        value = msg.value()
        topic, partition, offset = msg.topic(), msg.partition(), msg.offset()
        if value is None or topic is None or partition is None or offset is None:
            raise KafkaException(f"Malformed audit message at {topic}/{partition}/{offset}")
        try:
            record = parse_audit_record(value)
        except (ValueError, KeyError, TypeError) as err:
            raise MalformedAuditMessageError(
                f"Unreadable audit message at {topic}/{partition}/{offset}: {err}"
            ) from err
        self._store.append_from_log(record, LogPosition(topic, partition, offset))
        # Commit only after the row is durable: a crash in between redelivers the
        # message, and its position makes the second insert a no-op.
        self._consumer.commit(message=msg, asynchronous=False)
        return record

    def run(self, should_stop: Callable[[], bool], timeout_s: float = 1.0) -> None:
        while not should_stop():
            self.poll_once(timeout_s)

    def close(self) -> None:
        self._consumer.close()
