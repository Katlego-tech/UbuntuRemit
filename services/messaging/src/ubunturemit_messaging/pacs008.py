"""pacs.008.001.08 message builder and parser -- docs/design/iso20022-messaging.md §5."""

from datetime import UTC, datetime
from decimal import Decimal

from lxml import etree
from ubunturemit_domain import (
    ComplianceDeclaration,
    Corridor,
    CountryCode,
    CurrencyCode,
    FxQuote,
    Money,
    Party,
    PaymentPurpose,
    RateSource,
    SettlementRail,
    SourceOfFunds,
    Transfer,
    TransferId,
    TransferQuote,
    TransferState,
)

from ubunturemit_messaging.pain001 import (
    ISO_TO_PURPOSE,
    PURPOSE_TO_ISO,
    decimal_str_to_minor_units,
    minor_units_to_decimal_str,
)

PACS008_NS = "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08"


def build_pacs008(transfer: Transfer) -> str:
    """Build a compliant pacs.008.001.08 XML document from a Transfer aggregate."""
    nsmap = {None: PACS008_NS}
    root = etree.Element(f"{{{PACS008_NS}}}Document", nsmap=nsmap)
    cstmr_trf = etree.SubElement(root, f"{{{PACS008_NS}}}FIToFICstmrCdtTrf")

    # 1. Group Header (GrpHdr)
    grp_hdr = etree.SubElement(cstmr_trf, f"{{{PACS008_NS}}}GrpHdr")
    msg_id = etree.SubElement(grp_hdr, f"{{{PACS008_NS}}}MsgId")
    msg_id.text = f"PACS-{transfer.reference}"

    cre_dt_tm = etree.SubElement(grp_hdr, f"{{{PACS008_NS}}}CreDtTm")
    cre_dt_tm.text = transfer.created_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    nb_of_txs = etree.SubElement(grp_hdr, f"{{{PACS008_NS}}}NbOfTxs")
    nb_of_txs.text = "1"

    # Settlement Information (SttlmInf)
    sttlm_inf = etree.SubElement(grp_hdr, f"{{{PACS008_NS}}}SttlmInf")
    sttlm_mtd = etree.SubElement(sttlm_inf, f"{{{PACS008_NS}}}SttlmMtd")
    if transfer.rail == SettlementRail.PAPSS:
        sttlm_mtd.text = "CLRG"
        clr_sys = etree.SubElement(sttlm_inf, f"{{{PACS008_NS}}}ClrSys")
        clr_prtry = etree.SubElement(clr_sys, f"{{{PACS008_NS}}}Prtry")
        clr_prtry.text = "PAPSS"
    else:
        sttlm_mtd.text = "INDA"

    # 2. Credit Transfer Transaction Information (CdtTrfTxInf)
    cdt_trf = etree.SubElement(cstmr_trf, f"{{{PACS008_NS}}}CdtTrfTxInf")

    # Payment ID
    pmt_id = etree.SubElement(cdt_trf, f"{{{PACS008_NS}}}PmtId")
    e2e_id = etree.SubElement(pmt_id, f"{{{PACS008_NS}}}EndToEndId")
    e2e_id.text = transfer.reference

    tx_id = etree.SubElement(pmt_id, f"{{{PACS008_NS}}}TxId")
    tx_id.text = transfer.id

    # Interbank Settlement Amount & Date
    settle_amount = transfer.quote.recipient_receives
    intr_bk_amt = etree.SubElement(cdt_trf, f"{{{PACS008_NS}}}IntrBkSttlmAmt")
    intr_bk_amt.set("Ccy", settle_amount.currency.value)
    intr_bk_amt.text = minor_units_to_decimal_str(settle_amount.minor_units)

    intr_bk_dt = etree.SubElement(cdt_trf, f"{{{PACS008_NS}}}IntrBkSttlmDt")
    intr_bk_dt.text = transfer.created_at.astimezone(UTC).strftime("%Y-%m-%d")

    # Charge Bearer
    chrg_br = etree.SubElement(cdt_trf, f"{{{PACS008_NS}}}ChrgBr")
    chrg_br.text = "SLEV"

    # Debtor (Sender)
    dbtr = etree.SubElement(cdt_trf, f"{{{PACS008_NS}}}Dbtr")
    dbtr_nm = etree.SubElement(dbtr, f"{{{PACS008_NS}}}Nm")
    dbtr_nm.text = transfer.sender.full_name
    dbtr_adr = etree.SubElement(dbtr, f"{{{PACS008_NS}}}PstlAdr")
    dbtr_ctry = etree.SubElement(dbtr_adr, f"{{{PACS008_NS}}}Ctry")
    dbtr_ctry.text = str(transfer.sender.country)

    # Debtor Account
    dbtr_acct = etree.SubElement(cdt_trf, f"{{{PACS008_NS}}}DbtrAcct")
    dbtr_acct_id = etree.SubElement(dbtr_acct, f"{{{PACS008_NS}}}Id")
    dbtr_othr = etree.SubElement(dbtr_acct_id, f"{{{PACS008_NS}}}Othr")
    dbtr_othr_id = etree.SubElement(dbtr_othr, f"{{{PACS008_NS}}}Id")
    dbtr_othr_id.text = transfer.sender.account_number

    # Debtor Agent
    dbtr_agt = etree.SubElement(cdt_trf, f"{{{PACS008_NS}}}DbtrAgt")
    dbtr_fin_id = etree.SubElement(dbtr_agt, f"{{{PACS008_NS}}}FinInstnId")
    dbtr_bic = etree.SubElement(dbtr_fin_id, f"{{{PACS008_NS}}}BICFI")
    dbtr_bic.text = transfer.sender.bic

    # Creditor Agent
    cdtr_agt = etree.SubElement(cdt_trf, f"{{{PACS008_NS}}}CdtrAgt")
    cdtr_fin_id = etree.SubElement(cdtr_agt, f"{{{PACS008_NS}}}FinInstnId")
    cdtr_bic = etree.SubElement(cdtr_fin_id, f"{{{PACS008_NS}}}BICFI")
    cdtr_bic.text = transfer.recipient.bic

    # Creditor (Recipient)
    cdtr = etree.SubElement(cdt_trf, f"{{{PACS008_NS}}}Cdtr")
    cdtr_nm = etree.SubElement(cdtr, f"{{{PACS008_NS}}}Nm")
    cdtr_nm.text = transfer.recipient.full_name
    cdtr_adr = etree.SubElement(cdtr, f"{{{PACS008_NS}}}PstlAdr")
    cdtr_ctry = etree.SubElement(cdtr_adr, f"{{{PACS008_NS}}}Ctry")
    cdtr_ctry.text = str(transfer.recipient.country)

    # Creditor Account
    cdtr_acct = etree.SubElement(cdt_trf, f"{{{PACS008_NS}}}CdtrAcct")
    cdtr_acct_id = etree.SubElement(cdtr_acct, f"{{{PACS008_NS}}}Id")
    cdtr_othr = etree.SubElement(cdtr_acct_id, f"{{{PACS008_NS}}}Othr")
    cdtr_othr_id = etree.SubElement(cdtr_othr, f"{{{PACS008_NS}}}Id")
    cdtr_othr_id.text = transfer.recipient.account_number

    # Purpose
    iso_purp = PURPOSE_TO_ISO.get(transfer.declaration.purpose)
    if iso_purp:
        purp = etree.SubElement(cdt_trf, f"{{{PACS008_NS}}}Purp")
        purp_cd = etree.SubElement(purp, f"{{{PACS008_NS}}}Cd")
        purp_cd.text = iso_purp

    # Remittance Information
    rmt_inf = etree.SubElement(cdt_trf, f"{{{PACS008_NS}}}RmtInf")
    ustrd = etree.SubElement(rmt_inf, f"{{{PACS008_NS}}}Ustrd")
    ustrd.text = transfer.reference

    return etree.tostring(
        root,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    ).decode("utf-8")


