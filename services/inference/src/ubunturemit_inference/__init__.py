"""UbuntuRemit inference client -- docs/design/inference.md."""

from ubunturemit_inference.client import (
    CHAT_COMPLETIONS_PATH,
    InferenceResponseError,
    VllmChatClient,
)
from ubunturemit_inference.schemas import (
    COMPLIANCE_VERDICT_NAME,
    COMPLIANCE_VERDICT_SCHEMA,
    LIQUIDITY_PROPOSAL_NAME,
    LIQUIDITY_PROPOSAL_SCHEMA,
)

__all__ = [
    "CHAT_COMPLETIONS_PATH",
    "COMPLIANCE_VERDICT_NAME",
    "COMPLIANCE_VERDICT_SCHEMA",
    "InferenceResponseError",
    "LIQUIDITY_PROPOSAL_NAME",
    "LIQUIDITY_PROPOSAL_SCHEMA",
    "VllmChatClient",
]
