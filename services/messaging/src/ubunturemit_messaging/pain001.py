"""pain.001.001.09 message builder and parser -- docs/design/iso20022-messaging.md §5."""

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
    SourceOfFunds,
    Transfer,
    TransferId,
    TransferQuote,
    TransferState,
)

PAIN001_NS = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.09"
EXCON_NS = "urn:sarb:excon:v1"

# Data-driven field mappings (iso20022-messaging.md §5)
PURPOSE_TO_ISO: dict[PaymentPurpose, str] = {
    PaymentPurpose.FAMILY_SUPPORT: "FAMI",
    PaymentPurpose.BUSINESS_INVESTMENT: "BEXP",
    PaymentPurpose.GOODS_OR_SERVICES: "GDDS",
    PaymentPurpose.EDUCATION: "EDUC",
    PaymentPurpose.MEDICAL: "HLTI",
}
ISO_TO_PURPOSE: dict[str, PaymentPurpose] = {v: k for k, v in PURPOSE_TO_ISO.items()}


def minor_units_to_decimal_str(minor_units: int) -> str:
    """Format integral minor units to exact 2-decimal string without float arithmetic."""
    dollars, cents = divmod(minor_units, 100)
    return f"{dollars}.{cents:02d}"


def decimal_str_to_minor_units(decimal_str: str) -> int:
    """Parse exact decimal string to integral minor units without float arithmetic."""
    parts = decimal_str.strip().split(".")
    dollars = int(parts[0])
    if len(parts) == 1:
        cents = 0
    else:
        cents_str = parts[1].ljust(2, "0")[:2]
        cents = int(cents_str)
    return dollars * 100 + cents


