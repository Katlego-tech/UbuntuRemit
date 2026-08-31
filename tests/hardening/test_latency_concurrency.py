"""Hardening: Latency against RTGS SLA window under concurrent load (T062).

Validates that multi-agent negotiation meets the SADC-RTGS settlement SLA window (<30 seconds)
under concurrent transaction load.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal

from ubunturemit_asco import (
    ComplianceAssessmentInput,
    ComplianceSentinel,
    ExitValidator,
    InMemoryAuditLogger,
    LiquidityStrategist,
    MasterOrchestrator,
    NegotiationCoordinator,
)
from ubunturemit_asco.models import RailQuote
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
    SettlementRail,
    SourceOfFunds,
    Transfer,
    TransferId,
    TransferQuote,
    TransferState,
)


class FastMockLLMClient:
    def complete(self, prompt: str, system_prompt: str = "") -> str:
        # Simulate realistic model inference latency (10-20ms)
        time.sleep(0.01)
        if "compliance" in system_prompt.lower() or "sentinel" in system_prompt.lower():
            return json.dumps(
                {
                    "outcome": "PASS",
                    "riskScore": "0.1",
                    "citedRules": ["FIC_ACT_S28A"],
                    "constraints": {"forbiddenRails": [], "maxSettlementSeconds": 30},
                    "rationale": "Passes FIC Act review.",
                }
            )
        return json.dumps(
            {
                "rail": "RIPPLE",
                "totalCost": {
                    "minorUnits": 0,
                },
                "estimatedSeconds": 3.2,
                "rationale": "Instant XRPL bridge.",
            }
        )


def make_concurrent_transfer(i: int) -> Transfer:
    corridor = Corridor(
        source=CurrencyCode.ZAR,
        target=CurrencyCode.GHS,
        papss_eligible=True,
    )
    quote = TransferQuote(
        send=Money(minor_units=100000 + i, currency=CurrencyCode.ZAR),
        fee=Money(minor_units=1500, currency=CurrencyCode.ZAR),
        recipient_receives=Money(minor_units=83725 + i, currency=CurrencyCode.GHS),
        fx=FxQuote(
            corridor=corridor,
            rate=Decimal("0.8500"),
            guaranteed=True,
            captured_at=datetime(2026, 8, 31, 10, 0, 0, tzinfo=UTC),
            expires_at=datetime(2026, 8, 31, 10, 15, 0, tzinfo=UTC),
            source=RateSource.LIVE_INTERBANK,
        ),
    )
    return Transfer(
        id=TransferId(f"TR-CONCUR-{i:03d}"),
        reference=f"UB-CONCUR-{i:03d}",
        sender=Party(f"Sender {i}", f"ZA-{i}", "SBICZAJJXXX", CountryCode("ZA")),
        recipient=Party(f"Recipient {i}", f"GH-{i}", "GHBKGHACXXX", CountryCode("GH")),
        quote=quote,
        declaration=ComplianceDeclaration(
            purpose=PaymentPurpose.FAMILY_SUPPORT,
            source_of_funds=SourceOfFunds.EMPLOYMENT_SALARY,
        ),
        state=TransferState.INITIATED,
        created_at=datetime(2026, 8, 31, 10, 5, 0, tzinfo=UTC),
    )


def run_single_transfer(i: int) -> float:
    start = time.perf_counter()
    llm = FastMockLLMClient()
    coordinator = NegotiationCoordinator(
        compliance_sentinel=ComplianceSentinel(llm_client=llm),
        liquidity_strategist=LiquidityStrategist(llm_client=llm),
        master_orchestrator=MasterOrchestrator(),
        exit_validator=ExitValidator(),
        audit_logger=InMemoryAuditLogger(),
    )
    quotes = [
        RailQuote(SettlementRail.RIPPLE, 0, 12, Decimal("3.2")),
        RailQuote(SettlementRail.PAPSS, 1200, 8, Decimal("11.0")),
    ]
    transfer = make_concurrent_transfer(i)
    assessment_input = ComplianceAssessmentInput(
        transfer_id=transfer.id,
        corridor_source=transfer.quote.send.currency,
        corridor_target=transfer.quote.recipient_receives.currency,
        amount=transfer.quote.send,
        purpose=transfer.declaration.purpose,
        source_of_funds=transfer.declaration.source_of_funds,
        sender_kyc_tier="TIER_2",
        sender_country="ZA",
        sender_is_pep=False,
        recipient_country="GH",
        recipient_account_age_days=100,
        prior_transfers_30d_count=0,
        prior_transfers_30d_minor_units=0,
    )
    res = coordinator.negotiate_and_settle(
        transfer=transfer,
        assessment_input=assessment_input,
        rail_quotes=quotes,
    )
    assert res.outcome == "SETTLING"
    return time.perf_counter() - start


def test_concurrent_negotiation_latency() -> None:
    num_transfers = 30
    latencies: list[float] = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(run_single_transfer, i) for i in range(num_transfers)]
        for f in futures:
            latencies.append(f.result())

    p50 = sorted(latencies)[int(len(latencies) * 0.50)]
    p99 = sorted(latencies)[int(len(latencies) * 0.99)]

    # RTGS SLA limit is 30.0s; our negotiation p99 should be < 2.0s
    assert p50 < 1.0, f"p50 latency {p50:.3f}s exceeds 1.0s target"
    assert p99 < 2.0, f"p99 latency {p99:.3f}s exceeds 2.0s target (RTGS SLA: 30s)"
