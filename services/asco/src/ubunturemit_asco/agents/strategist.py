"""Liquidity Strategist agent -- docs/design/asco-orchestrator.md §3, §5.

32B math-optimised model persona finding cheapest/fastest settlement rail.
Selects exclusively from provided RailQuotes.
"""

import json
from decimal import Decimal

from ubunturemit_asco.agents.sentinel import InferenceTimeoutError, LLMClient
from ubunturemit_asco.models import (
    LiquidityProposal,
    LiquidityRequestInput,
)
from ubunturemit_domain import Money, SettlementRail

STRATEGIST_SYSTEM_PROMPT = """You are the Liquidity Strategist for UbuntuRemit.
Evaluate available rail quotes (Ripple, SWIFT, PAPSS) to find the cheapest/fastest rail.

CRITICAL: ONLY choose from provided railQuotes. Never invent a rail or fee.

You MUST return a valid JSON object matching the LiquidityProposal schema:
{
  "rail": "RIPPLE" | "SWIFT" | "PAPSS",
  "totalCost": { "minorUnits": 1800, "currency": "ZAR" },
  "estimatedSeconds": 3.2,
  "rationale": "Brief rationale under 400 characters"
}
"""


class LiquidityStrategist:
    """Liquidity Strategist agent selecting optimal settlement rail."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._client = llm_client

    def propose(
        self,
        request_input: LiquidityRequestInput,
    ) -> tuple[LiquidityProposal, str, str]:
        """Propose an optimal rail and return (LiquidityProposal, thought, action)."""
        valid_rails = {q.rail for q in request_input.rail_quotes}
        forbidden = set(request_input.constraints.forbidden_rails)
        eligible_quotes = [q for q in request_input.rail_quotes if q.rail not in forbidden]

        if not eligible_quotes:
            raise ValueError(
                f"No eligible rails available after applying compliance constraints. "
                f"Offered: {list(valid_rails)}, Forbidden: {list(forbidden)}"
            )

        payload_json = json.dumps(
            {
                "transferId": request_input.transfer_id,
                "corridor": {
                    "source": request_input.corridor_source.value,
                    "target": request_input.corridor_target.value,
                },
                "amount": {
                    "minorUnits": request_input.amount.minor_units,
                    "currency": request_input.amount.currency.value,
                },
                "constraints": {
                    "forbiddenRails": [r.value for r in request_input.constraints.forbidden_rails],
                    "maxSettlementSeconds": (
                        float(request_input.constraints.max_settlement_seconds)
                        if request_input.constraints.max_settlement_seconds is not None
                        else None
                    ),
                },
                "railQuotes": [
                    {
                        "rail": q.rail.value,
                        "feeMinorUnits": q.fee_minor_units,
                        "spreadBps": q.spread_bps,
                        "estimatedSeconds": float(q.estimated_seconds),
                    }
                    for q in eligible_quotes
                ],
            },
            indent=2,
        )

        thought = (
            f"Selecting optimal rail from {len(eligible_quotes)} eligible quotes "
            f"for transfer {request_input.transfer_id}"
        )
        action = f"Prompting 32B Liquidity Strategist with payload: {payload_json}"

        if self._client is None:
            # Deterministic selection: pick lowest total fee, breaking ties by fastest settlement
            best_quote = min(
                eligible_quotes,
                key=lambda q: (q.fee_minor_units, q.estimated_seconds),
            )
            proposal = LiquidityProposal(
                rail=best_quote.rail,
                total_cost=Money(
                    minor_units=best_quote.fee_minor_units,
                    currency=request_input.amount.currency,
                ),
                estimated_seconds=best_quote.estimated_seconds,
                rationale=(
                    f"Selected {best_quote.rail} as optimal rail with fee "
                    f"{best_quote.fee_minor_units} and {best_quote.estimated_seconds}s latency."
                ),
            )
            return proposal, thought, action

        try:
            raw_response = self._client.complete(
                prompt=payload_json,
                system_prompt=STRATEGIST_SYSTEM_PROMPT,
            )
            proposal = self._parse_and_validate(raw_response, request_input)
            return proposal, thought, action
        except InferenceTimeoutError as err:
            raise err
        except Exception:
            # Retry once
            retry_prompt = (
                f"Previous response invalid. Select ONLY from provided rail quotes:\n{payload_json}"  # noqa: S608
            )
            raw_response2 = self._client.complete(
                prompt=retry_prompt,
                system_prompt=STRATEGIST_SYSTEM_PROMPT,
            )
            proposal2 = self._parse_and_validate(raw_response2, request_input)
            return proposal2, thought, action

    def _parse_and_validate(
        self,
        json_str: str,
        request_input: LiquidityRequestInput,
    ) -> LiquidityProposal:
        data = json.loads(json_str)
        rail_str = data.get("rail", "")
        if rail_str not in SettlementRail._value2member_map_:
            raise ValueError(f"Unknown rail '{rail_str}'")
        rail = SettlementRail(rail_str)

        cost_data = data.get("totalCost", {})
        cost_minor = int(cost_data.get("minorUnits", 0))
        total_cost = Money(
            minor_units=cost_minor,
            currency=request_input.amount.currency,
        )

        est_sec = Decimal(str(data.get("estimatedSeconds", "10.0")))
        rationale = data.get("rationale", "")

        return LiquidityProposal(
            rail=rail,
            total_cost=total_cost,
            estimated_seconds=est_sec,
            rationale=rationale,
        )
