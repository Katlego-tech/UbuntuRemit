"""Construction rules for the entities around Money -- domain-model.md §3.

The theme: every value that could only be satisfied by inventing one is
refused at construction rather than defaulted.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ubunturemit_domain import (
    CurrencyCode,
    Money,
    Party,
    TransferState,
)

from .factories import (
    CAPTURED_AT,
    a_corridor,
    a_party,
    a_transfer,
    a_transfer_quote,
    an_fx_quote,
)


class TestFxQuote:
    def test_builds_from_valid_inputs(self):
        assert an_fx_quote().rate == Decimal("7.5")

    def test_rejects_a_float_rate(self):
        with pytest.raises(TypeError, match="rate"):
            an_fx_quote(rate=7.5)

    def test_rejects_a_non_positive_rate(self):
        with pytest.raises(ValueError, match="rate"):
            an_fx_quote(rate=Decimal(0))

    def test_rejects_naive_timestamps(self):
        # A naive settlement timestamp is a bug waiting for a DST boundary --
        # it is why ruff's DTZ rules are selected for this repo.
        naive = datetime(2026, 1, 1, 12, 0)  # noqa: DTZ001 -- the point of the test
        with pytest.raises(ValueError, match="timezone"):
            an_fx_quote(captured_at=naive)
        with pytest.raises(ValueError, match="timezone"):
            an_fx_quote(expires_at=naive)

    def test_rejects_an_expiry_at_or_before_capture(self):
        with pytest.raises(ValueError, match="expires_at"):
            an_fx_quote(expires_at=CAPTURED_AT)
        with pytest.raises(ValueError, match="expires_at"):
            an_fx_quote(expires_at=CAPTURED_AT.replace(hour=11))

    def test_accepts_any_hold_window(self):
        # §9 records that the guaranteed-rate hold window is unknown. Guessing
        # a default here would be a fabricated commercial term, so the model
        # takes whatever it is given and asserts only ordering.
        long_hold = an_fx_quote(expires_at=datetime(2027, 1, 1, tzinfo=UTC))
        assert long_hold.expires_at > long_hold.captured_at


class TestTransferQuote:
    def test_builds_from_valid_inputs(self):
        assert a_transfer_quote().send.minor_units == 10000

    def test_send_and_fee_must_be_in_the_corridor_source_currency(self):
        fx = an_fx_quote(corridor=a_corridor(source=CurrencyCode.ZAR, target=CurrencyCode.KES))
        with pytest.raises(ValueError, match="source currency"):
            a_transfer_quote(fx=fx, send=Money(100_00, CurrencyCode.USD))
        with pytest.raises(ValueError, match="source currency"):
            a_transfer_quote(fx=fx, fee=Money(2_50, CurrencyCode.USD))

    def test_recipient_receives_must_be_in_the_corridor_target_currency(self):
        fx = an_fx_quote(corridor=a_corridor(source=CurrencyCode.ZAR, target=CurrencyCode.KES))
        with pytest.raises(ValueError, match="target currency"):
            a_transfer_quote(fx=fx, recipient_receives=Money(750_00, CurrencyCode.NGN))


class TestParty:
    def test_builds_from_valid_inputs(self):
        assert a_party().country == "ZA"

    @pytest.mark.parametrize("field", ["full_name", "account_number", "bic", "country"])
    def test_rejects_blank_identifying_fields(self, field: str):
        # An empty BIC is the hard-coded stand-in problem in miniature: it
        # looks like a value, carries no information, and fails at the rail.
        with pytest.raises(ValueError, match=field):
            a_party(**{field: "   "})

    def test_bic_is_required(self):
        # §9 asks whether SARB needs the sender's BIC on retail transfers.
        # Until that is answered the diagram is followed literally: required.
        with pytest.raises(TypeError):
            Party(full_name="X", account_number="1", country="ZA")  # type: ignore[call-arg]


class TestTransfer:
    def test_starts_with_no_rail_and_no_settlement_time(self):
        # §9: a transfer at INITIATED has neither, and a required field there
        # could only be satisfied by inventing a value.
        transfer = a_transfer()
        assert transfer.rail is None
        assert transfer.settlement_seconds is None

    def test_rejects_naive_created_at(self):
        with pytest.raises(ValueError, match="timezone"):
            a_transfer(created_at=datetime(2026, 1, 1))  # noqa: DTZ001 -- the point of the test

    def test_rejects_a_blank_reference(self):
        with pytest.raises(ValueError, match="reference"):
            a_transfer(reference="")

    def test_rejects_float_settlement_seconds(self):
        with pytest.raises(TypeError, match="settlement_seconds"):
            a_transfer(settlement_seconds=3.2)

    def test_sender_and_recipient_are_distinct_fields(self):
        transfer = a_transfer()
        assert transfer.sender.full_name != transfer.recipient.full_name

    def test_is_frozen(self):
        with pytest.raises((AttributeError, TypeError)):
            a_transfer().state = TransferState.DELIVERED  # type: ignore[misc]

    def test_equality_is_by_value(self):
        assert a_transfer() == a_transfer()
        assert a_transfer() != a_transfer(reference="OTHER")


class TestModuleSurface:
    def test_every_public_name_is_exported(self):
        import ubunturemit_domain as domain

        for name in ("Money", "Party", "FxQuote", "Transfer", "TransferId"):
            assert name in domain.__all__, f"{name} missing from __all__"

    def test_the_library_imports_nothing_from_services(self):
        # domain-model.md §6: libs/domain depends on no service. If this ever
        # fails, the dependency arrow has been drawn backwards.
        import ubunturemit_domain as domain

        source_root = domain.__path__[0]
        offenders = []
        for module in ("money", "party", "quote", "transfer"):
            with open(f"{source_root}/{module}.py") as handle:
                if "services" in handle.read():
                    offenders.append(module)
        assert not offenders, f"libs/domain modules reference services: {offenders}"
