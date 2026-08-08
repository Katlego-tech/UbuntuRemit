"""The canonical UbuntuRemit domain entities.

This package is the single implementation of the class diagram in
`docs/design/domain-model.md` §3, shared by `gateway`, `asco` and `messaging`.
It is a library, not a service: it holds no process and imports from no
service. See domain-model.md §6.

Two entities from §3 deliberately live elsewhere, per the §6 placement table:
`ComplianceVerdict` in `services/asco/guardrails/exit.py` (it exists to be
checked by the exit validator) and `LiquidityProposal` in
`services/asco/agents/strategist.py`.
"""

from .money import CurrencyCode, Money
from .party import CountryCode, Party
from .quote import Corridor, FxQuote, RateSource, TransferQuote
from .transfer import (
    ComplianceDeclaration,
    PaymentPurpose,
    SettlementRail,
    SourceOfFunds,
    Transfer,
    TransferId,
    TransferState,
)

__all__ = [
    "ComplianceDeclaration",
    "Corridor",
    "CountryCode",
    "CurrencyCode",
    "FxQuote",
    "Money",
    "Party",
    "PaymentPurpose",
    "RateSource",
    "SettlementRail",
    "SourceOfFunds",
    "Transfer",
    "TransferId",
    "TransferQuote",
    "TransferState",
]
