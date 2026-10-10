"""Quotes API endpoint -- docs/design/gateway.md §5."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from ubunturemit_domain import CurrencyCode, Money
from ubunturemit_gateway.dependencies import (
    GatewayDependencies,
    UnsupportedCorridorError,
    get_dependencies,
    not_configured,
)
from ubunturemit_gateway.models import QuoteResponse
from ubunturemit_rails import RailRouter

router = APIRouter(prefix="/api/fx", tags=["Quotes"])


@router.get("/quote", response_model=QuoteResponse)
def get_quote(
    deps: Annotated[GatewayDependencies, Depends(get_dependencies)],
    source: str = Query(..., description="Source currency code (e.g. ZAR)"),
    target: str = Query(..., description="Target currency code (e.g. GHS)"),
    amount: int = Query(..., gt=0, description="Send amount in minor units"),
) -> QuoteResponse:
    try:
        src_code = CurrencyCode(source.upper())
        tgt_code = CurrencyCode(target.upper())
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Unsupported currency: {err}") from err

    if deps.quote_source is None:
        raise not_configured("quote_source")

    send_money = Money(minor_units=amount, currency=src_code)
    try:
        quote = deps.quote_source.quote(src_code, tgt_code, send_money)
    except UnsupportedCorridorError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err

    rail_quotes = RailRouter().get_quotes(quote.fx.corridor, send_money)
    if not rail_quotes:
        raise HTTPException(status_code=503, detail="No rail quotes available for this corridor.")

    return QuoteResponse(
        source_currency=src_code.value,
        target_currency=tgt_code.value,
        send_amount_minor_units=quote.send.minor_units,
        recipient_receives_minor_units=quote.recipient_receives.minor_units,
        exchange_rate=quote.fx.rate,
        fee_minor_units=quote.fee.minor_units,
        estimated_seconds=min(q.estimated_seconds for q in rail_quotes),
        available_rails=[q.rail.value for q in rail_quotes],
    )
