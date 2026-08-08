"""Money -- domain-model.md §3 and the §8 property test.

The invariant under test: "no arithmetic path can produce a non-integer
`minorUnits`". That is checked here against every operation Money exposes, not
against a hand-picked example.
"""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from ubunturemit_domain import CurrencyCode, Money

# Bounded to a range a settlement could plausibly carry, so the property test
# exercises realistic magnitudes rather than only pathological ones.
minor_units = st.integers(min_value=-(10**15), max_value=10**15)
rates = st.decimals(
    min_value=Decimal("0.000001"),
    max_value=Decimal("1000000"),
    allow_nan=False,
    allow_infinity=False,
    places=6,
)


class TestConstruction:
    def test_accepts_integral_minor_units(self):
        m = Money(minor_units=150_00, currency=CurrencyCode.ZAR)
        assert m.minor_units == 15000
        assert m.currency is CurrencyCode.ZAR

    def test_rejects_float(self):
        # The single most important rejection in the model. A float that
        # happens to be integral is still a float.
        with pytest.raises(TypeError, match="minor_units"):
            Money(minor_units=150.0, currency=CurrencyCode.ZAR)  # type: ignore[arg-type]

    def test_rejects_decimal(self):
        with pytest.raises(TypeError, match="minor_units"):
            Money(minor_units=Decimal(150), currency=CurrencyCode.ZAR)  # type: ignore[arg-type]

    def test_rejects_bool(self):
        # bool is a subclass of int, so a naive isinstance check lets True
        # through as the amount 1.
        with pytest.raises(TypeError, match="minor_units"):
            Money(minor_units=True, currency=CurrencyCode.ZAR)  # type: ignore[arg-type]

    def test_rejects_a_currency_that_is_not_a_currency_code(self):
        with pytest.raises(TypeError, match="currency"):
            Money(minor_units=100, currency="ZAR")  # type: ignore[arg-type]

    def test_is_immutable(self):
        m = Money(minor_units=100, currency=CurrencyCode.ZAR)
        with pytest.raises((AttributeError, TypeError)):
            m.minor_units = 200  # type: ignore[misc]


class TestAdd:
    def test_adds_within_one_currency(self):
        a = Money(minor_units=100, currency=CurrencyCode.ZAR)
        b = Money(minor_units=250, currency=CurrencyCode.ZAR)
        assert a.add(b) == Money(minor_units=350, currency=CurrencyCode.ZAR)

    def test_cross_currency_addition_is_a_type_error(self):
        # §3: "Arithmetic across currencies is a type error." Not a conversion,
        # not a warning -- a refusal.
        zar = Money(minor_units=100, currency=CurrencyCode.ZAR)
        kes = Money(minor_units=100, currency=CurrencyCode.KES)
        with pytest.raises(TypeError, match="currenc"):
            zar.add(kes)

    def test_rejects_adding_a_non_money(self):
        zar = Money(minor_units=100, currency=CurrencyCode.ZAR)
        with pytest.raises(TypeError):
            zar.add(100)  # type: ignore[arg-type]


class TestApplyRate:
    def test_rejects_a_float_rate(self):
        m = Money(minor_units=100, currency=CurrencyCode.ZAR)
        with pytest.raises(TypeError, match="rate"):
            m.apply_rate(1.5)  # type: ignore[arg-type]

    def test_rejects_a_non_positive_rate(self):
        m = Money(minor_units=100, currency=CurrencyCode.ZAR)
        for bad in (Decimal(0), Decimal("-1.5")):
            with pytest.raises(ValueError, match="rate"):
                m.apply_rate(bad)

    def test_preserves_currency(self):
        # applyRate scales within one currency. Crossing a Corridor is not a
        # drawn operation -- see domain-model.md §9.
        m = Money(minor_units=1000, currency=CurrencyCode.NGN)
        assert m.apply_rate(Decimal("2.5")).currency is CurrencyCode.NGN

    def test_rounds_half_to_even(self):
        # §7: ROUND_HALF_EVEN, chosen because it is unbiased over many
        # operations. 2.5 -> 2 and 3.5 -> 4, both to the nearest even.
        half = Decimal("0.5")
        assert Money(5, CurrencyCode.ZAR).apply_rate(half).minor_units == 2
        assert Money(7, CurrencyCode.ZAR).apply_rate(half).minor_units == 4


class TestTheSection8Property:
    @given(units=minor_units, rate=rates)
    def test_apply_rate_always_yields_an_integer(self, units: int, rate: Decimal):
        result = Money(minor_units=units, currency=CurrencyCode.ZAR).apply_rate(rate)
        assert isinstance(result.minor_units, int)
        assert not isinstance(result.minor_units, bool)

    @given(a=minor_units, b=minor_units)
    def test_add_always_yields_an_integer(self, a: int, b: int):
        result = Money(a, CurrencyCode.ZAR).add(Money(b, CurrencyCode.ZAR))
        assert isinstance(result.minor_units, int)

    @given(units=minor_units, first=rates, second=rates)
    def test_chained_rates_stay_integral(self, units: int, first: Decimal, second: Decimal):
        # The path that would smuggle a float in: applying one rate to the
        # result of another.
        result = Money(units, CurrencyCode.ZAR).apply_rate(first).apply_rate(second)
        assert isinstance(result.minor_units, int)
