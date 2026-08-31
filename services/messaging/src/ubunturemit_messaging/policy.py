"""ISO 20022 schema policy matrix loader and validation."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml


class PolicyValidationError(ValueError):
    """Raised when a schema policy matrix fails schema, structural, or business rules."""


class ConformanceClaim(StrEnum):
    """Permitted values for conformance.claim."""

    ISO_20022_BASE = "ISO_20022_BASE"
    SARB_PEM_CONFORMANT = "SARB_PEM_CONFORMANT"


class ContextSource(StrEnum):
    """Permitted provenance sources for clearing contexts."""

    PUBLIC_BASE_CATALOGUE = "PUBLIC_BASE_CATALOGUE"
    SARB_MYSTANDARDS = "SARB_MYSTANDARDS"


@dataclass(frozen=True)
class MessagePolicy:
    """Policy entry for a specific ISO 20022 message identifier."""

    authorized_version: str | None
    sha256: str | None


@dataclass(frozen=True)
class ClearingContextPolicy:
    """Policy for a clearing context (e.g. base, samos, sadc_rtgs)."""

    source: ContextSource
    retrieved_on: str | None
    messages: dict[str, MessagePolicy]


@dataclass(frozen=True)
class SchemaPolicyMatrix:
    """In-memory representation of schema-policy.yaml."""

    conformance_claim: ConformanceClaim
    conformance_not_claimed: str
    contexts: dict[str, ClearingContextPolicy]

    def get_message_policy(self, context: str, message_identifier: str) -> MessagePolicy | None:
        """Look up message policy for a given clearing context and message identifier."""
        ctx = self.contexts.get(context)
        if ctx is None:
            return None
        return ctx.messages.get(message_identifier)

    def is_version_authorized(self, context: str, message_identifier: str, version: str) -> bool:
        """Check if a specific version suffix is authorized in the given context."""
        msg_policy = self.get_message_policy(context, message_identifier)
        if msg_policy is None or msg_policy.authorized_version is None:
            return False
        return msg_policy.authorized_version == version


REQUIRED_CONTEXTS = {"base", "samos", "sadc_rtgs"}


def load_schema_policy(path: Path | str) -> SchemaPolicyMatrix:
    """Load and strictly validate a schema-policy.yaml file."""
    path_obj = Path(path)
    if not path_obj.is_file():
        raise FileNotFoundError(f"Policy file not found: {path_obj}")

    with path_obj.open("r", encoding="utf-8") as f:
        try:
            data: Any = yaml.safe_load(f)
        except yaml.YAMLError as err:
            raise PolicyValidationError(f"Malformed YAML in policy file: {err}") from err

    if not isinstance(data, dict):
        raise PolicyValidationError("Policy file must contain a top-level mapping.")

    # 1. Conformance section validation
    conformance_raw = data.get("conformance")
    if not isinstance(conformance_raw, dict):
        raise PolicyValidationError("Missing required 'conformance' section in policy file.")

    claim_raw = conformance_raw.get("claim")
    try:
        conformance_claim = ConformanceClaim(str(claim_raw))
    except ValueError as err:
        raise PolicyValidationError(
            f"Invalid conformance claim '{claim_raw}'. "
            f"Allowed: {[c.value for c in ConformanceClaim]}"
        ) from err

    not_claimed_raw = conformance_raw.get("notClaimed")
    if not isinstance(not_claimed_raw, str):
        raise PolicyValidationError("Missing or invalid 'notClaimed' in conformance section.")

    # 2. Contexts section validation
    contexts_raw = data.get("contexts")
    if not isinstance(contexts_raw, dict):
        raise PolicyValidationError("Missing required 'contexts' section in policy file.")

    missing_contexts = REQUIRED_CONTEXTS - contexts_raw.keys()
    if missing_contexts:
        raise PolicyValidationError(
            f"Missing required context(s) in policy file: {sorted(missing_contexts)}"
        )

    parsed_contexts: dict[str, ClearingContextPolicy] = {}
    for ctx_name, ctx_data in contexts_raw.items():
        if not isinstance(ctx_data, dict):
            raise PolicyValidationError(f"Context '{ctx_name}' must be a mapping.")

        source_raw = ctx_data.get("source")
        if not source_raw:
            raise PolicyValidationError(f"Context '{ctx_name}' is missing required 'source' field.")

        try:
            context_source = ContextSource(str(source_raw))
        except ValueError as err:
            raise PolicyValidationError(
                f"Invalid source '{source_raw}' for context '{ctx_name}'. "
                f"Allowed: {[s.value for s in ContextSource]}"
            ) from err

        retrieved_on = ctx_data.get("retrievedOn")
        if retrieved_on is not None and not isinstance(retrieved_on, str):
            raise PolicyValidationError(
                f"Context '{ctx_name}' has invalid 'retrievedOn' value: {retrieved_on}"
            )

        messages_raw = ctx_data.get("messages")
        if not isinstance(messages_raw, dict):
            raise PolicyValidationError(f"Context '{ctx_name}' must contain a 'messages' mapping.")

        parsed_messages: dict[str, MessagePolicy] = {}
        for msg_id, msg_data in messages_raw.items():
            if not isinstance(msg_data, dict):
                raise PolicyValidationError(
                    f"Message entry '{msg_id}' in context '{ctx_name}' must be a mapping."
                )

            auth_ver = msg_data.get("authorizedVersion")
            if auth_ver is not None:
                auth_ver = str(auth_ver)

            sha = msg_data.get("sha256")
            if sha is not None:
                sha = str(sha)

            parsed_messages[msg_id] = MessagePolicy(
                authorized_version=auth_ver,
                sha256=sha,
            )

        parsed_contexts[ctx_name] = ClearingContextPolicy(
            source=context_source,
            retrieved_on=retrieved_on,
            messages=parsed_messages,
        )

    # 3. Business rule: Conformance boundary check (Non-negotiable I)
    # If SARB_PEM_CONFORMANT is claimed, both samos and sadc_rtgs contexts must be
    # populated with authorized versions from SARB_MYSTANDARDS.
    if conformance_claim == ConformanceClaim.SARB_PEM_CONFORMANT:
        samos_msgs = parsed_contexts.get("samos")
        sadc_msgs = parsed_contexts.get("sadc_rtgs")
        has_samos = samos_msgs and any(m.authorized_version for m in samos_msgs.messages.values())
        has_sadc = sadc_msgs and any(m.authorized_version for m in sadc_msgs.messages.values())
        if not (has_samos and has_sadc):
            raise PolicyValidationError(
                "Cannot claim SARB_PEM_CONFORMANT without populated SARB_MYSTANDARDS "
                "clearing contexts for both 'samos' and 'sadc_rtgs'."
            )

    return SchemaPolicyMatrix(
        conformance_claim=conformance_claim,
        conformance_not_claimed=not_claimed_raw,
        contexts=parsed_contexts,
    )
