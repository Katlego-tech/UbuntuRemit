"""Business Application Header (head.001.001.02) builder, parser, and envelope.

Implements ISO 20022 BusinessApplicationHeaderV02 per docs/design/iso20022-messaging.md §3.4
and docs/design/domain-model.md §3 (SettlementInstruction).
"""

from dataclasses import dataclass

from lxml import etree

HEAD_001_001_02_NS = "urn:iso:std:iso:20022:tech:xsd:head.001.001.02"


@dataclass(frozen=True)
class BusinessApplicationHeader:
    """Canonical representation of ISO 20022 head.001.001.02 Business Application Header."""

    from_bic: str
    to_bic: str
    business_msg_id: str
    message_definition_id: str
    creation_date_time: str
    business_service: str | None = None
    copy_duplicate: str | None = None
    possible_duplicate: bool | None = None
    priority: str | None = None


def build_bah(header: BusinessApplicationHeader) -> str:
    """Build a compliant head.001.001.02 XML document from BusinessApplicationHeader."""
    nsmap = {None: HEAD_001_001_02_NS}
    root = etree.Element(f"{{{HEAD_001_001_02_NS}}}AppHdr", nsmap=nsmap)

    # 1. From Party (Fr)
    fr_elem = etree.SubElement(root, f"{{{HEAD_001_001_02_NS}}}Fr")
    fr_fi = etree.SubElement(fr_elem, f"{{{HEAD_001_001_02_NS}}}FIId")
    fr_fin_id = etree.SubElement(fr_fi, f"{{{HEAD_001_001_02_NS}}}FinInstnId")
    fr_bic = etree.SubElement(fr_fin_id, f"{{{HEAD_001_001_02_NS}}}BICFI")
    fr_bic.text = header.from_bic

    # 2. To Party (To)
    to_elem = etree.SubElement(root, f"{{{HEAD_001_001_02_NS}}}To")
    to_fi = etree.SubElement(to_elem, f"{{{HEAD_001_001_02_NS}}}FIId")
    to_fin_id = etree.SubElement(to_fi, f"{{{HEAD_001_001_02_NS}}}FinInstnId")
    to_bic = etree.SubElement(to_fin_id, f"{{{HEAD_001_001_02_NS}}}BICFI")
    to_bic.text = header.to_bic

    # 3. Business Message Identifier (BizMsgIdr)
    biz_msg_id = etree.SubElement(root, f"{{{HEAD_001_001_02_NS}}}BizMsgIdr")
    biz_msg_id.text = header.business_msg_id

    # 4. Message Definition Identifier (MsgDefIdr)
    msg_def_id = etree.SubElement(root, f"{{{HEAD_001_001_02_NS}}}MsgDefIdr")
    msg_def_id.text = header.message_definition_id

    # 5. Optional Business Service (BizSvc)
    if header.business_service:
        biz_svc = etree.SubElement(root, f"{{{HEAD_001_001_02_NS}}}BizSvc")
        biz_svc.text = header.business_service

    # 6. Creation Date Time (CreDt)
    cre_dt = etree.SubElement(root, f"{{{HEAD_001_001_02_NS}}}CreDt")
    cre_dt.text = header.creation_date_time

    # 7. Optional Copy/Duplicate (CpyDplct)
    if header.copy_duplicate:
        cpy = etree.SubElement(root, f"{{{HEAD_001_001_02_NS}}}CpyDplct")
        cpy.text = header.copy_duplicate

    # 8. Optional Possible Duplicate (PssblDplct)
    if header.possible_duplicate is not None:
        pssbl = etree.SubElement(root, f"{{{HEAD_001_001_02_NS}}}PssblDplct")
        pssbl.text = "true" if header.possible_duplicate else "false"

    # 9. Optional Priority (Prty)
    if header.priority:
        prty = etree.SubElement(root, f"{{{HEAD_001_001_02_NS}}}Prty")
        prty.text = header.priority

    xml_bytes = etree.tostring(
        root,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    )
    return xml_bytes.decode("utf-8")


def parse_bah(xml_input: str | bytes) -> BusinessApplicationHeader:
    """Parse and validate a head.001.001.02 AppHdr XML into BusinessApplicationHeader."""
    if isinstance(xml_input, str):
        xml_bytes = xml_input.encode("utf-8")
    else:
        xml_bytes = xml_input

    try:
        root = etree.fromstring(xml_bytes)
    except (etree.XMLSyntaxError, OSError) as err:
        raise ValueError(f"XML syntax error in Business Application Header: {err}") from err

    # Check root element and namespace
    expected_tag = f"{{{HEAD_001_001_02_NS}}}AppHdr"
    if root.tag != expected_tag:
        actual_ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
        if actual_ns != HEAD_001_001_02_NS:
            raise ValueError(
                f"Unexpected namespace '{actual_ns}' in AppHdr. Expected '{HEAD_001_001_02_NS}'"
            )
        raise ValueError(f"Expected root tag <AppHdr>, got <{root.tag}>")

    def _find_text(path: str, mandatory: bool = True) -> str | None:
        elem = root.find(path, namespaces={"head": HEAD_001_001_02_NS})
        if elem is None or elem.text is None:
            if mandatory:
                field_name = path.split("/")[-1].replace("head:", "")
                raise ValueError(f"Missing required element '{field_name}' in AppHdr")
            return None
        return elem.text.strip()

    from_bic = _find_text("head:Fr/head:FIId/head:FinInstnId/head:BICFI")
    to_bic = _find_text("head:To/head:FIId/head:FinInstnId/head:BICFI")
    biz_msg_id = _find_text("head:BizMsgIdr")
    msg_def_id = _find_text("head:MsgDefIdr")
    cre_dt = _find_text("head:CreDt")
    biz_svc = _find_text("head:BizSvc", mandatory=False)
    cpy_dplct = _find_text("head:CpyDplct", mandatory=False)
    pssbl_raw = _find_text("head:PssblDplct", mandatory=False)
    pssbl = pssbl_raw.lower() == "true" if pssbl_raw else None
    priority = _find_text("head:Prty", mandatory=False)

    return BusinessApplicationHeader(
        from_bic=from_bic or "",
        to_bic=to_bic or "",
        business_msg_id=biz_msg_id or "",
        message_definition_id=msg_def_id or "",
        creation_date_time=cre_dt or "",
        business_service=biz_svc,
        copy_duplicate=cpy_dplct,
        possible_duplicate=pssbl,
        priority=priority,
    )


def envelope_message(bah_xml: str, payload_xml: str) -> str:
    """Envelope a Business Application Header and ISO 20022 Payload into RequestPayload."""
    bah_root = etree.fromstring(bah_xml.encode("utf-8"))
    payload_root = etree.fromstring(payload_xml.encode("utf-8"))

    wrapper = etree.Element("RequestPayload")
    wrapper.append(bah_root)
    wrapper.append(payload_root)

    return etree.tostring(
        wrapper,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    ).decode("utf-8")
