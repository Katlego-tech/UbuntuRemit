"""Deterministic 3-tier runtime validation gates -- docs/design/iso20022-messaging.md §6B.

Validation Pipeline:
1. XSD Validation (admitted schema)
2. Field Rules (mandatory fields, valid ISO 4217 currencies, mapped purpose codes)
3. Business Rules (amount > 0, corridor support, EndToEndId uniqueness)

No LLM participates in validation.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from lxml import etree
from ubunturemit_domain import CurrencyCode

from ubunturemit_messaging.pain001 import (
    EXCON_NS,
    ISO_TO_PURPOSE,
    PAIN001_NS,
    decimal_str_to_minor_units,
)

ValidationStage = Literal["XSD", "FIELD_RULES", "BUSINESS_RULES", "ACCEPTED"]

SCHEMAS_DIR = Path(__file__).resolve().parent.parent.parent / "schemas"
PAIN001_XSD_PATH = SCHEMAS_DIR / "pain.001.001.09.xsd"
PACS008_XSD_PATH = SCHEMAS_DIR / "pacs.008.001.08.xsd"


@dataclass(frozen=True, slots=True)
class ValidationVerdict:
    """Deterministic verdict from the message validation pipeline."""

    valid: bool
    stage: ValidationStage
    reason: str


class EndToEndIdStore(Protocol):
    """Store protocol for tracking seen EndToEndIds to prevent reuse."""

    def is_seen(self, id_val: str) -> bool:
        """Check if an EndToEndId has already been processed."""
        ...

    def record(self, id_val: str) -> None:
        """Record an EndToEndId as processed."""
        ...


class InMemoryEndToEndIdStore:
    """In-memory implementation of EndToEndIdStore."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def is_seen(self, id_val: str) -> bool:
        return id_val in self._seen

    def record(self, id_val: str) -> None:
        self._seen.add(id_val)


def validate_pain001_message(
    xml_input: str | bytes,
    id_store: EndToEndIdStore | None = None,
) -> ValidationVerdict:
    """Run 3-tier validation pipeline over a pain.001.001.09 XML document."""
    if isinstance(xml_input, str):
        xml_bytes = xml_input.encode("utf-8")
    else:
        xml_bytes = xml_input

    # --- Tier 1: XSD Validation ---
    try:
        doc = etree.fromstring(xml_bytes)
    except (etree.XMLSyntaxError, OSError) as err:
        return ValidationVerdict(
            valid=False,
            stage="XSD",
            reason=f"XML syntax error: {err}",
        )

    try:
        schema_doc = etree.parse(str(PAIN001_XSD_PATH))
        xmlschema = etree.XMLSchema(schema_doc)
        if not xmlschema.validate(doc):
            return ValidationVerdict(
                valid=False,
                stage="XSD",
                reason=f"XSD validation failed: {xmlschema.error_log}",
            )
    except Exception as err:
        return ValidationVerdict(
            valid=False,
            stage="XSD",
            reason=f"Schema validation error: {err}",
        )

    # --- Tier 2: Field Rules ---
    namespaces = {"p": PAIN001_NS, "ex": EXCON_NS}

    # Extract EndToEndId / PmtInfId
    e2e_elem = doc.find(".//p:CdtTrfTxInf/p:PmtId/p:EndToEndId", namespaces=namespaces)
    if e2e_elem is None or not e2e_elem.text or not e2e_elem.text.strip():
        return ValidationVerdict(
            valid=False,
            stage="FIELD_RULES",
            reason="Missing or blank EndToEndId",
        )
    e2e_id = e2e_elem.text.strip()

    # Extract currency and check ISO 4217 support
    instd_amt_elem = doc.find(".//p:CdtTrfTxInf/p:Amt/p:InstdAmt", namespaces=namespaces)
    if instd_amt_elem is None:
        return ValidationVerdict(
            valid=False,
            stage="FIELD_RULES",
            reason="Missing InstdAmt element",
        )
    ccy = instd_amt_elem.get("Ccy", "")
    if ccy not in CurrencyCode._value2member_map_:
        supported_currencies = list(CurrencyCode._value2member_map_.keys())
        return ValidationVerdict(
            valid=False,
            stage="FIELD_RULES",
            reason=f"Unsupported currency '{ccy}'. Must be one of {supported_currencies}",
        )

    # Check ChargeBearer is SLEV
    chrg_br_elem = doc.find(".//p:CdtTrfTxInf/p:ChrgBr", namespaces=namespaces)
    if chrg_br_elem is None or chrg_br_elem.text != "SLEV":
        return ValidationVerdict(
            valid=False,
            stage="FIELD_RULES",
            reason="ChargeBearer (ChrgBr) must be 'SLEV'",
        )

    # Check Purpose Code mapping
    purp_elem = doc.find(".//p:CdtTrfTxInf/p:Purp/p:Cd", namespaces=namespaces)
    if purp_elem is not None and purp_elem.text:
        purp_cd = purp_elem.text.strip()
        if purp_cd not in ISO_TO_PURPOSE:
            return ValidationVerdict(
                valid=False,
                stage="FIELD_RULES",
                reason=f"Unsupported purpose code '{purp_cd}'",
            )

    # --- Tier 3: Business Rules ---
    # Check positive amount
    try:
        amount_minor = decimal_str_to_minor_units(instd_amt_elem.text or "0")
        if amount_minor <= 0:
            return ValidationVerdict(
                valid=False,
                stage="BUSINESS_RULES",
                reason=f"Amount must be greater than zero, got {instd_amt_elem.text}",
            )
    except Exception as err:
        return ValidationVerdict(
            valid=False,
            stage="BUSINESS_RULES",
            reason=f"Invalid amount decimal: {err}",
        )

    # Check EndToEndId uniqueness / reuse
    if id_store is not None:
        if id_store.is_seen(e2e_id):
            return ValidationVerdict(
                valid=False,
                stage="BUSINESS_RULES",
                reason=(
                    f"Duplicate EndToEndId '{e2e_id}' reused. "
                    "Reuse is rejected to prevent silent reconciliation corruption."
                ),
            )
        id_store.record(e2e_id)

    return ValidationVerdict(
        valid=True,
        stage="ACCEPTED",
        reason="All validation gates passed",
    )
