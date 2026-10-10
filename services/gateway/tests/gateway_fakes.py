"""Test-only sources for the gateway, each named as a test double.

Nothing here is reachable from the gateway's own wiring: create_app() with no
dependencies answers 503. These exist so the tests can exercise the configured path.
"""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from ubunturemit_asco import (
    InMemoryAuditLogger,
    LimitTable,
    RailQuote,
    SanctionsListSource,
    StaticSanctionsScreener,
)
from ubunturemit_domain import (
    Corridor,
    CurrencyCode,
    FxQuote,
    Money,
    RateSource,
    SettlementRail,
    Transfer,
    TransferQuote,
)
from ubunturemit_gateway.dependencies import GatewayDependencies, UnsupportedCorridorError
from ubunturemit_rails import RailRouter, RailStatus, RailSubmissionResult

TEST_RATE = Decimal("0.8500")
TEST_FEE_MINOR_UNITS = 1500
TEST_LIMITS = LimitTable(
    source_name="gateway test fixture limits",
    published=date(2026, 10, 1),
    currency=CurrencyCode.ZAR,
    single_transfer_limits={"L1": 500000, "L2": 5000000, "L3": 100000000},
    cumulative_30d_limit=100000000,
    pep_review_threshold=5000000,
)
TEST_LIST = SanctionsListSource(name="gateway test fixture list", published=date(2026, 10, 1))


class FixedRateTestQuoteSource:
    """Quotes ZAR->GHS at a fixed test rate; every other corridor is unsupported."""

    def quote(self, source: CurrencyCode, target: CurrencyCode, send: Money) -> TransferQuote:
        if (source, target) != (CurrencyCode.ZAR, CurrencyCode.GHS):
            raise UnsupportedCorridorError(f"No test corridor for {source}->{target}")
        now = datetime.now(UTC)
        return TransferQuote(
            send=send,
            fee=Money(minor_units=TEST_FEE_MINOR_UNITS, currency=source),
            recipient_receives=Money(
                minor_units=int(Decimal(send.minor_units) * TEST_RATE), currency=target
            ),
            fx=FxQuote(
                corridor=Corridor(source=source, target=target, papss_eligible=True),
                rate=TEST_RATE,
                guaranteed=True,
                captured_at=now,
                expires_at=now + timedelta(minutes=15),
                source=RateSource.LIVE_INTERBANK,
            ),
        )


class ScriptedTestLLMClient:
    """Returns one fixed JSON document on every call."""

    def __init__(self, document: dict[str, object]) -> None:
        self._text = json.dumps(document)

    def complete(self, prompt: str, system_prompt: str) -> str:
        return self._text


class SimulatedTestRail:
    """A PAPSS stand-in: quotes the terms it is given and reports a SIMULATED settlement."""

    rail = SettlementRail.PAPSS

    def __init__(self, fail: bool = False) -> None:
        self._fail = fail

    def get_quote(self, corridor: Corridor, amount: Money) -> RailQuote:
        return RailQuote(self.rail, 1200, 8, Decimal("11"))

    def submit_settlement(self, pacs008_xml: str, transfer: Transfer) -> RailSubmissionResult:
        return RailSubmissionResult(
            rail=self.rail,
            status=RailStatus.FAILED if self._fail else RailStatus.DELIVERED,
            settlement_reference="SIMULATED-TEST",
            fee=Money(minor_units=1200, currency=transfer.quote.send.currency),
            settlement_seconds=Decimal("11"),
        )


def configured_dependencies() -> GatewayDependencies:
    return GatewayDependencies(
        quote_source=FixedRateTestQuoteSource(),
        sentinel_client=ScriptedTestLLMClient(
            {
                "outcome": "PASS",
                "riskScore": 0.1,
                "citedRules": ["TEST_RULE_FROM_MOCKED_MODEL"],
                "rationale": "Scripted test verdict.",
                "constraints": {"forbiddenRails": []},
            }
        ),
        strategist_client=ScriptedTestLLMClient(
            {
                "rail": "PAPSS",
                "totalCost": {"minorUnits": 1200, "currency": "ZAR"},
                "estimatedSeconds": 11.0,
                "rationale": "Scripted test proposal.",
            }
        ),
        sanctions_screener=StaticSanctionsScreener(
            source=TEST_LIST, sanctioned_names=["Listed Test Person"]
        ),
        rail_router=RailRouter(adapters={SettlementRail.PAPSS: SimulatedTestRail()}),
        # Test-only: the deployed gateway is given a KafkaAuditLogger (T050a).
        audit_logger=InMemoryAuditLogger(),
        limit_table=TEST_LIMITS,
    )