def build_pain001(transfer: Transfer) -> str:
    """Build a compliant pain.001.001.09 XML document from a Transfer aggregate."""
    nsmap = {None: PAIN001_NS}
    root = etree.Element(f"{{{PAIN001_NS}}}Document", nsmap=nsmap)
    cstmr_init = etree.SubElement(root, f"{{{PAIN001_NS}}}CstmrCdtTrfInitn")

    # 1. Group Header (GrpHdr)
    grp_hdr = etree.SubElement(cstmr_init, f"{{{PAIN001_NS}}}GrpHdr")
    msg_id = etree.SubElement(grp_hdr, f"{{{PAIN001_NS}}}MsgId")
    msg_id.text = f"MSG-{transfer.reference}"

    cre_dt_tm = etree.SubElement(grp_hdr, f"{{{PAIN001_NS}}}CreDtTm")
    cre_dt_tm.text = transfer.created_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    nb_of_txs = etree.SubElement(grp_hdr, f"{{{PAIN001_NS}}}NbOfTxs")
    nb_of_txs.text = "1"

    initg_pty = etree.SubElement(grp_hdr, f"{{{PAIN001_NS}}}InitgPty")
    initg_nm = etree.SubElement(initg_pty, f"{{{PAIN001_NS}}}Nm")
    initg_nm.text = transfer.sender.full_name

    # 2. Payment Information (PmtInf)
    pmt_inf = etree.SubElement(cstmr_init, f"{{{PAIN001_NS}}}PmtInf")
    pmt_inf_id = etree.SubElement(pmt_inf, f"{{{PAIN001_NS}}}PmtInfId")
    pmt_inf_id.text = transfer.reference

    pmt_mtd = etree.SubElement(pmt_inf, f"{{{PAIN001_NS}}}PmtMtd")
    pmt_mtd.text = "TRF"

    pmt_nb_txs = etree.SubElement(pmt_inf, f"{{{PAIN001_NS}}}NbOfTxs")
    pmt_nb_txs.text = "1"

    reqd_exctn_dt = etree.SubElement(pmt_inf, f"{{{PAIN001_NS}}}ReqdExctnDt")
    dt = etree.SubElement(reqd_exctn_dt, f"{{{PAIN001_NS}}}Dt")
    dt.text = transfer.created_at.astimezone(UTC).strftime("%Y-%m-%d")

    # Debtor (Sender)
    dbtr = etree.SubElement(pmt_inf, f"{{{PAIN001_NS}}}Dbtr")
    dbtr_nm = etree.SubElement(dbtr, f"{{{PAIN001_NS}}}Nm")
    dbtr_nm.text = transfer.sender.full_name
    dbtr_adr = etree.SubElement(dbtr, f"{{{PAIN001_NS}}}PstlAdr")
    dbtr_ctry = etree.SubElement(dbtr_adr, f"{{{PAIN001_NS}}}Ctry")
    dbtr_ctry.text = str(transfer.sender.country)

    # Debtor Account
    dbtr_acct = etree.SubElement(pmt_inf, f"{{{PAIN001_NS}}}DbtrAcct")
    dbtr_acct_id = etree.SubElement(dbtr_acct, f"{{{PAIN001_NS}}}Id")
    dbtr_othr = etree.SubElement(dbtr_acct_id, f"{{{PAIN001_NS}}}Othr")
    dbtr_othr_id = etree.SubElement(dbtr_othr, f"{{{PAIN001_NS}}}Id")
    dbtr_othr_id.text = transfer.sender.account_number

    # Debtor Agent
    dbtr_agt = etree.SubElement(pmt_inf, f"{{{PAIN001_NS}}}DbtrAgt")
    dbtr_fin_id = etree.SubElement(dbtr_agt, f"{{{PAIN001_NS}}}FinInstnId")
    dbtr_bic = etree.SubElement(dbtr_fin_id, f"{{{PAIN001_NS}}}BICFI")
    dbtr_bic.text = transfer.sender.bic

    # Charge Bearer (Mandatory SLEV per §5)
    chrg_br = etree.SubElement(pmt_inf, f"{{{PAIN001_NS}}}ChrgBr")
    chrg_br.text = "SLEV"

    # 3. Credit Transfer Transaction Information (CdtTrfTxInf)
    cdt_trf = etree.SubElement(pmt_inf, f"{{{PAIN001_NS}}}CdtTrfTxInf")

    pmt_id = etree.SubElement(cdt_trf, f"{{{PAIN001_NS}}}PmtId")
    e2e_id = etree.SubElement(pmt_id, f"{{{PAIN001_NS}}}EndToEndId")
    e2e_id.text = transfer.reference

    amt = etree.SubElement(cdt_trf, f"{{{PAIN001_NS}}}Amt")
    instd_amt = etree.SubElement(amt, f"{{{PAIN001_NS}}}InstdAmt")
    instd_amt.set("Ccy", transfer.quote.send.currency.value)
    instd_amt.text = minor_units_to_decimal_str(transfer.quote.send.minor_units)

    tx_chrg_br = etree.SubElement(cdt_trf, f"{{{PAIN001_NS}}}ChrgBr")
    tx_chrg_br.text = "SLEV"

    # Creditor Agent
    cdtr_agt = etree.SubElement(cdt_trf, f"{{{PAIN001_NS}}}CdtrAgt")
    cdtr_fin_id = etree.SubElement(cdtr_agt, f"{{{PAIN001_NS}}}FinInstnId")
    cdtr_bic = etree.SubElement(cdtr_fin_id, f"{{{PAIN001_NS}}}BICFI")
    cdtr_bic.text = transfer.recipient.bic

    # Creditor (Recipient)
    cdtr = etree.SubElement(cdt_trf, f"{{{PAIN001_NS}}}Cdtr")
    cdtr_nm = etree.SubElement(cdtr, f"{{{PAIN001_NS}}}Nm")
    cdtr_nm.text = transfer.recipient.full_name
    cdtr_adr = etree.SubElement(cdtr, f"{{{PAIN001_NS}}}PstlAdr")
    cdtr_ctry = etree.SubElement(cdtr_adr, f"{{{PAIN001_NS}}}Ctry")
    cdtr_ctry.text = str(transfer.recipient.country)

    # Creditor Account
    cdtr_acct = etree.SubElement(cdt_trf, f"{{{PAIN001_NS}}}CdtrAcct")
    cdtr_acct_id = etree.SubElement(cdtr_acct, f"{{{PAIN001_NS}}}Id")
    cdtr_othr = etree.SubElement(cdtr_acct_id, f"{{{PAIN001_NS}}}Othr")
    cdtr_othr_id = etree.SubElement(cdtr_othr, f"{{{PAIN001_NS}}}Id")
    cdtr_othr_id.text = transfer.recipient.account_number

    # Purpose
    iso_purp = PURPOSE_TO_ISO.get(transfer.declaration.purpose)
    if iso_purp:
        purp = etree.SubElement(cdt_trf, f"{{{PAIN001_NS}}}Purp")
        purp_cd = etree.SubElement(purp, f"{{{PAIN001_NS}}}Cd")
        purp_cd.text = iso_purp

    # Remittance Information
    rmt_inf = etree.SubElement(cdt_trf, f"{{{PAIN001_NS}}}RmtInf")
    ustrd = etree.SubElement(rmt_inf, f"{{{PAIN001_NS}}}Ustrd")
    ustrd.text = transfer.reference

    # Supplementary Data (SourceOfFunds rides here per §5)
    splmtry = etree.SubElement(cdt_trf, f"{{{PAIN001_NS}}}SplmtryData")
    plc_nm = etree.SubElement(splmtry, f"{{{PAIN001_NS}}}PlcAndNm")
    plc_nm.text = "/Document/CstmrCdtTrfInitn/PmtInf/CdtTrfTxInf"

    envlp = etree.SubElement(splmtry, f"{{{PAIN001_NS}}}Envlp")
    sof_elem = etree.Element(f"{{{EXCON_NS}}}SourceOfFunds", nsmap={None: EXCON_NS})
    sof_elem.text = transfer.declaration.source_of_funds.value
    envlp.append(sof_elem)

    return etree.tostring(
        root,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    ).decode("utf-8")


