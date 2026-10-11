"""The JSON Schemas each agent's replies are constrained to -- docs/design/inference.md §5.

Restated from asco-orchestrator.md §5. A test holds these equal to the blocks in
inference.md, so the code and the design cannot drift apart silently.
"""

from typing import Any

_RAILS = ["RIPPLE", "SWIFT", "PAPSS"]

COMPLIANCE_VERDICT_NAME = "ComplianceVerdict"
COMPLIANCE_VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["outcome", "riskScore", "citedRules", "rationale"],
    "properties": {
        "outcome": {"enum": ["PASS", "ESCALATE", "BLOCK"]},
        "riskScore": {"type": "number", "minimum": 0, "maximum": 1},
        "citedRules": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": {"type": "string", "minLength": 1, "maxLength": 200},
        },
        "rationale": {"type": "string", "maxLength": 600},
        "constraints": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "forbiddenRails": {
                    "type": "array",
                    "maxItems": 3,
                    "uniqueItems": True,
                    "items": {"enum": _RAILS},
                },
                "maxSettlementSeconds": {"type": "number", "exclusiveMinimum": 0},
            },
        },
    },
}

LIQUIDITY_PROPOSAL_NAME = "LiquidityProposal"
LIQUIDITY_PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["rail", "totalCost", "estimatedSeconds", "rationale"],
    "properties": {
        "rail": {"enum": _RAILS},
        "totalCost": {
            "type": "object",
            "additionalProperties": False,
            "required": ["minorUnits", "currency"],
            "properties": {
                "minorUnits": {"type": "integer", "minimum": 0},
                "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
            },
        },
        "estimatedSeconds": {"type": "number", "exclusiveMinimum": 0},
        "rationale": {"type": "string", "maxLength": 400},
    },
}
