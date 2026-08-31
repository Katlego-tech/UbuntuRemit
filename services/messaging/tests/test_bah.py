"""Tests for Business Application Header (head.001.001.02) builder, parser, and envelope."""

from pathlib import Path

import pytest
from lxml import etree
from ubunturemit_messaging.bah import (
    BusinessApplicationHeader,
    build_bah,
    envelope_message,
    parse_bah,
)

HEAD_XSD_PATH = Path(__file__).resolve().parent.parent / "schemas" / "head.001.001.02.xsd"


@pytest.fixture
def sample_bah() -> BusinessApplicationHeader:
    """Sample Business Application Header."""
    return BusinessApplicationHeader(
        from_bic="UBUNZAJJXXX",
        to_bic="SARBZAJJXXX",
        business_msg_id="UB-99420-X-01",
        message_definition_id="pacs.008.001.08",
        creation_date_time="2026-08-31T10:15:30Z",
    )


def test_build_bah_validates_against_xsd(sample_bah: BusinessApplicationHeader) -> None:
    """Emitted BAH XML must strictly validate against admitted head.001.001.02.xsd."""
    bah_xml = build_bah(sample_bah)

    schema_doc = etree.parse(str(HEAD_XSD_PATH))
    xmlschema = etree.XMLSchema(schema_doc)

    doc = etree.fromstring(bah_xml.encode("utf-8"))
    assert xmlschema.validate(doc), f"BAH XML failed XSD validation: {xmlschema.error_log}"


def test_bah_round_trip(sample_bah: BusinessApplicationHeader) -> None:
    """build_bah -> parse_bah must be completely lossless."""
    bah_xml = build_bah(sample_bah)
    parsed = parse_bah(bah_xml)

    assert parsed.from_bic == sample_bah.from_bic
    assert parsed.to_bic == sample_bah.to_bic
    assert parsed.business_msg_id == sample_bah.business_msg_id
    assert parsed.message_definition_id == sample_bah.message_definition_id
    assert parsed.creation_date_time == sample_bah.creation_date_time


def test_parse_bah_rejects_malformed_xml() -> None:
    """Reject malformed XML strings."""
    with pytest.raises(ValueError, match="XML syntax error"):
        parse_bah("<AppHdr><unclosed>")


def test_parse_bah_rejects_wrong_namespace() -> None:
    """Reject AppHdr in an incorrect namespace."""
    wrong_ns_xml = """<?xml version="1.0" encoding="UTF-8"?>
<AppHdr xmlns="urn:iso:std:iso:20022:tech:xsd:head.001.001.01">
    <Fr><FIId><FinInstnId><BICFI>UBUNZAJJXXX</BICFI></FinInstnId></FIId></Fr>
    <To><FIId><FinInstnId><BICFI>SARBZAJJXXX</BICFI></FinInstnId></FIId></To>
    <BizMsgIdr>UB-1</BizMsgIdr>
    <MsgDefIdr>pacs.008.001.08</MsgDefIdr>
    <CreDt>2026-08-31T10:00:00Z</CreDt>
</AppHdr>"""
    with pytest.raises(ValueError, match="Unexpected namespace"):
        parse_bah(wrong_ns_xml)


def test_parse_bah_rejects_missing_mandatory_fields() -> None:
    """Reject AppHdr missing mandatory elements."""
    missing_msgid_xml = """<?xml version="1.0" encoding="UTF-8"?>
<AppHdr xmlns="urn:iso:std:iso:20022:tech:xsd:head.001.001.02">
    <Fr><FIId><FinInstnId><BICFI>UBUNZAJJXXX</BICFI></FinInstnId></FIId></Fr>
    <To><FIId><FinInstnId><BICFI>SARBZAJJXXX</BICFI></FinInstnId></FIId></To>
    <MsgDefIdr>pacs.008.001.08</MsgDefIdr>
    <CreDt>2026-08-31T10:00:00Z</CreDt>
</AppHdr>"""
    with pytest.raises(ValueError, match="Missing required element 'BizMsgIdr'"):
        parse_bah(missing_msgid_xml)


def test_envelope_message(sample_bah: BusinessApplicationHeader) -> None:
    """Verify BAH and Payload XML enveloping."""
    bah_xml = build_bah(sample_bah)
    payload_xml = (
        "<Document xmlns='urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08'>"
        "<FIToFICstmrCdtTrf/>"
        "</Document>"
    )

    enveloped = envelope_message(bah_xml, payload_xml)
    assert "<RequestPayload>" in enveloped
    assert "<AppHdr" in enveloped
    assert "<Document" in enveloped

    # Parse and verify elements are present
    root = etree.fromstring(enveloped.encode("utf-8"))
    assert root.tag == "RequestPayload"
    assert len(root) == 2
