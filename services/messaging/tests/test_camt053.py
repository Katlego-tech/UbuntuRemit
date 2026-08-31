"""Tests for camt.053.001.08 parser and transfer reconciliation (T037).

Implements reconciliation rules per docs/design/iso20022-messaging.md §5:
- Exact reference match required.
- 1 minor unit mismatch leaves transfer unreconciled and raises UnreconciledError.
- BOOK status transitions transfer to DELIVERED; PDNG leaves transfer in SETTLING.
"""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
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
from ubunturemit_messaging.camt053 import (
    StatementEntry,
    UnreconciledError,
    build_camt053,
    parse_camt053,
    reconcile_transfer,
)

CAMT053_XSD_PATH = Path(__file__).resolve().parent.parent / "schemas" / "camt.053.001.08.xsd"


@pytest.fixture
def settling_transfer() -> Transfer:
    """Transfer in SETTLING state awaiting reconciliation."""
    sender = Party(
        full_name="Amara Okafor",
        account_number="1002938475",
        bic="SBICZAJJXXX",
        country=CountryCode("ZA"),
    )
    recipient = Party(
        full_name="Kofi Mensah",
        account_number="2003948576",
        bic="GHBKGHACXXX",
        country=CountryCode("GH"),
    )
    corridor = Corridor(
        source=CurrencyCode.ZAR,
        target=CurrencyCode.GHS,
        papss_eligible=True,
    )
    fx = FxQuote(
        corridor=corridor,
        rate=Decimal("0.8500"),
        guaranteed=True,
        captured_at=datetime(2026, 8, 31, 10, 0, 0, tzinfo=UTC),
        expires_at=datetime(2026, 8, 31, 10, 15, 0, tzinfo=UTC),
        source=RateSource.LIVE_INTERBANK,
    )
    quote = TransferQuote(
        send=Money(minor_units=100000, currency=CurrencyCode.ZAR),
        fee=Money(minor_units=1500, currency=CurrencyCode.ZAR),
        recipient_receives=Money(minor_units=83725, currency=CurrencyCode.GHS),  # 837.25 GHS
        fx=fx,
    )
    declaration = ComplianceDeclaration(
        purpose=PaymentPurpose.FAMILY_SUPPORT,
        source_of_funds=SourceOfFunds.EMPLOYMENT_SALARY,
    )
    return Transfer(
        id=TransferId("TR-99420-001"),
        reference="UB-99420-X",
        sender=sender,
        recipient=recipient,
        quote=quote,
        declaration=declaration,
        state=TransferState.SETTLING,
        created_at=datetime(2026, 8, 31, 10, 5, 0, tzinfo=UTC),
        rail=SettlementRail.PAPSS,
    )


def test_build_camt053_validates_against_xsd() -> None:
    """Emitted camt.053 XML must validate cleanly against admitted schema."""
    entries = [
        StatementEntry(
            entry_reference="UB-99420-X",
            amount_minor=83725,
            currency=CurrencyCode.GHS,
            credit_debit="CRDT",
            status="BOOK",
            booking_date="2026-08-31",
            end_to_end_id="UB-99420-X",
        )
    ]
    xml_str = build_camt053(statement_id="STMT-001", entries=entries)

    schema_doc = etree.parse(str(CAMT053_XSD_PATH))
    xmlschema = etree.XMLSchema(schema_doc)

    doc = etree.fromstring(xml_str.encode("utf-8"))
    assert xmlschema.validate(doc), f"camt.053 XML failed XSD validation: {xmlschema.error_log}"


def test_reconcile_transfer_success_booked(settling_transfer: Transfer) -> None:
    """Matching booked entry transitions transfer SETTLING -> DELIVERED."""
    entries = [
        StatementEntry(
            entry_reference="UB-99420-X",
            amount_minor=83725,
            currency=CurrencyCode.GHS,
            credit_debit="CRDT",
            status="BOOK",
            booking_date="2026-08-31",
            end_to_end_id="UB-99420-X",
        )
    ]
    xml_str = build_camt053(statement_id="STMT-001", entries=entries)
    parsed_entries = parse_camt053(xml_str)

    updated_transfer = reconcile_transfer(settling_transfer, parsed_entries)
    assert updated_transfer.state == TransferState.DELIVERED


def test_reconcile_transfer_pending_stays_settling(settling_transfer: Transfer) -> None:
    """Pending (PDNG) status leaves transfer in SETTLING state."""
    entries = [
        StatementEntry(
            entry_reference="UB-99420-X",
            amount_minor=83725,
            currency=CurrencyCode.GHS,
            credit_debit="CRDT",
            status="PDNG",
            booking_date="2026-08-31",
            end_to_end_id="UB-99420-X",
        )
    ]
    updated_transfer = reconcile_transfer(settling_transfer, entries)
    assert updated_transfer.state == TransferState.SETTLING


def test_reconcile_transfer_amount_mismatch_raises(settling_transfer: Transfer) -> None:
    """A 1-minor-unit mismatch leaves transfer unreconciled and raises UnreconciledError."""
    entries = [
        StatementEntry(
            entry_reference="UB-99420-X",
            amount_minor=83724,  # 1 cent off
            currency=CurrencyCode.GHS,
            credit_debit="CRDT",
            status="BOOK",
            booking_date="2026-08-31",
            end_to_end_id="UB-99420-X",
        )
    ]
    with pytest.raises(UnreconciledError, match="Amount mismatch"):
        reconcile_transfer(settling_transfer, entries)

    # State was NOT modified to DELIVERED
    assert settling_transfer.state == TransferState.SETTLING


def test_reconcile_transfer_currency_mismatch_raises(settling_transfer: Transfer) -> None:
    """Currency mismatch raises UnreconciledError."""
    entries = [
        StatementEntry(
            entry_reference="UB-99420-X",
            amount_minor=83725,
            currency=CurrencyCode.ZAR,  # wrong currency
            credit_debit="CRDT",
            status="BOOK",
            booking_date="2026-08-31",
            end_to_end_id="UB-99420-X",
        )
    ]
    with pytest.raises(UnreconciledError, match="Currency mismatch"):
        reconcile_transfer(settling_transfer, entries)


def test_reconcile_transfer_missing_entry_raises(settling_transfer: Transfer) -> None:
    """No matching entry raises UnreconciledError."""
    entries = [
        StatementEntry(
            entry_reference="OTHER-REF",
            amount_minor=83725,
            currency=CurrencyCode.GHS,
            credit_debit="CRDT",
            status="BOOK",
            booking_date="2026-08-31",
            end_to_end_id="OTHER-REF",
        )
    ]
    with pytest.raises(UnreconciledError, match="No statement entry found"):
        reconcile_transfer(settling_transfer, entries)


def test_parse_camt053_rejects_malformed_xml() -> None:
    """Reject non-XML string."""
    with pytest.raises(ValueError, match="XML syntax error"):
        parse_camt053("<not-valid>")