def parse_pacs008(xml_input: str | bytes) -> Transfer:
    """Parse a pacs.008.001.08 XML document into a canonical Transfer aggregate."""
    if isinstance(xml_input, str):
        xml_bytes = xml_input.encode("utf-8")
    else:
        xml_bytes = xml_input

    try:
        root = etree.fromstring(xml_bytes)
    except (etree.XMLSyntaxError, OSError) as err:
        raise ValueError(f"XML syntax error in pacs.008: {err}") from err

    expected_tag = f"{{{PACS008_NS}}}Document"
    if root.tag != expected_tag:
        actual_ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
        if actual_ns != PACS008_NS:
            raise ValueError(
                f"Unexpected namespace '{actual_ns}' in pacs.008. Expected '{PACS008_NS}'"
            )
        raise ValueError(f"Expected root tag <Document>, got <{root.tag}>")

    namespaces = {"p": PACS008_NS}

    def _get_text(xpath: str, default: str = "") -> str:
        elem = root.find(xpath, namespaces=namespaces)
        if elem is not None and elem.text is not None:
            return elem.text.strip()
        return default

    # Extract Header & IDs
    ref = _get_text(".//p:CdtTrfTxInf/p:PmtId/p:EndToEndId")
    tx_id_str = _get_text(".//p:CdtTrfTxInf/p:PmtId/p:TxId") or f"TR-{ref}"
    if not ref:
        raise ValueError("Missing EndToEndId in pacs.008")

    cre_dt_raw = _get_text(".//p:GrpHdr/p:CreDtTm")
    if cre_dt_raw:
        created_at = datetime.fromisoformat(cre_dt_raw.replace("Z", "+00:00"))
    else:
        created_at = datetime.now(UTC)

    # Settlement method / Rail
    sttlm_mtd_str = _get_text(".//p:GrpHdr/p:SttlmInf/p:SttlmMtd")
    clr_sys_str = _get_text(".//p:GrpHdr/p:SttlmInf/p:ClrSys/p:Prtry")
    if sttlm_mtd_str == "CLRG" or clr_sys_str == "PAPSS":
        rail = SettlementRail.PAPSS
    else:
        rail = SettlementRail.SWIFT

    # Sender (Debtor)
    sender_name = _get_text(".//p:CdtTrfTxInf/p:Dbtr/p:Nm")
    sender_country_str = _get_text(".//p:CdtTrfTxInf/p:Dbtr/p:PstlAdr/p:Ctry", "ZA")
    sender_acct = _get_text(".//p:CdtTrfTxInf/p:DbtrAcct/p:Id/p:Othr/p:Id") or _get_text(
        ".//p:CdtTrfTxInf/p:DbtrAcct/p:Id/p:IBAN"
    )
    sender_bic = _get_text(".//p:CdtTrfTxInf/p:DbtrAgt/p:FinInstnId/p:BICFI")

    sender = Party(
        full_name=sender_name,
        account_number=sender_acct,
        bic=sender_bic,
        country=CountryCode(sender_country_str),
    )

    # Recipient (Creditor)
    recipient_name = _get_text(".//p:CdtTrfTxInf/p:Cdtr/p:Nm")
    recipient_country_str = _get_text(".//p:CdtTrfTxInf/p:Cdtr/p:PstlAdr/p:Ctry", "GH")
    recipient_acct = _get_text(".//p:CdtTrfTxInf/p:CdtrAcct/p:Id/p:Othr/p:Id") or _get_text(
        ".//p:CdtTrfTxInf/p:CdtrAcct/p:Id/p:IBAN"
    )
    recipient_bic = _get_text(".//p:CdtTrfTxInf/p:CdtrAgt/p:FinInstnId/p:BICFI")

    recipient = Party(
        full_name=recipient_name,
        account_number=recipient_acct,
        bic=recipient_bic,
        country=CountryCode(recipient_country_str),
    )

    # Interbank Settlement Amount & Currency
    settle_elem = root.find(".//p:CdtTrfTxInf/p:IntrBkSttlmAmt", namespaces=namespaces)
    if settle_elem is None or settle_elem.text is None:
        raise ValueError("Missing IntrBkSttlmAmt in pacs.008")

    target_ccy_str = settle_elem.get("Ccy", "GHS")
    recipient_minor = decimal_str_to_minor_units(settle_elem.text)

    # Purpose
    purp_cd = _get_text(".//p:CdtTrfTxInf/p:Purp/p:Cd")
    if purp_cd and purp_cd in ISO_TO_PURPOSE:
        purpose = ISO_TO_PURPOSE[purp_cd]
    else:
        purpose = PaymentPurpose.FAMILY_SUPPORT

    declaration = ComplianceDeclaration(
        purpose=purpose,
        source_of_funds=SourceOfFunds.EMPLOYMENT_SALARY,
    )

    country_to_currency = {
        "ZA": CurrencyCode.ZAR,
        "GH": CurrencyCode.GHS,
        "KE": CurrencyCode.KES,
        "NG": CurrencyCode.NGN,
        "US": CurrencyCode.USD,
    }
    source_ccy = country_to_currency.get(str(sender.country), CurrencyCode.ZAR)
    target_ccy = (
        CurrencyCode(target_ccy_str)
        if target_ccy_str in CurrencyCode._value2member_map_
        else CurrencyCode.GHS
    )

    corridor = Corridor(
        source=source_ccy,
        target=target_ccy,
        papss_eligible=True,
    )
    from datetime import timedelta

    fx = FxQuote(
        corridor=corridor,
        rate=Decimal("1.0"),
        guaranteed=True,
        captured_at=created_at,
        expires_at=created_at + timedelta(minutes=15),
        source=RateSource.LIVE_INTERBANK,
    )
    quote = TransferQuote(
        send=Money(minor_units=recipient_minor, currency=source_ccy),
        fee=Money(minor_units=0, currency=source_ccy),
        recipient_receives=Money(minor_units=recipient_minor, currency=target_ccy),
        fx=fx,
    )

    return Transfer(
        id=TransferId(tx_id_str),
        reference=ref,
        sender=sender,
        recipient=recipient,
        quote=quote,
        declaration=declaration,
        state=TransferState.VALIDATED,
        created_at=created_at,
        rail=rail,
    )
