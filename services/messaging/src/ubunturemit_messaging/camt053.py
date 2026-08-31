"""camt.053.001.08 parser and reconciliation engine -- docs/design/iso20022-messaging.md §5."""

from dataclasses import dataclass
from datetime import UTC, datetime

from lxml import etree
from ubunturemit_domain import (
    CurrencyCode,
    Transfer,
    TransferState,
)

from ubunturemit_messaging.pain001 import (
    decimal_str_to_minor_units,
    minor_units_to_decimal_str,
)

CAMT053_NS = "urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"


class UnreconciledError(Exception):
    """Raised when a transfer cannot be reconciled against statement entries."""


@dataclass(frozen=True, slots=True)
class StatementEntry:
    """A statement entry in a camt.053 BankToCustomerStatement."""

    entry_reference: str
    amount_minor: int
    currency: CurrencyCode
    credit_debit: str  # "CRDT" or "DBIT"
    status: str  # "BOOK", "PDNG", "INFO"
    booking_date: str
    end_to_end_id: str | None = None


def parse_camt053(xml_input: str | bytes) -> list[StatementEntry]:
    """Parse a camt.053.001.08 XML document into a list of StatementEntry instances."""
    if isinstance(xml_input, str):
        xml_bytes = xml_input.encode("utf-8")
    else:
        xml_bytes = xml_input

    try:
        root = etree.fromstring(xml_bytes)
    except (etree.XMLSyntaxError, OSError) as err:
        raise ValueError(f"XML syntax error in camt.053: {err}") from err

    expected_tag = f"{{{CAMT053_NS}}}Document"
    if root.tag != expected_tag:
        actual_ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
        if actual_ns != CAMT053_NS:
            raise ValueError(
                f"Unexpected namespace '{actual_ns}' in camt.053. Expected '{CAMT053_NS}'"
            )
        raise ValueError(f"Expected root tag <Document>, got <{root.tag}>")

    namespaces = {"c": CAMT053_NS}
    entries: list[StatementEntry] = []

    for ntry in root.findall(".//c:Stmt/c:Ntry", namespaces=namespaces):
        ntry_ref = ""
        ntry_ref_elem = ntry.find("c:NtryRef", namespaces=namespaces)
        if ntry_ref_elem is not None and ntry_ref_elem.text:
            ntry_ref = ntry_ref_elem.text.strip()

        amt_elem = ntry.find("c:Amt", namespaces=namespaces)
        if amt_elem is None or not amt_elem.text:
            continue
        ccy_str = amt_elem.get("Ccy", "ZAR")
        amount_minor = decimal_str_to_minor_units(amt_elem.text)

        cdt_dbt = "CRDT"
        cdt_dbt_elem = ntry.find("c:CdtDbtInd", namespaces=namespaces)
        if cdt_dbt_elem is not None and cdt_dbt_elem.text:
            cdt_dbt = cdt_dbt_elem.text.strip()

        status = "BOOK"
        sts_elem = ntry.find("c:Sts/c:Cd", namespaces=namespaces)
        if sts_elem is not None and sts_elem.text:
            status = sts_elem.text.strip()

        booking_date = ""
        bkg_dt_elem = ntry.find("c:BookgDt/c:Dt", namespaces=namespaces)
        if bkg_dt_elem is not None and bkg_dt_elem.text:
            booking_date = bkg_dt_elem.text.strip()

        e2e_id = ""
        e2e_elem = ntry.find(".//c:NtryDtls/c:TxDtls/c:Refs/c:EndToEndId", namespaces=namespaces)
        if e2e_elem is not None and e2e_elem.text:
            e2e_id = e2e_elem.text.strip()

        currency = (
            CurrencyCode(ccy_str)
            if ccy_str in CurrencyCode._value2member_map_
            else CurrencyCode.ZAR
        )

        entries.append(
            StatementEntry(
                entry_reference=ntry_ref,
                amount_minor=amount_minor,
                currency=currency,
                credit_debit=cdt_dbt,
                status=status,
                booking_date=booking_date,
                end_to_end_id=e2e_id or ntry_ref,
            )
        )

    return entries


