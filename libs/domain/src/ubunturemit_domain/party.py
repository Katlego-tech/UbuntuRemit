"""Parties to a transfer -- docs/design/domain-model.md §3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NewType

__all__ = ["CountryCode", "Party"]

# ISO 3166-1 alpha-2. Deliberately NOT an enum: §5 closes CurrencyCode and the
# compliance taxonomies, but names no closed set of countries, and inventing
# one here would decide which corridors exist as a side effect.
CountryCode = NewType("CountryCode", str)


def _require_text(value: str, field: str) -> None:
    """Refuse blank identifiers.

    An empty account number or BIC is the hard-coded stand-in problem in
    miniature: it looks like a value, carries no information, and fails at the
    rail rather than at construction.
    """
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a str, got {type(value).__name__}")
    if not value.strip():
        raise ValueError(f"{field} must not be blank")


@dataclass(frozen=True, slots=True)
class Party:
    """A sender or recipient -- domain-model.md §3.

    `bic` is required, following the diagram literally. Whether SARB reporting
    needs it on retail (non-institutional) transfers is an open question in §9;
    until that is answered, required is the honest reading.
    """

    full_name: str
    account_number: str
    bic: str
    country: CountryCode

    def __post_init__(self) -> None:
        _require_text(self.full_name, "full_name")
        _require_text(self.account_number, "account_number")
        _require_text(self.bic, "bic")
        _require_text(self.country, "country")
