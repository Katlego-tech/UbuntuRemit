"""Quotes API endpoint -- docs/design/frontend-web.md §4."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query
from ubunturemit_domain import (
    Corridor,
    CurrencyCode,
    FxQuote,
    Money,
    RateSource,
    TransferQuote,
)
from ubunturemit_gateway.models import QuoteResponse
from ubunturemit_rails import RailRouter

router = APIRouter(prefix="/api/fx", tags=["Quotes"])

CORRIDOR_RATES: dict[tuple[CurrencyCode, CurrencyCode], tuple[Decimal, bool]] = {
    (CurrencyCode.ZAR, CurrencyCode.GHS): (Decimal("0.8500"), True),
    (CurrencyCode.ZAR, CurrencyCode.NGN): (Decimal("82.5000"), True),
    (CurrencyCode.ZAR, CurrencyCode.KES): (Decimal("7.2000"), True),
}


@router.get("/quote", response_model=QuoteResponse)
def get_quote(
    source: str = Query(..., description="Source currency code (e.g. ZAR)"),
    target: str = Query(..., description="Target currency code (e.g. GHS)"),
    amount: int = Query(..., gt=0, description="Send amount in minor units"),
) -> QuoteResponse:
    try:
        src_code = CurrencyCode(source.upper())
        tgt_code = CurrencyCode(target.upper())
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Unsupported currency: {err}") from err

    key = (src_code, tgt_code)
    if key not in CORRIDOR_RATES:
        raise HTTPException(
            status_code=404,
            detail=f"No active liquidity bridge for corridor {src_code}->{tgt_code}",
        )

    rate, papss_elig = CORRIDOR_RATES[key]
    corridor = Corridor(source=src_code, target=tgt_code, papss_eligible=papss_elig)
    send_money = Money(minor_units=amount, currency=src_code)

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

    rail_router = RailRouter()
    rail_quotes = rail_router.get_quotes(corridor, send_money)
    available_rails = [q.rail.value for q in rail_quotes]
    fastest_sec = min((q.estimated_seconds for q in rail_quotes), default=Decimal("3.2"))

    return QuoteResponse(
        source_currency=src_code.value,
        target_currency=tgt_code.value,
        send_amount_minor_units=quote.send.minor_units,
        recipient_receives_minor_units=quote.recipient_receives.minor_units,
        exchange_rate=rate,
        fee_minor_units=quote.fee.minor_units,
        estimated_seconds=fastest_sec,
        available_rails=available_rails,
    )