def reconcile_transfer(transfer: Transfer, entries: list[StatementEntry]) -> Transfer:
    """Reconcile a Transfer against a list of statement entries.

    Rules per docs/design/iso20022-messaging.md §5:
    - Exact match on Transfer.reference against entry.end_to_end_id or entry.entry_reference.
    - Amount mismatch (even 1 minor unit) raises UnreconciledError and does NOT mark DELIVERED.
    - Currency mismatch raises UnreconciledError.
    - Status == 'BOOK' transitions transfer to DELIVERED.
    - Status == 'PDNG' leaves transfer in SETTLING.
    """
    matching_entry: StatementEntry | None = None
    for entry in entries:
        if entry.end_to_end_id == transfer.reference or entry.entry_reference == transfer.reference:
            matching_entry = entry
            break

    if matching_entry is None:
        raise UnreconciledError(
            f"No statement entry found matching transfer reference '{transfer.reference}'"
        )

    expected_amount = transfer.quote.recipient_receives
    if matching_entry.currency != expected_amount.currency:
        raise UnreconciledError(
            f"Currency mismatch for '{transfer.reference}': expected {expected_amount.currency}, "
            f"got {matching_entry.currency}"
        )

    if matching_entry.amount_minor != expected_amount.minor_units:
        raise UnreconciledError(
            f"Amount mismatch for '{transfer.reference}': expected {expected_amount.minor_units} "
            f"minor units, got {matching_entry.amount_minor} minor units"
        )

    if matching_entry.status == "BOOK":
        if transfer.state == TransferState.SETTLING:
            return transfer.transition_to(TransferState.DELIVERED)
        return transfer
    elif matching_entry.status == "PDNG":
        # Pending statement entry leaves transfer in settling state
        return transfer
    else:
        raise UnreconciledError(
            f"Unsupported statement status '{matching_entry.status}' for '{transfer.reference}'"
        )


