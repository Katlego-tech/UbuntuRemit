"""Transfers API endpoints -- docs/design/gateway.md §4, §5."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from ubunturemit_asco import (
    ComplianceAssessmentInput,
    ComplianceSentinel,
    EntryGuardrail,
    ExitValidator,
    GuardrailOutcome,
    LiquidityStrategist,
    NegotiationCoordinator,
    RecipientProfile,
    SenderProfile,
)
from ubunturemit_domain import (
    ComplianceDeclaration,
    CountryCode,
    CurrencyCode,
    Money,
    Party,
    PaymentPurpose,
    SourceOfFunds,
    Transfer,
    TransferId,
    TransferState,
)
from ubunturemit_gateway.dependencies import (
    GatewayDependencies,
    GatewayRuntime,
    UnsupportedCorridorError,
    get_dependencies,
    get_runtime,
    not_configured,
)
from ubunturemit_gateway.models import TransferInitiationRequest, TransferResponse
from ubunturemit_messaging import build_pacs008, build_pain001
from ubunturemit_rails import SettlementExhaustionError

router = APIRouter(prefix="/api/transfers", tags=["Transfers"])


@router.post("", response_model=TransferResponse)
def initiate_transfer(
    req: TransferInitiationRequest,
    deps: Annotated[GatewayDependencies, Depends(get_dependencies)],
    runtime: Annotated[GatewayRuntime, Depends(get_runtime)],
) -> TransferResponse:
    # Every source is checked before any work: a transfer is either priced, screened and
    # assessed by real sources, or refused -- never part-way on a stand-in.
    quote_source, screener = deps.quote_source, deps.sanctions_screener
    sentinel_client, strategist_client = deps.sentinel_client, deps.strategist_client
    rail_router = deps.rail_router
    if (
        quote_source is None
        or screener is None
        or sentinel_client is None
        or strategist_client is None
        or rail_router is None
    ):
        raise not_configured(*deps.missing())

    try:
        src_code = CurrencyCode(req.source_currency.upper())
        tgt_code = CurrencyCode(req.target_currency.upper())
        purpose = PaymentPurpose(req.purpose.upper())
        source_of_funds = SourceOfFunds(req.source_of_funds.upper())
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid transfer parameter: {err}") from err

    send_money = Money(minor_units=req.send_amount_minor_units, currency=src_code)
    try:
        quote = quote_source.quote(src_code, tgt_code, send_money)
    except UnsupportedCorridorError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    corridor = quote.fx.corridor

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
    entry_guardrail = EntryGuardrail(sanctions_screener=screener)
    sender_prof = SenderProfile(
        kyc_tier=req.sender_kyc_tier,
        country_of_residence=req.sender_country.upper(),
        is_pep=req.sender_is_pep,
        prior_transfers_30d_count=req.sender_prior_transfers_30d_count,
        prior_transfers_30d_minor_units=req.sender_prior_transfers_30d_minor_units,
    )
    recipient_prof = RecipientProfile(
        country_of_residence=req.recipient_country.upper(),
        account_age_days=req.recipient_account_age_days,
    )

    pain001_xml = build_pain001(transfer)
    entry_result = entry_guardrail.evaluate(pain001_xml, sender_prof, recipient_prof)
    if entry_result.outcome != GuardrailOutcome.PASS:
        if entry_result.outcome == GuardrailOutcome.REJECTED:
            transfer = runtime.orchestrator.transition(transfer, TransferState.REJECTED)
        return runtime.remember(
            TransferResponse(
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
        )

    # 2. Multi-agent negotiation loop
    rail_quotes = rail_router.get_quotes(corridor, send_money)

    coordinator = NegotiationCoordinator(
        master_orchestrator=runtime.orchestrator,
        compliance_sentinel=ComplianceSentinel(llm_client=sentinel_client),
        liquidity_strategist=LiquidityStrategist(llm_client=strategist_client),
        exit_validator=ExitValidator(),
        audit_logger=runtime.audit_logger,
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
        recipient_account_age_days=req.recipient_account_age_days,
        prior_transfers_30d_count=req.sender_prior_transfers_30d_count,
        prior_transfers_30d_minor_units=req.sender_prior_transfers_30d_minor_units,
    )

    neg_result = coordinator.negotiate_and_settle(
        transfer=transfer,
        assessment_input=assessment_input,
        rail_quotes=rail_quotes,
    )

    if neg_result.outcome != "SETTLING" or neg_result.proposal is None:
        return runtime.remember(
            TransferResponse(
                transfer_id=str(t_id),
                reference=ref,
                status=neg_result.transfer.state.value,
                outcome=neg_result.outcome,
                selected_rail=None,
                fee_minor_units=quote.fee.minor_units,
                settlement_seconds=None,
                cited_rules=neg_result.verdict.cited_rules if neg_result.verdict else [],
                reason=neg_result.reason,
            )
        )

    # 3. Submit settlement to rail router with retry
    pacs_xml = neg_result.pacs008_xml or build_pacs008(neg_result.transfer)
    try:
        settled_transfer, sub_result, _ = rail_router.execute_settlement_with_retry(
            transfer=neg_result.transfer,
            pacs008_xml=pacs_xml,
            preferred_rail=neg_result.proposal.rail,
            orchestrator=runtime.orchestrator,
        )
    except SettlementExhaustionError as err:
        # Every rail failed and the retry budget is spent: a real outcome, stored and
        # returned like any other -- not a 500 that loses the transfer.
        return runtime.remember(
            TransferResponse(
                transfer_id=str(t_id),
                reference=ref,
                status=TransferState.FAILED.value,
                outcome=TransferState.FAILED.value,
                selected_rail=None,
                fee_minor_units=quote.fee.minor_units,
                settlement_seconds=None,
                cited_rules=neg_result.verdict.cited_rules if neg_result.verdict else [],
                reason=str(err),
            )
        )

    return runtime.remember(
        TransferResponse(
            transfer_id=str(t_id),
            reference=ref,
            status=settled_transfer.state.value,
            outcome=sub_result.status.value,
            selected_rail=settled_transfer.rail.value if settled_transfer.rail else None,
            fee_minor_units=sub_result.fee.minor_units,
            settlement_seconds=settled_transfer.settlement_seconds,
            cited_rules=neg_result.verdict.cited_rules if neg_result.verdict else [],
            reason=f"Rail reported {sub_result.status.value}",
        )
    )


@router.get("/{transfer_id}", response_model=TransferResponse)
def get_transfer(
    transfer_id: str,
    runtime: Annotated[GatewayRuntime, Depends(get_runtime)],
) -> TransferResponse:
    # The stored response, not a re-derivation: the GET returns the outcome and the
    # citations the POST answered with, never an empty list in their place.
    if transfer_id not in runtime.transfers:
        raise HTTPException(status_code=404, detail="Transfer not found")
    return runtime.transfers[transfer_id]
