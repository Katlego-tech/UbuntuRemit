"""Corridors, rates and pricing -- docs/design/domain-model.md §3."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from .money import CurrencyCode, Money

__all__ = ["Corridor", "FxQuote", "RateSource", "TransferQuote"]


class RateSource(StrEnum):
    """Where a rate came from -- domain-model.md §5.

    Recorded on every quote because an auditor asking "why this rate" is
    answered by provenance, not by the number.
    """

    LIVE_INTERBANK = "LIVE_INTERBANK"
    PAPSS_QUOTED = "PAPSS_QUOTED"
    FALLBACK_CACHED = "FALLBACK_CACHED"


def _require_aware(value: datetime, field: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime, got {type(value).__name__}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{field} must be timezone-aware. A naive settlement timestamp is "
            "ambiguous the moment it crosses a corridor."
        )


@dataclass(frozen=True, slots=True)
class Corridor:
    """A source/target currency pair -- domain-model.md §3."""

    source: CurrencyCode
    target: CurrencyCode
    papss_eligible: bool

    def __post_init__(self) -> None:
        for field in ("source", "target"):
            value = getattr(self, field)
            if not isinstance(value, CurrencyCode):
                raise TypeError(f"{field} must be a CurrencyCode, got {type(value).__name__}")
        if not isinstance(self.papss_eligible, bool):
            raise TypeError("papss_eligible must be a bool")


@dataclass(frozen=True, slots=True)
class FxQuote:
    """A rate for a corridor, with its provenance and validity window.

    Nothing here defaults the hold window: §9 records that the guaranteed-rate
    duration is unknown, and a default would be a fabricated commercial term.
    The model asserts ordering only -- domain-model.md §3.
    """

    corridor: Corridor
    rate: Decimal
    guaranteed: bool
    captured_at: datetime
    expires_at: datetime
    source: RateSource

    def __post_init__(self) -> None:
        if not isinstance(self.corridor, Corridor):
            raise TypeError(f"corridor must be a Corridor, got {type(self.corridor).__name__}")
        if not isinstance(self.rate, Decimal):
            raise TypeError(
                f"rate must be a Decimal, got {type(self.rate).__name__}. "
                "A float rate cannot represent its own value exactly."
            )
        if self.rate <= 0:
            raise ValueError(f"rate must be positive, got {self.rate}")
        if not isinstance(self.guaranteed, bool):
            raise TypeError("guaranteed must be a bool")
        if not isinstance(self.source, RateSource):
            raise TypeError(f"source must be a RateSource, got {type(self.source).__name__}")

        _require_aware(self.captured_at, "captured_at")
        _require_aware(self.expires_at, "expires_at")
        if self.expires_at <= self.captured_at:
            raise ValueError(
                f"expires_at ({self.expires_at.isoformat()}) must be after "
                f"captured_at ({self.captured_at.isoformat()})"
            )


@dataclass(frozen=True, slots=True)
class TransferQuote:
    """What the sender pays and what the recipient gets -- domain-model.md §3.

    The currency checks below are the §3 relationships made executable: a quote
    whose amounts sit in currencies its own corridor doesn't name is
    incoherent, and would surface as a reconciliation break rather than an
    error if it were allowed to construct.
    """

    send: Money
    fee: Money
    recipient_receives: Money
    fx: FxQuote

    def __post_init__(self) -> None:
        if not isinstance(self.fx, FxQuote):
            raise TypeError(f"fx must be an FxQuote, got {type(self.fx).__name__}")
        for field in ("send", "fee", "recipient_receives"):
            value = getattr(self, field)
            if not isinstance(value, Money):
                raise TypeError(f"{field} must be Money, got {type(value).__name__}")

        corridor = self.fx.corridor
        for field in ("send", "fee"):
            currency = getattr(self, field).currency
            if currency is not corridor.source:
                raise ValueError(
                    f"{field} is in {currency}, but the corridor's source currency "
                    f"is {corridor.source}"
                )
        if self.recipient_receives.currency is not corridor.target:
            raise ValueError(
                f"recipient_receives is in {self.recipient_receives.currency}, but the "
                f"corridor's target currency is {corridor.target}"
            )
