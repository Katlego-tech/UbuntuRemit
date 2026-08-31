"""Tests for ISO 20022 schema policy matrix loader and validation."""

from pathlib import Path

import pytest
from ubunturemit_messaging.policy import (
    ConformanceClaim,
    ContextSource,
    PolicyValidationError,
    load_schema_policy,
)

ROOT_POLICY_PATH = Path(__file__).resolve().parent.parent / "schema-policy.yaml"


def test_load_default_unpopulated_policy() -> None:
    """Verifies that the canonical schema-policy.yaml loads cleanly in its unpopulated state."""
    matrix = load_schema_policy(ROOT_POLICY_PATH)

    assert matrix.conformance_claim == ConformanceClaim.ISO_20022_BASE
    assert matrix.conformance_not_claimed == "SARB_PEM_CONFORMANT"

    # Base context
    assert "base" in matrix.contexts
    base_ctx = matrix.contexts["base"]
    assert base_ctx.source == ContextSource.PUBLIC_BASE_CATALOGUE
    assert base_ctx.retrieved_on is None
    assert "pain.001.001" in base_ctx.messages
    assert base_ctx.messages["pain.001.001"].authorized_version is None
    assert base_ctx.messages["pain.001.001"].sha256 is None

    # Clearing contexts (present but empty of messages)
    assert "samos" in matrix.contexts
    assert matrix.contexts["samos"].source == ContextSource.SARB_MYSTANDARDS
    assert matrix.contexts["samos"].messages == {}

    assert "sadc_rtgs" in matrix.contexts
    assert matrix.contexts["sadc_rtgs"].source == ContextSource.SARB_MYSTANDARDS
    assert matrix.contexts["sadc_rtgs"].messages == {}


def test_reject_nonexistent_policy_file() -> None:
    """Verifies that loading a non-existent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_schema_policy(Path("nonexistent/path/schema-policy.yaml"))


def test_reject_missing_conformance_section(tmp_path: Path) -> None:
    """Rejects policy YAML missing top-level conformance block."""
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text("contexts: {}\n", encoding="utf-8")

    with pytest.raises(PolicyValidationError, match="Missing required 'conformance' section"):
        load_schema_policy(policy_file)


def test_reject_missing_contexts_section(tmp_path: Path) -> None:
    """Rejects policy YAML missing top-level contexts block."""
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(
        "conformance:\n  claim: ISO_20022_BASE\n  notClaimed: SARB_PEM_CONFORMANT\n",
        encoding="utf-8",
    )

    with pytest.raises(PolicyValidationError, match="Missing required 'contexts' section"):
        load_schema_policy(policy_file)


def test_reject_missing_required_context(tmp_path: Path) -> None:
    """Rejects policy YAML missing required clearing contexts (base, samos, sadc_rtgs)."""
    policy_file = tmp_path / "policy.yaml"
    content = """
conformance:
  claim: ISO_20022_BASE
  notClaimed: SARB_PEM_CONFORMANT
contexts:
  base:
    source: PUBLIC_BASE_CATALOGUE
    messages: {}
"""
    policy_file.write_text(content, encoding="utf-8")

    with pytest.raises(PolicyValidationError, match="Missing required context"):
        load_schema_policy(policy_file)


def test_reject_missing_source_in_context(tmp_path: Path) -> None:
    """Rejects policy YAML when a context lacks the load-bearing 'source' field."""
    policy_file = tmp_path / "policy.yaml"
    content = """
conformance:
  claim: ISO_20022_BASE
  notClaimed: SARB_PEM_CONFORMANT
contexts:
  base:
    messages: {}
  samos:
    source: SARB_MYSTANDARDS
    messages: {}
  sadc_rtgs:
    source: SARB_MYSTANDARDS
    messages: {}
"""
    policy_file.write_text(content, encoding="utf-8")

    with pytest.raises(PolicyValidationError, match="missing required 'source'"):
        load_schema_policy(policy_file)


def test_reject_unearned_sarb_conformance_claim(tmp_path: Path) -> None:
    """Non-negotiable I: cannot claim SARB PEM conformance when clearing contexts are empty."""
    policy_file = tmp_path / "policy.yaml"
    content = """
conformance:
  claim: SARB_PEM_CONFORMANT
  notClaimed: NONE
contexts:
  base:
    source: PUBLIC_BASE_CATALOGUE
    messages: {}
  samos:
    source: SARB_MYSTANDARDS
    messages: {}
  sadc_rtgs:
    source: SARB_MYSTANDARDS
    messages: {}
"""
    policy_file.write_text(content, encoding="utf-8")

    with pytest.raises(
        PolicyValidationError,
        match="Cannot claim SARB_PEM_CONFORMANT without populated SARB_MYSTANDARDS",
    ):
        load_schema_policy(policy_file)


def test_reject_invalid_claim_value(tmp_path: Path) -> None:
    """Rejects unknown conformance claim enum values."""
    policy_file = tmp_path / "policy.yaml"
    content = """
conformance:
  claim: FULLY_CERTIFIED_SARB_CUSTOM
  notClaimed: NONE
contexts:
  base: { source: PUBLIC_BASE_CATALOGUE, messages: {} }
  samos: { source: SARB_MYSTANDARDS, messages: {} }
  sadc_rtgs: { source: SARB_MYSTANDARDS, messages: {} }
"""
    policy_file.write_text(content, encoding="utf-8")

    with pytest.raises(PolicyValidationError, match="Invalid conformance claim"):
        load_schema_policy(policy_file)
