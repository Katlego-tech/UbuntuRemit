"""What the gateway needs from outside itself -- docs/design/gateway.md §3, §5.

Every rate, verdict and sanctions decision the gateway returns comes from one of these
sources. None of them has a default: an endpoint whose source is not configured answers
503 and names what is missing, rather than serving a stand-in (Non-negotiable I).
"""

from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException, Request
from ubunturemit_asco import LLMClient, SanctionsScreener
from ubunturemit_domain import CurrencyCode, Money, TransferQuote


class UnsupportedCorridorError(LookupError):
    """The quote source has no corridor for this currency pair."""


class QuoteSource(Protocol):
    """Prices a transfer: the FX rate and the fee, from a real rate provider."""

    def quote(self, source: CurrencyCode, target: CurrencyCode, send: Money) -> TransferQuote:
        """Return a quote for `send`, or raise UnsupportedCorridorError."""
        ...


@dataclass(frozen=True, slots=True)
class GatewayDependencies:
    """The external sources, injected once at app creation."""

    quote_source: QuoteSource | None = None
    sentinel_client: LLMClient | None = None
    strategist_client: LLMClient | None = None
    sanctions_screener: SanctionsScreener | None = None

    def missing(self) -> list[str]:
        """Names of the sources not configured, in a stable order."""
        names = {
            "quote_source": self.quote_source,
            "sentinel_client": self.sentinel_client,
            "strategist_client": self.strategist_client,
            "sanctions_screener": self.sanctions_screener,
        }
        return [name for name, value in names.items() if value is None]


def get_dependencies(request: Request) -> GatewayDependencies:
    return request.app.state.dependencies


def not_configured(*names: str) -> HTTPException:
    """The 503 an endpoint returns when a source it needs is absent."""
    return HTTPException(
        status_code=503,
        detail=f"Not configured: {', '.join(names)}. "
        "The gateway refuses rather than serving a stand-in value.",
    )
