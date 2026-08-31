"""Tests for SettlementInstruction and BAH integration -- docs/design/domain-model.md §3."""

from datetime import UTC, datetime

import pytest
from ubunturemit_domain import SettlementRail
from ubunturemit_messaging.bah import (
    BusinessApplicationHeader,
    build_bah,
    parse_bah,
)
from ubunturemit_messaging.settlement import SettlementInstruction


def test_settlement_instruction_creation_and_enveloping() -> None:
    """Verify SettlementInstruction fields and enveloped XML generation."""
    bah = BusinessApplicationHeader(
        from_bic="UBUNZAJJXXX",
        to_bic="SARBZAJJXXX",
        business_msg_id="UB-99420-X-01",
        message_definition_id="pacs.008.001.08",
        creation_date_time="2026-08-31T10:15:30Z",
    )
    bah_xml = build_bah(bah)
    payload_xml = (
        "<Document xmlns='urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08'>"
        "<FIToFICstmrCdtTrf/>"
        "</Document>"
    )

    instruction = SettlementInstruction(
        transfer_id="TR-001",
        rail=SettlementRail.SWIFT,
        iso20022_message_id="MSG-001",
        business_application_header_xml=bah_xml,
        payload_xml=payload_xml,
        submitted_at=datetime(2026, 8, 31, 10, 15, 30, tzinfo=UTC),
    )

    assert instruction.transfer_id == "TR-001"
    assert instruction.rail == SettlementRail.SWIFT
    assert instruction.iso20022_message_id == "MSG-001"
    assert instruction.business_application_header_xml == bah_xml
    assert instruction.payload_xml == payload_xml

    # Check that BAH inside instruction can be parsed
    parsed_header = parse_bah(instruction.business_application_header_xml)
    assert parsed_header.business_msg_id == "UB-99420-X-01"

    # Check enveloped XML
    enveloped = instruction.enveloped_xml()
    assert "<RequestPayload>" in enveloped
    assert "<AppHdr" in enveloped
    assert "<Document" in enveloped


def test_settlement_instruction_validation() -> None:
    """Validate type and timezone constraints on SettlementInstruction."""
    with pytest.raises(ValueError, match="timezone-aware"):
        SettlementInstruction(
            transfer_id="TR-001",
            rail=SettlementRail.PAPSS,
            iso20022_message_id="MSG-001",
            business_application_header_xml="<AppHdr/>",
            payload_xml="<Document/>",
            submitted_at=datetime(2026, 8, 31, 10, 15, 30),  # noqa: DTZ001 - deliberate naive test
        )
