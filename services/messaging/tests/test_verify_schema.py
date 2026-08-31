"""Tests for the 6-stage (plus dependency recursion) ISO 20022 schema verification pipeline."""

from pathlib import Path

import pytest
from ubunturemit_messaging.policy import (
    ClearingContextPolicy,
    ConformanceClaim,
    ContextSource,
    MessagePolicy,
    SchemaPolicyMatrix,
)
from ubunturemit_messaging.verify_schema import verify_schema

MINIMAL_XSD_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           {ns_decl}
           elementFormDefault="qualified"
           {target_ns}>
    {content}
</xs:schema>
"""


@pytest.fixture
def test_policy() -> SchemaPolicyMatrix:
    """Fixture policy authorising pacs.008.001.08, pain.001.001.09, and head.001.001.02."""
    return SchemaPolicyMatrix(
        conformance_claim=ConformanceClaim.ISO_20022_BASE,
        conformance_not_claimed="SARB_PEM_CONFORMANT",
        contexts={
            "base": ClearingContextPolicy(
                source=ContextSource.PUBLIC_BASE_CATALOGUE,
                retrieved_on="2026-08-31",
                messages={
                    "pacs.008.001": MessagePolicy(authorized_version="08", sha256=None),
                    "pain.001.001": MessagePolicy(authorized_version="09", sha256=None),
                    "camt.053.001": MessagePolicy(authorized_version="08", sha256=None),
                    "head.001.001": MessagePolicy(authorized_version="02", sha256=None),
                },
            ),
            "samos": ClearingContextPolicy(
                source=ContextSource.SARB_MYSTANDARDS,
                retrieved_on=None,
                messages={},
            ),
            "sadc_rtgs": ClearingContextPolicy(
                source=ContextSource.SARB_MYSTANDARDS,
                retrieved_on=None,
                messages={},
            ),
        },
    )


# ------------------------------------------------------------------ Stage 1 ----


def test_stage1_reject_non_xsd_file(tmp_path: Path, test_policy: SchemaPolicyMatrix) -> None:
    """Stage 1: File ingestion must reject files without .xsd extension."""
    bad_file = tmp_path / "schema.xml"
    bad_file.write_text("<xs:schema/>", encoding="utf-8")

    result = verify_schema(bad_file, test_policy)
    assert not result.ok
    assert result.stage == 1
    assert "not an XSD schema (.xsd)" in (result.reason or "")


def test_stage1_reject_nonexistent_file(tmp_path: Path, test_policy: SchemaPolicyMatrix) -> None:
    """Stage 1: File ingestion must reject missing files."""
    missing = tmp_path / "missing.xsd"
    result = verify_schema(missing, test_policy)
    assert not result.ok
    assert result.stage == 1
    assert "File not found" in (result.reason or "")


# ------------------------------------------------------------------ Stage 2 ----


def test_stage2_reject_invalid_xml_syntax(tmp_path: Path, test_policy: SchemaPolicyMatrix) -> None:
    """Stage 2: XML DOM parse must catch XML syntax errors."""
    bad_xml = tmp_path / "syntax_error.xsd"
    bad_xml.write_text("<xs:schema><unclosed>", encoding="utf-8")

    result = verify_schema(bad_xml, test_policy)
    assert not result.ok
    assert result.stage == 2
    assert "XML syntax error" in (result.reason or "")


def test_stage2_reject_non_schema_root(tmp_path: Path, test_policy: SchemaPolicyMatrix) -> None:
    """Stage 2: Root element must be an XSD schema tag."""
    bad_root = tmp_path / "not_schema.xsd"
    bad_root.write_text("<root xmlns='http://example.com'/>", encoding="utf-8")

    result = verify_schema(bad_root, test_policy)
    assert not result.ok
    assert result.stage == 2
    assert "Root element is not <xs:schema>" in (result.reason or "")


# ------------------------------------------------------------------ Stage 3 ----


def test_stage3_reject_missing_target_namespace(
    tmp_path: Path, test_policy: SchemaPolicyMatrix
) -> None:
    """Stage 3: Namespace extraction must require targetNamespace on root schema."""
    no_target_ns = tmp_path / "no_target_ns.xsd"
    content = MINIMAL_XSD_TEMPLATE.format(
        ns_decl="",
        target_ns="",
        content="<xs:element name='Doc'/>",
    )
    no_target_ns.write_text(content, encoding="utf-8")

    result = verify_schema(no_target_ns, test_policy)
    assert not result.ok
    assert result.stage == 3
    assert "missing required 'targetNamespace'" in (result.reason or "")


# ------------------------------------------------------------------ Stage 4 ----


def test_stage4_reject_typo_urn_base_missing_zero(
    tmp_path: Path, test_policy: SchemaPolicyMatrix
) -> None:
    """Stage 4: Catch the known vendor failure 'urn:iso:std:iso:2022:tech:xsd:' (missing zero)."""
    typo_xsd = tmp_path / "typo_urn.xsd"
    ns = "urn:iso:std:iso:2022:tech:xsd:pacs.008.001.08"
    content = MINIMAL_XSD_TEMPLATE.format(
        ns_decl=f'xmlns="{ns}"',
        target_ns=f'targetNamespace="{ns}"',
        content="<xs:element name='Doc'/>",
    )
    typo_xsd.write_text(content, encoding="utf-8")

    result = verify_schema(typo_xsd, test_policy)
    assert not result.ok
    assert result.stage == 4
    assert "does not match required URN pattern" in (result.reason or "")


def test_stage4_reject_http_namespace(tmp_path: Path, test_policy: SchemaPolicyMatrix) -> None:
    """Stage 4: Reject non-ISO URN namespace format (e.g. http URI)."""
    http_xsd = tmp_path / "http_ns.xsd"
    ns = "http://iso20022.org/pacs.008.001.08"
    content = MINIMAL_XSD_TEMPLATE.format(
        ns_decl=f'xmlns="{ns}"',
        target_ns=f'targetNamespace="{ns}"',
        content="<xs:element name='Doc'/>",
    )
    http_xsd.write_text(content, encoding="utf-8")

    result = verify_schema(http_xsd, test_policy)
    assert not result.ok
    assert result.stage == 4
    assert "does not match required URN pattern" in (result.reason or "")


# ------------------------------------------------------------------ Stage 5 ----


def test_stage5_reject_invalid_suffix_format(
    tmp_path: Path, test_policy: SchemaPolicyMatrix
) -> None:
    """Stage 5: Reject components not matching <area>.<type>.<variant>.<version>."""
    bad_suffix_xsd = tmp_path / "bad_suffix.xsd"
    ns = "urn:iso:std:iso:20022:tech:xsd:pacs.008.1.8"  # unpadded variant and version
    content = MINIMAL_XSD_TEMPLATE.format(
        ns_decl=f'xmlns="{ns}"',
        target_ns=f'targetNamespace="{ns}"',
        content="<xs:element name='Doc'/>",
    )
    bad_suffix_xsd.write_text(content, encoding="utf-8")

    result = verify_schema(bad_suffix_xsd, test_policy)
    assert not result.ok
    assert result.stage == 4 or result.stage == 5


# ------------------------------------------------------------------ Stage 6 ----


def test_stage6_reject_unauthorized_version(
    tmp_path: Path, test_policy: SchemaPolicyMatrix
) -> None:
    """Stage 6: Reject version suffix not authorized in policy matrix."""
    unauthorized_xsd = tmp_path / "pacs.008.001.09.xsd"
    ns = "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.09"  # policy only has 08
    content = MINIMAL_XSD_TEMPLATE.format(
        ns_decl=f'xmlns="{ns}"',
        target_ns=f'targetNamespace="{ns}"',
        content="<xs:element name='Doc'/>",
    )
    unauthorized_xsd.write_text(content, encoding="utf-8")

    result = verify_schema(unauthorized_xsd, test_policy)
    assert not result.ok
    assert result.stage == 6
    assert "not authorized in clearing context" in (result.reason or "")


def test_stage6_reject_checksum_mismatch(tmp_path: Path, test_policy: SchemaPolicyMatrix) -> None:
    """Stage 6: Reject when file hash does not match pinned checksum in policy."""
    policy_with_sha = SchemaPolicyMatrix(
        conformance_claim=ConformanceClaim.ISO_20022_BASE,
        conformance_not_claimed="SARB_PEM_CONFORMANT",
        contexts={
            "base": ClearingContextPolicy(
                source=ContextSource.PUBLIC_BASE_CATALOGUE,
                retrieved_on="2026-08-31",
                messages={
                    "pacs.008.001": MessagePolicy(
                        authorized_version="08",
                        sha256="0000000000000000000000000000000000000000000000000000000000000000",
                    ),
                },
            ),
            "samos": ClearingContextPolicy(
                source=ContextSource.SARB_MYSTANDARDS,
                retrieved_on=None,
                messages={},
            ),
            "sadc_rtgs": ClearingContextPolicy(
                source=ContextSource.SARB_MYSTANDARDS,
                retrieved_on=None,
                messages={},
            ),
        },
    )
    pacs_xsd = tmp_path / "pacs.008.001.08.xsd"
    ns = "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08"
    content = MINIMAL_XSD_TEMPLATE.format(
        ns_decl=f'xmlns="{ns}"',
        target_ns=f'targetNamespace="{ns}"',
        content="<xs:element name='Doc'/>",
    )
    pacs_xsd.write_text(content, encoding="utf-8")

    result = verify_schema(pacs_xsd, policy_with_sha)
    assert not result.ok
    assert result.stage == 6
    assert "Checksum mismatch" in (result.reason or "")


# ------------------------------------------------------------------ Stage 7 ----


def test_stage7_reject_missing_imported_dependency(
    tmp_path: Path, test_policy: SchemaPolicyMatrix
) -> None:
    """Stage 7: Recurse xs:import and reject missing dependency file."""
    pacs_xsd = tmp_path / "pacs.008.001.08.xsd"
    ns = "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08"
    content = MINIMAL_XSD_TEMPLATE.format(
        ns_decl=f'xmlns="{ns}"',
        target_ns=f'targetNamespace="{ns}"',
        content="<xs:import namespace='urn:iso:std:iso:20022:tech:xsd:head.001.001.02' "
        "schemaLocation='missing_head.xsd'/>",
    )
    pacs_xsd.write_text(content, encoding="utf-8")

    result = verify_schema(pacs_xsd, test_policy)
    assert not result.ok
    assert result.stage == 7
    assert "Dependency" in (result.reason or "")
    assert "failed verification" in (result.reason or "")


def test_stage7_reject_outdated_imported_dependency(
    tmp_path: Path, test_policy: SchemaPolicyMatrix
) -> None:
    """Stage 7: Reject when imported dependency (e.g. BAH) carries an unauthorized version."""
    bah_xsd = tmp_path / "head.001.001.01.xsd"
    bah_ns = "urn:iso:std:iso:20022:tech:xsd:head.001.001.01"  # policy only authorises 02
    bah_content = MINIMAL_XSD_TEMPLATE.format(
        ns_decl=f'xmlns="{bah_ns}"',
        target_ns=f'targetNamespace="{bah_ns}"',
        content="<xs:element name='AppHdr'/>",
    )
    bah_xsd.write_text(bah_content, encoding="utf-8")

    pacs_xsd = tmp_path / "pacs.008.001.08.xsd"
    pacs_ns = "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08"
    pacs_content = MINIMAL_XSD_TEMPLATE.format(
        ns_decl=f'xmlns="{pacs_ns}"',
        target_ns=f'targetNamespace="{pacs_ns}"',
        content=f"<xs:import namespace='{bah_ns}' schemaLocation='head.001.001.01.xsd'/>",
    )
    pacs_xsd.write_text(pacs_content, encoding="utf-8")

    result = verify_schema(pacs_xsd, test_policy)
    assert not result.ok
    assert result.stage == 7
    assert "stage 6" in (result.reason or "")


def test_stage7_reject_dependency_namespace_mismatch(
    tmp_path: Path, test_policy: SchemaPolicyMatrix
) -> None:
    """Stage 7: xs:import namespace attribute must match imported file's targetNamespace."""
    bah_xsd = tmp_path / "head.001.001.02.xsd"
    bah_ns = "urn:iso:std:iso:20022:tech:xsd:head.001.001.02"
    bah_content = MINIMAL_XSD_TEMPLATE.format(
        ns_decl=f'xmlns="{bah_ns}"',
        target_ns=f'targetNamespace="{bah_ns}"',
        content="<xs:element name='AppHdr'/>",
    )
    bah_xsd.write_text(bah_content, encoding="utf-8")

    pacs_xsd = tmp_path / "pacs.008.001.08.xsd"
    pacs_ns = "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08"
    pacs_content = MINIMAL_XSD_TEMPLATE.format(
        ns_decl=f'xmlns="{pacs_ns}"',
        target_ns=f'targetNamespace="{pacs_ns}"',
        content="<xs:import namespace='urn:iso:std:iso:20022:tech:xsd:head.001.001.01' "
        "schemaLocation='head.001.001.02.xsd'/>",
    )
    pacs_xsd.write_text(pacs_content, encoding="utf-8")

    result = verify_schema(pacs_xsd, test_policy)
    assert not result.ok
    assert result.stage == 7
    assert "Imported schema namespace mismatch" in (result.reason or "")


