"""The schemas in code are the schemas in the design -- docs/design/inference.md §5."""

import json
import re
from pathlib import Path

from ubunturemit_inference import (
    COMPLIANCE_VERDICT_NAME,
    COMPLIANCE_VERDICT_SCHEMA,
    LIQUIDITY_PROPOSAL_NAME,
    LIQUIDITY_PROPOSAL_SCHEMA,
)

DESIGN = Path(__file__).resolve().parents[3] / "docs" / "design" / "inference.md"


def _design_blocks() -> dict[str, dict[str, object]]:
    blocks = re.findall(r"```json\n(.*?)```", DESIGN.read_text(), re.S)
    return {block["name"]: block for block in map(json.loads, blocks)}


def test_code_schemas_equal_the_design_doc_blocks() -> None:
    blocks = _design_blocks()
    assert blocks == {
        COMPLIANCE_VERDICT_NAME: {
            "name": COMPLIANCE_VERDICT_NAME,
            "strict": True,
            "schema": COMPLIANCE_VERDICT_SCHEMA,
        },
        LIQUIDITY_PROPOSAL_NAME: {
            "name": LIQUIDITY_PROPOSAL_NAME,
            "strict": True,
            "schema": LIQUIDITY_PROPOSAL_SCHEMA,
        },
    }
