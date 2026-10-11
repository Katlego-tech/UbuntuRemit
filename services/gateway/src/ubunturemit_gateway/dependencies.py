"""What the gateway needs from outside itself -- docs/design/gateway.md §3, §5.

Every rate, verdict and sanctions decision the gateway returns comes from one of these
sources. None of them has a default: an endpoint whose source is not configured answers
503 and names what is missing, rather than serving a stand-in (Non-negotiable I).
"""

from dataclasses import dataclass, field
from typing import Protocol

from fastapi import HTTPException, Request
from ubunturemit_asco import (
    AuditLogger,
    LLMClient,
    MasterOrchestrator,
    SanctionsScreener,
)
from ubunturemit_domain import CurrencyCode, Money, TransferQuote
from ubunturemit_rails import RailRouter

from ubunturemit_gateway.models import TransferResponse


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
    rail_router: RailRouter | None = None
    # Where every agent turn and gate decision is written -- in production a
    # ubunturemit_audit.KafkaAuditLogger. An in-process logger would make every
    # settlement unauditable once the process exits.
    audit_logger: AuditLogger | None = None

    def missing(self) -> list[str]:
        """Names of the sources not configured, in a stable order."""
        names = {
            "quote_source": self.quote_source,
            "sentinel_client": self.sentinel_client,
            "strategist_client": self.strategist_client,
            "sanctions_screener": self.sanctions_screener,
            "rail_router": self.rail_router,
            "audit_logger": self.audit_logger,
        }
        return [name for name, value in names.items() if value is None]


@dataclass(slots=True)
class GatewayRuntime:
    """Per-app state, created by create_app() -- never shared between app instances.

    `transfers` holds the response each transfer was answered with, so a GET returns
    the same outcome and citations the POST did. Process-local until T050a.
    """

    orchestrator: MasterOrchestrator = field(default_factory=MasterOrchestrator)
    transfers: dict[str, TransferResponse] = field(default_factory=dict)

    def remember(self, response: TransferResponse) -> TransferResponse:
        self.transfers[response.transfer_id] = response
        return response


def get_dependencies(request: Request) -> GatewayDependencies:
    return request.app.state.dependencies


def get_runtime(request: Request) -> GatewayRuntime:
    return request.app.state.runtime


def not_configured(*names: str) -> HTTPException:
    """The 503 an endpoint returns when a source it needs is absent."""
    return HTTPException(
        status_code=503,
        detail=f"Not configured: {', '.join(names)}. "
        "The gateway refuses rather than serving a stand-in value.",
    )