# ------------------------------------------------------------------ Success path ----


def test_valid_schema_with_dependency_passes_all_stages(
    tmp_path: Path, test_policy: SchemaPolicyMatrix
) -> None:
    """Golden path: valid pacs.008 importing valid head.001 passes all verification stages."""
    bah_xsd = tmp_path / "head.001.001.02.xsd"
    bah_ns = "urn:iso:std:iso:20022:tech:xsd:head.001.001.02"
    bah_content = MINIMAL_XSD_TEMPLATE.format(
        ns_decl=f'xmlns="{bah_ns}"',
        target_ns=f'targetNamespace="{bah_ns}"',
        content="<xs:element name='AppHdr'/>",
    )
    bah_xsd.write_text(bah_content, encoding="utf-8")

    pacs_xsd = tmp_path / "pacs.008.001.08.xsd"
    pacs_ns = "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08"
    pacs_content = MINIMAL_XSD_TEMPLATE.format(
        ns_decl=f'xmlns="{pacs_ns}"',
        target_ns=f'targetNamespace="{pacs_ns}"',
        content=f"<xs:import namespace='{bah_ns}' schemaLocation='head.001.001.02.xsd'/>"
        "<xs:element name='Document'/>",
    )
    pacs_xsd.write_text(pacs_content, encoding="utf-8")

    result = verify_schema(pacs_xsd, test_policy)
    assert result.ok
    assert result.stage is None
    assert result.reason is None
    assert result.message_identifier == "pacs.008.001"
    assert result.version_suffix == "08"
    assert result.target_namespace == pacs_ns
    assert "head.001.001.02.xsd" in result.dependencies_verified
