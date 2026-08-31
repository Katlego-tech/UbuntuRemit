"""SettlementInstruction entity -- docs/design/domain-model.md §3."""

from dataclasses import dataclass
from datetime import datetime

from ubunturemit_domain import SettlementRail

from ubunturemit_messaging.bah import envelope_message


@dataclass(frozen=True, slots=True)
class SettlementInstruction:
    """Outbound ISO 20022 settlement instruction passed to rail adapters."""

    transfer_id: str
    rail: SettlementRail
    iso20022_message_id: str
    business_application_header_xml: str
    payload_xml: str
    submitted_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.transfer_id, str) or not self.transfer_id.strip():
            raise ValueError("transfer_id must be a non-blank string")
        if not isinstance(self.rail, SettlementRail):
            raise TypeError(f"rail must be a SettlementRail, got {type(self.rail).__name__}")
        if not isinstance(self.iso20022_message_id, str) or not self.iso20022_message_id.strip():
            raise ValueError("iso20022_message_id must be a non-blank string")
        if (
            not isinstance(self.business_application_header_xml, str)
            or not self.business_application_header_xml.strip()
        ):
            raise ValueError("business_application_header_xml must be a non-blank XML string")
        if not isinstance(self.payload_xml, str) or not self.payload_xml.strip():
            raise ValueError("payload_xml must be a non-blank XML string")
        if not isinstance(self.submitted_at, datetime):
            raise TypeError(
                f"submitted_at must be a datetime, got {type(self.submitted_at).__name__}"
            )
        if self.submitted_at.tzinfo is None or self.submitted_at.utcoffset() is None:
            raise ValueError("submitted_at must be timezone-aware (DTZ)")

    def enveloped_xml(self) -> str:
        """Produce the combined RequestPayload containing BAH and Payload Document."""
        return envelope_message(self.business_application_header_xml, self.payload_xml)
