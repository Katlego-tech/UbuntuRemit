"""Transfers API endpoints -- docs/design/frontend-web.md §4, §6."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from ubunturemit_asco import (
    ComplianceAssessmentInput,
    ComplianceSentinel,
    EntryGuardrail,
    ExitValidator,
    GuardrailOutcome,
    InMemoryAuditLogger,
    LiquidityStrategist,
    MasterOrchestrator,
    NegotiationCoordinator,
    RecipientProfile,
    SenderProfile,
)
from ubunturemit_asco.guardrails.entry import StaticSanctionsScreener
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
from ubunturemit_gateway.models import TransferInitiationRequest, TransferResponse
from ubunturemit_gateway.routes.quotes import CORRIDOR_RATES
from ubunturemit_messaging import build_pacs008, build_pain001
from ubunturemit_rails import RailRouter

router = APIRouter(prefix="/api/transfers", tags=["Transfers"])

# In-memory transfer and orchestrator registry for the gateway
TRANSFERS_DB: dict[str, Transfer] = {}
ORCHESTRATOR = MasterOrchestrator()
AUDIT_LOGGER = InMemoryAuditLogger()


@router.post("", response_model=TransferResponse)
def initiate_transfer(req: TransferInitiationRequest) -> TransferResponse:
    try:
        src_code = CurrencyCode(req.source_currency.upper())
        tgt_code = CurrencyCode(req.target_currency.upper())
        purpose = PaymentPurpose(req.purpose.upper())
        source_of_funds = SourceOfFunds(req.source_of_funds.upper())
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid transfer parameter: {err}") from err

    key = (src_code, tgt_code)
    if key not in CORRIDOR_RATES:
        raise HTTPException(status_code=404, detail="Corridor unsupported")

    rate, papss_elig = CORRIDOR_RATES[key]
    corridor = Corridor(source=src_code, target=tgt_code, papss_eligible=papss_elig)
    send_money = Money(minor_units=req.send_amount_minor_units, currency=src_code)

    now = datetime.now(UTC)
    fx = FxQuote(
        corridor=corridor,
        rate=rate,
        guaranteed=True,
        captured_at=now,
        expires_at=now + timedelta(minutes=15),
        source=RateSource.LIVE_INTERBANK,
    )
    recip_units = int(round(Decimal(send_money.minor_units) * rate))
    quote = TransferQuote(
        send=send_money,
        fee=Money(minor_units=1500, currency=src_code),
        recipient_receives=Money(minor_units=recip_units, currency=tgt_code),
        fx=fx,
    )

    t_id = TransferId(f"TR-{uuid.uuid4().hex[:8].upper()}")
    ref = f"UB-{uuid.uuid4().hex[:8].upper()}"

    sender = Party(
        full_name=req.sender_name,
        account_number=req.sender_account,
        bic=req.sender_bic,
        country=CountryCode(req.sender_country.upper()),
    )
    recipient = Party(
        full_name=req.recipient_name,
        account_number=req.recipient_account,
        bic=req.recipient_bic,
        country=CountryCode(req.recipient_country.upper()),
    )

    transfer = Transfer(
        id=t_id,
        reference=ref,
        sender=sender,
        recipient=recipient,
        quote=quote,
        declaration=ComplianceDeclaration(
            purpose=purpose,
            source_of_funds=source_of_funds,
        ),
        state=TransferState.INITIATED,
        created_at=datetime.now(UTC),
    )

    # 1. Evaluate Entry Guardrail
    screener = StaticSanctionsScreener(sanctioned_names={"Sanctioned Person"})
    entry_guardrail = EntryGuardrail(sanctions_screener=screener)
    sender_prof = SenderProfile(
        kyc_tier="L3" if "3" in req.sender_kyc_tier else "L2",
        country_of_residence=req.sender_country.upper(),
        is_pep=req.sender_is_pep,
        prior_transfers_30d_count=0,
        prior_transfers_30d_minor_units=0,
    )
    recipient_prof = RecipientProfile(
        country_of_residence=req.recipient_country.upper(),
        account_age_days=180,
    )

    pain001_xml = build_pain001(transfer)
    entry_result = entry_guardrail.evaluate(pain001_xml, sender_prof, recipient_prof)
    if entry_result.outcome != GuardrailOutcome.PASS:
        TRANSFERS_DB[str(t_id)] = transfer
        return TransferResponse(
            transfer_id=str(t_id),
            reference=ref,
            status=transfer.state.value,
            outcome=entry_result.outcome.value,
            selected_rail=None,
            fee_minor_units=quote.fee.minor_units,
            settlement_seconds=None,
            cited_rules=entry_result.cited_rules,
            reason=entry_result.rejection_reason or "Entry guardrail rejected transfer",
        )

    # 2. Multi-agent negotiation loop
    rail_router = RailRouter()
    rail_quotes = rail_router.get_quotes(corridor, send_money)

    coordinator = NegotiationCoordinator(
        master_orchestrator=ORCHESTRATOR,
        compliance_sentinel=ComplianceSentinel(),
        liquidity_strategist=LiquidityStrategist(),
        exit_validator=ExitValidator(),
        audit_logger=AUDIT_LOGGER,
    )

    assessment_input = ComplianceAssessmentInput(
        transfer_id=transfer.id,
        corridor_source=src_code,
        corridor_target=tgt_code,
        amount=send_money,
        purpose=purpose,
        source_of_funds=source_of_funds,
        sender_kyc_tier=req.sender_kyc_tier,
        sender_country=req.sender_country,
        sender_is_pep=req.sender_is_pep,
        recipient_country=req.recipient_country,
        recipient_account_age_days=180,
    )

    neg_result = coordinator.negotiate_and_settle(
        transfer=transfer,
        assessment_input=assessment_input,
        rail_quotes=rail_quotes,
    )

    if neg_result.outcome != "SETTLING" or neg_result.proposal is None:
        TRANSFERS_DB[str(t_id)] = neg_result.transfer
        return TransferResponse(
            transfer_id=str(t_id),
            reference=ref,
            status=neg_result.transfer.state.value,
            outcome=neg_result.outcome,
            selected_rail=None,
            fee_minor_units=quote.fee.minor_units,
            settlement_seconds=None,
            cited_rules=[],
            reason=neg_result.reason,
        )

    # 3. Submit settlement to rail router with retry
    pacs_xml = neg_result.pacs008_xml or build_pacs008(neg_result.transfer)
    settled_transfer, sub_result, _ = rail_router.execute_settlement_with_retry(
        transfer=neg_result.transfer,
        pacs008_xml=pacs_xml,
        preferred_rail=neg_result.proposal.rail,
        orchestrator=ORCHESTRATOR,
    )

    TRANSFERS_DB[str(t_id)] = settled_transfer

    return TransferResponse(
        transfer_id=str(t_id),
        reference=ref,
        status=settled_transfer.state.value,
        outcome=sub_result.status.value,
        selected_rail=settled_transfer.rail.value if settled_transfer.rail else None,
        fee_minor_units=sub_result.fee.minor_units,
        settlement_seconds=settled_transfer.settlement_seconds,
        cited_rules=["FIC_ACT_S28A", "SARB_EXCON_B4"],
        reason="Settlement completed successfully",
    )


@router.get("/{transfer_id}", response_model=TransferResponse)
def get_transfer(transfer_id: str) -> TransferResponse:
    if transfer_id not in TRANSFERS_DB:
        raise HTTPException(status_code=404, detail="Transfer not found")
    t = TRANSFERS_DB[transfer_id]
    return TransferResponse(
        transfer_id=str(t.id),
        reference=t.reference,
        status=t.state.value,
        outcome=t.state.value,
        selected_rail=t.rail.value if t.rail else None,
        fee_minor_units=t.quote.fee.minor_units,
        settlement_seconds=t.settlement_seconds,
        cited_rules=[],
        reason="",
    )
