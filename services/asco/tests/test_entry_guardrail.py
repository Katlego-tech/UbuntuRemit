"""Tests for ASCO Entry Guardrail (T040, T041).

Rules per docs/design/asco-orchestrator.md §3, §4:
- Deterministic, no LLM invoked.
- Hard gates:
  1. Schema validation (pain.001 3-tier validation).
  2. Sanctions / PEP screening (sanctions hit is an immediate rejection; PEP triggers review).
  3. Corridor and KYC limit checks (single transaction limit + 30d cumulative SDA limits).
- Any hard gate failure rejects or escalates with cited rules.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ubunturemit_asco.guardrails.entry import (
    EntryGuardrail,
    GuardrailOutcome,
    RecipientProfile,
    SanctionsScreener,
    SenderProfile,
    StaticSanctionsScreener,
)
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
from ubunturemit_messaging.pain001 import build_pain001


@pytest.fixture
def canonical_transfer() -> Transfer:
    """Valid canonical Transfer aggregate."""
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
        send=Money(minor_units=100000, currency=CurrencyCode.ZAR),  # 1,000.00 ZAR
        fee=Money(minor_units=1500, currency=CurrencyCode.ZAR),
        recipient_receives=Money(minor_units=83725, currency=CurrencyCode.GHS),
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
        state=TransferState.INITIATED,
        created_at=datetime(2026, 8, 31, 10, 5, 0, tzinfo=UTC),
        rail=SettlementRail.PAPSS,
    )


@pytest.fixture
def sender_profile_l3() -> SenderProfile:
    return SenderProfile(
        kyc_tier="L3",
        country_of_residence="ZA",
        is_pep=False,
        prior_transfers_30d_count=4,
        prior_transfers_30d_minor_units=4200000,
    )


@pytest.fixture
def recipient_profile() -> RecipientProfile:
    return RecipientProfile(
        country_of_residence="GH",
        account_age_days=412,
    )


@pytest.fixture
def sanctions_screener() -> SanctionsScreener:
    return StaticSanctionsScreener(
        sanctioned_names={"VLADIMIR SANCTIONED", "CORRUPT ACTOR", "BLOCKED ENTITY"},
        sanctioned_bics={"BLCKZAJJXXX"},
    )


def test_entry_guardrail_pass_on_clean_transfer(
    canonical_transfer: Transfer,
    sender_profile_l3: SenderProfile,
    recipient_profile: RecipientProfile,
    sanctions_screener: SanctionsScreener,
) -> None:
    """Clean transfer with L3 profile passes all entry guardrail checks."""
    guardrail = EntryGuardrail(sanctions_screener=sanctions_screener)
    xml_str = build_pain001(canonical_transfer)

    result = guardrail.evaluate(
        xml_input=xml_str,
        sender_profile=sender_profile_l3,
        recipient_profile=recipient_profile,
    )

    assert result.outcome == GuardrailOutcome.PASS
    assert result.transfer is not None
    assert result.transfer.reference == canonical_transfer.reference
    assert len(result.cited_rules) == 0


def test_entry_guardrail_rejects_on_schema_violation(
    sender_profile_l3: SenderProfile,
    recipient_profile: RecipientProfile,
    sanctions_screener: SanctionsScreener,
) -> None:
    """Invalid schema is rejected at gate 1 with cited rule."""
    guardrail = EntryGuardrail(sanctions_screener=sanctions_screener)
    result = guardrail.evaluate(
        xml_input="<InvalidXmlDocument/>",
        sender_profile=sender_profile_l3,
        recipient_profile=recipient_profile,
    )

    assert result.outcome == GuardrailOutcome.REJECTED
    assert result.stage == "SCHEMA"
    assert "ISO_20022_PAIN001_SCHEMA" in result.cited_rules
    assert result.rejection_reason is not None


def test_entry_guardrail_rejects_sanctioned_sender(
    canonical_transfer: Transfer,
    recipient_profile: RecipientProfile,
    sanctions_screener: SanctionsScreener,
) -> None:
    """Sanctioned sender is blocked immediately without LLM invocation."""
    sanctioned_sender = Party(
        full_name="Vladimir Sanctioned",
        account_number="1002938475",
        bic="SBICZAJJXXX",
        country=CountryCode("ZA"),
    )
    transfer = Transfer(
        id=canonical_transfer.id,
        reference=canonical_transfer.reference,
        sender=sanctioned_sender,
        recipient=canonical_transfer.recipient,
        quote=canonical_transfer.quote,
        declaration=canonical_transfer.declaration,
        state=canonical_transfer.state,
        created_at=canonical_transfer.created_at,
    )
    xml_str = build_pain001(transfer)

    sender_profile = SenderProfile(
        kyc_tier="L3",
        country_of_residence="ZA",
        is_pep=False,
    )
    guardrail = EntryGuardrail(sanctions_screener=sanctions_screener)
    result = guardrail.evaluate(
        xml_input=xml_str,
        sender_profile=sender_profile,
        recipient_profile=recipient_profile,
    )

    assert result.outcome == GuardrailOutcome.REJECTED
    assert result.stage == "SANCTIONS"
    assert "FIC_ACT_S28A" in result.cited_rules
    assert "UN_SANCTIONS_LIST" in result.cited_rules
    assert "Vladimir Sanctioned" in str(result.rejection_reason)


def test_entry_guardrail_rejects_sanctioned_recipient(
    canonical_transfer: Transfer,
    sender_profile_l3: SenderProfile,
    recipient_profile: RecipientProfile,
    sanctions_screener: SanctionsScreener,
) -> None:
    """Sanctioned recipient is blocked immediately."""
    sanctioned_recipient = Party(
        full_name="Corrupt Actor",
        account_number="2003948576",
        bic="GHBKGHACXXX",
        country=CountryCode("GH"),
    )
    transfer = Transfer(
        id=canonical_transfer.id,
        reference=canonical_transfer.reference,
        sender=canonical_transfer.sender,
        recipient=sanctioned_recipient,
        quote=canonical_transfer.quote,
        declaration=canonical_transfer.declaration,
        state=canonical_transfer.state,
        created_at=canonical_transfer.created_at,
    )
    xml_str = build_pain001(transfer)

    guardrail = EntryGuardrail(sanctions_screener=sanctions_screener)
    result = guardrail.evaluate(
        xml_input=xml_str,
        sender_profile=sender_profile_l3,
        recipient_profile=recipient_profile,
    )

    assert result.outcome == GuardrailOutcome.REJECTED
    assert result.stage == "SANCTIONS"
    assert "FIC_ACT_S28A" in result.cited_rules


def test_entry_guardrail_escalates_pep_above_threshold(
    canonical_transfer: Transfer,
    recipient_profile: RecipientProfile,
    sanctions_screener: SanctionsScreener,
) -> None:
    """PEP sender above enhanced due diligence threshold triggers ESCALATE for human review."""
    # Transfer 60,000 ZAR (> 50,000 ZAR PEP threshold)
    large_quote = TransferQuote(
        send=Money(minor_units=6000000, currency=CurrencyCode.ZAR),
        fee=Money(minor_units=1500, currency=CurrencyCode.ZAR),
        recipient_receives=Money(minor_units=5000000, currency=CurrencyCode.GHS),
        fx=canonical_transfer.quote.fx,
    )
    transfer = Transfer(
        id=canonical_transfer.id,
        reference=canonical_transfer.reference,
        sender=canonical_transfer.sender,
        recipient=canonical_transfer.recipient,
        quote=large_quote,
        declaration=canonical_transfer.declaration,
        state=canonical_transfer.state,
        created_at=canonical_transfer.created_at,
    )
    xml_str = build_pain001(transfer)

    pep_profile = SenderProfile(
        kyc_tier="L3",
        country_of_residence="ZA",
        is_pep=True,
    )
    guardrail = EntryGuardrail(sanctions_screener=sanctions_screener)
    result = guardrail.evaluate(
        xml_input=xml_str,
        sender_profile=pep_profile,
        recipient_profile=recipient_profile,
    )

    assert result.outcome == GuardrailOutcome.ESCALATE
    assert result.stage == "PEP_SCREEN"
    assert "FIC_ACT_S21H_PEP" in result.cited_rules


def test_entry_guardrail_rejects_amount_exceeding_kyc_tier(
    canonical_transfer: Transfer,
    recipient_profile: RecipientProfile,
    sanctions_screener: SanctionsScreener,
) -> None:
    """Transfer exceeding tier limits (e.g. L1 basic limit 5,000 ZAR) is rejected."""
    # 10,000 ZAR transfer with L1 (limit 5,000 ZAR)
    quote = TransferQuote(
        send=Money(minor_units=1000000, currency=CurrencyCode.ZAR),  # 10,000 ZAR
        fee=Money(minor_units=1500, currency=CurrencyCode.ZAR),
        recipient_receives=Money(minor_units=837250, currency=CurrencyCode.GHS),
        fx=canonical_transfer.quote.fx,
    )
    transfer = Transfer(
        id=canonical_transfer.id,
        reference=canonical_transfer.reference,
        sender=canonical_transfer.sender,
        recipient=canonical_transfer.recipient,
        quote=quote,
        declaration=canonical_transfer.declaration,
        state=canonical_transfer.state,
        created_at=canonical_transfer.created_at,
    )
    xml_str = build_pain001(transfer)

    tier_l1_profile = SenderProfile(
        kyc_tier="L1",
        country_of_residence="ZA",
        is_pep=False,
    )
    guardrail = EntryGuardrail(sanctions_screener=sanctions_screener)
    result = guardrail.evaluate(
        xml_input=xml_str,
        sender_profile=tier_l1_profile,
        recipient_profile=recipient_profile,
    )

    assert result.outcome == GuardrailOutcome.REJECTED
    assert result.stage == "LIMITS"
    assert "FICA_TIER_LIMIT" in result.cited_rules
    assert "SARB_EXCON_LIMIT_EXCEEDED" in result.cited_rules


def test_entry_guardrail_rejects_sda_cap_exceeded(
    canonical_transfer: Transfer,
    recipient_profile: RecipientProfile,
    sanctions_screener: SanctionsScreener,
) -> None:
    """Transfer that would exceed the 1,000,000 ZAR SDA annual limit is rejected."""
    quote = TransferQuote(
        send=Money(minor_units=20000000, currency=CurrencyCode.ZAR),  # 200,000 ZAR
        fee=Money(minor_units=1500, currency=CurrencyCode.ZAR),
        recipient_receives=Money(minor_units=16000000, currency=CurrencyCode.GHS),
        fx=canonical_transfer.quote.fx,
    )
    transfer = Transfer(
        id=canonical_transfer.id,
        reference=canonical_transfer.reference,
        sender=canonical_transfer.sender,
        recipient=canonical_transfer.recipient,
        quote=quote,
        declaration=canonical_transfer.declaration,
        state=canonical_transfer.state,
        created_at=canonical_transfer.created_at,
    )
    xml_str = build_pain001(transfer)

    profile_near_cap = SenderProfile(
        kyc_tier="L3",
        country_of_residence="ZA",
        is_pep=False,
        prior_transfers_30d_count=10,
        # 900,000 ZAR already spent (900k + 200k = 1.1M > 1M SDA cap)
        prior_transfers_30d_minor_units=90000000,
    )
    guardrail = EntryGuardrail(sanctions_screener=sanctions_screener)
    result = guardrail.evaluate(
        xml_input=xml_str,
        sender_profile=profile_near_cap,
        recipient_profile=recipient_profile,
    )

    assert result.outcome == GuardrailOutcome.REJECTED
    assert result.stage == "LIMITS"
    assert "SARB_EXCON_SDA_CAP_EXCEEDED" in result.cited_rules
