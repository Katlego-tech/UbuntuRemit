"""Valid entities for tests that are about something else.

Every value here is obviously synthetic. Nothing in this module is a rate, a
fee or a corridor anyone should read as real -- these exist so a state-machine
test doesn't have to hand-build a nine-field object to make its point.
"""

from datetime import UTC, datetime
from decimal import Decimal

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

CAPTURED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
EXPIRES_AT = datetime(2026, 1, 1, 12, 5, tzinfo=UTC)


def a_corridor(**kwargs) -> Corridor:
    return Corridor(
        **{
            "source": CurrencyCode.ZAR,
            "target": CurrencyCode.KES,
            "papss_eligible": True,
            **kwargs,
        }
    )


def an_fx_quote(**kwargs) -> FxQuote:
    return FxQuote(
        **{
            "corridor": a_corridor(),
            "rate": Decimal("7.5"),
            "guaranteed": False,
            "captured_at": CAPTURED_AT,
            "expires_at": EXPIRES_AT,
            "source": RateSource.LIVE_INTERBANK,
            **kwargs,
        }
    )


def a_party(**kwargs) -> Party:
    return Party(
        **{
            "full_name": "Test Sender",
            "account_number": "0000000000",
            "bic": "TESTZAJJXXX",
            "country": CountryCode("ZA"),
            **kwargs,
        }
    )


def a_transfer_quote(**kwargs) -> TransferQuote:
    fx = kwargs.pop("fx", an_fx_quote())
    return TransferQuote(
        **{
            "send": Money(100_00, fx.corridor.source),
            "fee": Money(2_50, fx.corridor.source),
            "recipient_receives": Money(750_00, fx.corridor.target),
            "fx": fx,
            **kwargs,
        }
    )


def a_declaration(**kwargs) -> ComplianceDeclaration:
    return ComplianceDeclaration(
        **{
            "purpose": PaymentPurpose.FAMILY_SUPPORT,
            "source_of_funds": SourceOfFunds.EMPLOYMENT_SALARY,
            **kwargs,
        }
    )


def a_transfer(**kwargs) -> Transfer:
    return Transfer(
        **{
            "id": TransferId("11111111-1111-4111-8111-111111111111"),
            "reference": "TEST-REFERENCE",
            "sender": a_party(),
            "recipient": a_party(full_name="Test Recipient", country=CountryCode("KE")),
            "quote": a_transfer_quote(),
            "declaration": a_declaration(),
            "state": TransferState.INITIATED,
            "created_at": CAPTURED_AT,
            **kwargs,
        }
    )