def parse_pain001(xml_input: str | bytes) -> Transfer:
    """Parse a pain.001.001.09 XML document into a canonical Transfer aggregate."""
    if isinstance(xml_input, str):
        xml_bytes = xml_input.encode("utf-8")
    else:
        xml_bytes = xml_input

    try:
        root = etree.fromstring(xml_bytes)
    except (etree.XMLSyntaxError, OSError) as err:
        raise ValueError(f"XML syntax error in pain.001: {err}") from err

    expected_tag = f"{{{PAIN001_NS}}}Document"
    if root.tag != expected_tag:
        actual_ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
        if actual_ns != PAIN001_NS:
            raise ValueError(
                f"Unexpected namespace '{actual_ns}' in pain.001. Expected '{PAIN001_NS}'"
            )
        raise ValueError(f"Expected root tag <Document>, got <{root.tag}>")

    namespaces = {"p": PAIN001_NS, "ex": EXCON_NS}

    def _get_text(xpath: str, default: str = "") -> str:
        elem = root.find(xpath, namespaces=namespaces)
        if elem is not None and elem.text is not None:
            return elem.text.strip()
        return default

    # Extract Header & Reference
    ref = _get_text(".//p:PmtInf/p:PmtInfId") or _get_text(".//p:CdtTrfTxInf/p:PmtId/p:EndToEndId")
    if not ref:
        raise ValueError("Missing reference in pain.001 (PmtInfId / EndToEndId)")

    cre_dt_raw = _get_text(".//p:GrpHdr/p:CreDtTm")
    if cre_dt_raw:
        # Normalize ISO datetime
        created_at = datetime.fromisoformat(cre_dt_raw.replace("Z", "+00:00"))
    else:
        created_at = datetime.now(UTC)

    # Sender (Debtor)
    sender_name = _get_text(".//p:PmtInf/p:Dbtr/p:Nm")
    sender_country_str = _get_text(".//p:PmtInf/p:Dbtr/p:PstlAdr/p:Ctry", "ZA")
    sender_acct = _get_text(".//p:PmtInf/p:DbtrAcct/p:Id/p:Othr/p:Id") or _get_text(
        ".//p:PmtInf/p:DbtrAcct/p:Id/p:IBAN"
    )
    sender_bic = _get_text(".//p:PmtInf/p:DbtrAgt/p:FinInstnId/p:BICFI")

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

    # Instructed Amount & Currency
    instd_elem = root.find(".//p:CdtTrfTxInf/p:Amt/p:InstdAmt", namespaces=namespaces)
    if instd_elem is None or instd_elem.text is None:
        raise ValueError("Missing InstdAmt in pain.001")

    ccy_str = instd_elem.get("Ccy", "ZAR")
    amount_minor = decimal_str_to_minor_units(instd_elem.text)

    # Purpose
    purp_cd = _get_text(".//p:CdtTrfTxInf/p:Purp/p:Cd")
    if not purp_cd:
        raise ValueError("Missing Purpose code in pain.001")
    if purp_cd not in ISO_TO_PURPOSE:
        raise ValueError(f"Unsupported or unmapped ISO purpose code '{purp_cd}'")
    purpose = ISO_TO_PURPOSE[purp_cd]

    # Source of Funds from SplmtryData
    sof_str = _get_text(".//p:SplmtryData/p:Envlp/ex:SourceOfFunds")
    if sof_str and sof_str in SourceOfFunds._value2member_map_:
        source_of_funds = SourceOfFunds(sof_str)
    else:
        source_of_funds = SourceOfFunds.SAVINGS

    declaration = ComplianceDeclaration(
        purpose=purpose,
        source_of_funds=source_of_funds,
    )

    # Construct minimal quote context
    country_to_currency = {
        "ZA": CurrencyCode.ZAR,
        "GH": CurrencyCode.GHS,
        "KE": CurrencyCode.KES,
        "NG": CurrencyCode.NGN,
        "US": CurrencyCode.USD,
    }
    source_ccy = (
        CurrencyCode(ccy_str) if ccy_str in CurrencyCode._value2member_map_ else CurrencyCode.ZAR
    )
    target_ccy = country_to_currency.get(str(recipient.country), CurrencyCode.GHS)
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
        send=Money(minor_units=amount_minor, currency=source_ccy),
        fee=Money(minor_units=0, currency=source_ccy),
        recipient_receives=Money(minor_units=amount_minor, currency=target_ccy),
        fx=fx,
    )

    return Transfer(
        id=TransferId(f"TR-{ref}"),
        reference=ref,
        sender=sender,
        recipient=recipient,
        quote=quote,
        declaration=declaration,
        state=TransferState.INITIATED,
        created_at=created_at,
    )
