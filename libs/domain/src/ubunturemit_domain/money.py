"""Money and currency -- docs/design/domain-model.md §3.

The one rule that outranks everything else here: money is integral minor units,
never a float, at any layer including JSON on the wire.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum

__all__ = ["CurrencyCode", "Money"]


class CurrencyCode(StrEnum):
    """ISO 4217 codes this system handles -- domain-model.md §5.

    Closed on purpose. Extending it is a deliberate act: a new currency needs a
    corridor, a rate source and a compliance position, not just a member here.
    """

    ZAR = "ZAR"
    KES = "KES"
    NGN = "NGN"
    GHS = "GHS"
    USD = "USD"


# Rate arithmetic is done at a precision far above anything a settlement needs,
# so that chained operations can never lose a digit to the default 28-digit
# context before the single rounding step at the end.
_ARITHMETIC_PRECISION = 60


@dataclass(frozen=True, slots=True)
class Money:
    """An amount in integral minor units -- domain-model.md §3.

    NEVER a float. Arithmetic across currencies is a type error.
    """

    minor_units: int
    currency: CurrencyCode

    def __post_init__(self) -> None:
        # `type(...) is not int` rather than isinstance: bool is a subclass of
        # int, so isinstance would quietly accept True as the amount 1.
        if type(self.minor_units) is not int:
            raise TypeError(
                f"minor_units must be an int, got {type(self.minor_units).__name__}. "
                "Money is integral minor units -- floats and Decimals are refused here "
                "rather than rounded silently."
            )
        if not isinstance(self.currency, CurrencyCode):
            raise TypeError(f"currency must be a CurrencyCode, got {type(self.currency).__name__}")

    def add(self, other: Money) -> Money:
        """Add two amounts in the same currency.

        Adding across currencies is refused, not converted: a conversion needs
        an `FxQuote`, and silently picking one would be the fabricated rate
        Non-negotiable I forbids.
        """
        if not isinstance(other, Money):
            raise TypeError(f"cannot add {type(other).__name__} to Money")
        if other.currency is not self.currency:
            raise TypeError(
                f"cannot add {other.currency} to {self.currency}: "
                "arithmetic across currencies is a type error, and converting "
                "requires an FxQuote"
            )
        return Money(minor_units=self.minor_units + other.minor_units, currency=self.currency)

    def apply_rate(self, rate: Decimal) -> Money:
        """Scale this amount by `rate`, staying in the same currency.

        This is the drawn `applyRate(decimal) Money`. It does **not** cross a
        corridor -- there is no drawn path from a source currency to a target
        one, and inventing one is the open question in domain-model.md §9.

        Rounds `ROUND_HALF_EVEN` exactly once, at the boundary back to integer
        minor units (§7). Half-even is unbiased over many operations, where
        truncation would silently favour one party on every conversion.
        """
        if not isinstance(rate, Decimal):
            raise TypeError(
                f"rate must be a Decimal, got {type(rate).__name__}. "
                "A float rate cannot represent its own value exactly, which is "
                "disqualifying in settlement."
            )
        if rate <= 0:
            raise ValueError(f"rate must be positive, got {rate}")

        with decimal.localcontext() as ctx:
            ctx.prec = _ARITHMETIC_PRECISION
            scaled = Decimal(self.minor_units) * rate
            rounded = scaled.quantize(Decimal(1), rounding=ROUND_HALF_EVEN)

        return Money(minor_units=int(rounded), currency=self.currency)