def build_camt053(
    statement_id: str,
    entries: list[StatementEntry],
    account_number: str = "1002938475",
    account_bic: str = "SBICZAJJXXX",
) -> str:
    """Build a compliant camt.053.001.08 XML document from a list of StatementEntry records."""
    nsmap = {None: CAMT053_NS}
    root = etree.Element(f"{{{CAMT053_NS}}}Document", nsmap=nsmap)
    bk_stmt = etree.SubElement(root, f"{{{CAMT053_NS}}}BkToCstmrStmt")

    # 1. Group Header (GrpHdr)
    grp_hdr = etree.SubElement(bk_stmt, f"{{{CAMT053_NS}}}GrpHdr")
    msg_id = etree.SubElement(grp_hdr, f"{{{CAMT053_NS}}}MsgId")
    msg_id.text = f"MSG-{statement_id}"

    cre_dt_tm = etree.SubElement(grp_hdr, f"{{{CAMT053_NS}}}CreDtTm")
    now_utc = datetime.now(UTC)
    cre_dt_tm.text = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 2. Statement (Stmt)
    stmt = etree.SubElement(bk_stmt, f"{{{CAMT053_NS}}}Stmt")
    stmt_id = etree.SubElement(stmt, f"{{{CAMT053_NS}}}Id")
    stmt_id.text = statement_id

    elc_seq = etree.SubElement(stmt, f"{{{CAMT053_NS}}}ElctrncSeqNb")
    elc_seq.text = "1"

    lgl_seq = etree.SubElement(stmt, f"{{{CAMT053_NS}}}LglSeqNb")
    lgl_seq.text = "1"

    stmt_cre_dt = etree.SubElement(stmt, f"{{{CAMT053_NS}}}CreDtTm")
    stmt_cre_dt.text = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Account (Acct)
    acct = etree.SubElement(stmt, f"{{{CAMT053_NS}}}Acct")
    acct_id = etree.SubElement(acct, f"{{{CAMT053_NS}}}Id")
    acct_othr = etree.SubElement(acct_id, f"{{{CAMT053_NS}}}Othr")
    acct_othr_id = etree.SubElement(acct_othr, f"{{{CAMT053_NS}}}Id")
    acct_othr_id.text = account_number

    svcr = etree.SubElement(acct, f"{{{CAMT053_NS}}}Svcr")
    fin_id = etree.SubElement(svcr, f"{{{CAMT053_NS}}}FinInstnId")
    bic_elem = etree.SubElement(fin_id, f"{{{CAMT053_NS}}}BICFI")
    bic_elem.text = account_bic

    # Balance (Bal)
    bal = etree.SubElement(stmt, f"{{{CAMT053_NS}}}Bal")
    bal_tp = etree.SubElement(bal, f"{{{CAMT053_NS}}}Tp")
    cd_prtry = etree.SubElement(bal_tp, f"{{{CAMT053_NS}}}CdOrPrtry")
    bal_cd = etree.SubElement(cd_prtry, f"{{{CAMT053_NS}}}Cd")
    bal_cd.text = "CLBD"

    bal_amt = etree.SubElement(bal, f"{{{CAMT053_NS}}}Amt")
    bal_amt.set("Ccy", "GHS")
    bal_amt.text = "100000.00"

    bal_ind = etree.SubElement(bal, f"{{{CAMT053_NS}}}CdtDbtInd")
    bal_ind.text = "CRDT"

    bal_dt = etree.SubElement(bal, f"{{{CAMT053_NS}}}Dt")
    bal_date = etree.SubElement(bal_dt, f"{{{CAMT053_NS}}}Dt")
    bal_date.text = now_utc.strftime("%Y-%m-%d")

    # Entries (Ntry)
    for entry in entries:
        ntry = etree.SubElement(stmt, f"{{{CAMT053_NS}}}Ntry")
        if entry.entry_reference:
            ntry_ref = etree.SubElement(ntry, f"{{{CAMT053_NS}}}NtryRef")
            ntry_ref.text = entry.entry_reference

        amt = etree.SubElement(ntry, f"{{{CAMT053_NS}}}Amt")
        amt.set("Ccy", entry.currency.value)
        amt.text = minor_units_to_decimal_str(entry.amount_minor)

        cdt_dbt = etree.SubElement(ntry, f"{{{CAMT053_NS}}}CdtDbtInd")
        cdt_dbt.text = entry.credit_debit

        sts = etree.SubElement(ntry, f"{{{CAMT053_NS}}}Sts")
        sts_cd = etree.SubElement(sts, f"{{{CAMT053_NS}}}Cd")
        sts_cd.text = entry.status

        bkg_dt = etree.SubElement(ntry, f"{{{CAMT053_NS}}}BookgDt")
        bkg_date = etree.SubElement(bkg_dt, f"{{{CAMT053_NS}}}Dt")
        bkg_date.text = entry.booking_date

        # Mandatory Bank Transaction Code (BkTxCd) per ISO schema
        bk_tx_cd = etree.SubElement(ntry, f"{{{CAMT053_NS}}}BkTxCd")
        prtry_cd = etree.SubElement(bk_tx_cd, f"{{{CAMT053_NS}}}Prtry")
        cd_elem = etree.SubElement(prtry_cd, f"{{{CAMT053_NS}}}Cd")
        cd_elem.text = "PMNT"

        if entry.end_to_end_id:
            ntry_dtls = etree.SubElement(ntry, f"{{{CAMT053_NS}}}NtryDtls")
            tx_dtls = etree.SubElement(ntry_dtls, f"{{{CAMT053_NS}}}TxDtls")
            refs = etree.SubElement(tx_dtls, f"{{{CAMT053_NS}}}Refs")
            e2e = etree.SubElement(refs, f"{{{CAMT053_NS}}}EndToEndId")
            e2e.text = entry.end_to_end_id

    return etree.tostring(
        root,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    ).decode("utf-8")
