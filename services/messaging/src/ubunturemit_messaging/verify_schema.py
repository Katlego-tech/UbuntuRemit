"""Six-stage ISO 20022 XML Schema verification pipeline.

Implements the specification from docs/design/iso20022-messaging.md §3.4.
"""

import hashlib
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from ubunturemit_messaging.policy import SchemaPolicyMatrix, load_schema_policy

# Stage 4 pattern: Must match the exact ISO 20022 URN prefix.
# Catches the known vendor typo 'urn:iso:std:iso:2022:tech:xsd:' (missing zero).
ISO_20022_URN_PATTERN = re.compile(
    r"^urn:iso:std:iso:20022:tech:xsd:([a-z]{4})\.([0-9]{3})\.([0-9]{3})\.([0-9]{2})$"
)

XML_SCHEMA_NS = "http://www.w3.org/2001/XMLSchema"


@dataclass(frozen=True)
class SchemaVerificationResult:
    """Outcome of running an XSD file through the verification pipeline."""

    ok: bool
    stage: int | None = None
    reason: str | None = None
    path: Path | None = None
    target_namespace: str | None = None
    message_identifier: str | None = None
    version_suffix: str | None = None
    dependencies_verified: tuple[str, ...] = field(default_factory=tuple)


def verify_schema(
    schema_path: Path | str,
    policy: SchemaPolicyMatrix | Path | str | None = None,
    context: str = "base",
    _seen_paths: set[Path] | None = None,
) -> SchemaVerificationResult:
    """Execute the 6-stage verification pipeline and dependency traversal on an XSD schema."""
    path = Path(schema_path).resolve()
    if _seen_paths is None:
        _seen_paths = set()

    if path in _seen_paths:
        return SchemaVerificationResult(ok=True, path=path)

    # 1. Resolve policy
    if policy is None:
        default_policy_path = Path(__file__).resolve().parent.parent.parent / "schema-policy.yaml"
        loaded_policy = load_schema_policy(default_policy_path)
    elif isinstance(policy, (str, Path)):
        loaded_policy = load_schema_policy(policy)
    else:
        loaded_policy = policy

    # Stage 1: File ingestion
    if not path.is_file():
        return SchemaVerificationResult(
            ok=False,
            stage=1,
            reason=f"File not found or not a regular file: {path}",
            path=path,
        )

    if path.suffix.lower() != ".xsd":
        return SchemaVerificationResult(
            ok=False,
            stage=1,
            reason=f"File is not an XSD schema (.xsd): {path.name}",
            path=path,
        )

    _seen_paths.add(path)

    # Stage 2: XML DOM parse
    try:
        tree = etree.parse(str(path))
    except (etree.XMLSyntaxError, OSError) as err:
        return SchemaVerificationResult(
            ok=False,
            stage=2,
            reason=f"XML syntax error in {path.name}: {err}",
            path=path,
        )

    root = tree.getroot()
    if root.tag != f"{{{XML_SCHEMA_NS}}}schema":
        return SchemaVerificationResult(
            ok=False,
            stage=2,
            reason=f"Root element is not <xs:schema>, got '{root.tag}' in {path.name}",
            path=path,
        )

    # Stage 3: Namespace extraction
    target_ns = root.get("targetNamespace")
    if not target_ns or not target_ns.strip():
        return SchemaVerificationResult(
            ok=False,
            stage=3,
            reason=f"Root <xs:schema> missing required 'targetNamespace' attribute in {path.name}",
            path=path,
        )

    target_ns = target_ns.strip()

    # Stage 4: URN regex validation
    match = ISO_20022_URN_PATTERN.match(target_ns)
    if not match:
        return SchemaVerificationResult(
            ok=False,
            stage=4,
            reason=(
                f"targetNamespace '{target_ns}' does not match required URN pattern "
                f"'^urn:iso:std:iso:20022:tech:xsd:<area>.<type>.<var>.<ver>' in {path.name}"
            ),
            path=path,
            target_namespace=target_ns,
        )

    # Stage 5: Suffix resolution
    business_area, message_type, variant, version_suffix = match.groups()
    message_identifier = f"{business_area}.{message_type}.{variant}"

    # Stage 6: Policy evaluation
    msg_policy = loaded_policy.get_message_policy(context, message_identifier)
    if msg_policy is None or msg_policy.authorized_version != version_suffix:
        expected = msg_policy.authorized_version if msg_policy else "unlisted"
        return SchemaVerificationResult(
            ok=False,
            stage=6,
            reason=(
                f"Message '{message_identifier}' version '{version_suffix}' is not authorized "
                f"in clearing context '{context}' (expected '{expected}') for {path.name}"
            ),
            path=path,
            target_namespace=target_ns,
            message_identifier=message_identifier,
            version_suffix=version_suffix,
        )

    if msg_policy.sha256 is not None:
        file_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if file_sha.lower() != msg_policy.sha256.lower():
            return SchemaVerificationResult(
                ok=False,
                stage=6,
                reason=(
                    f"Checksum mismatch for {path.name}: computed '{file_sha}' "
                    f"does not match policy '{msg_policy.sha256}'"
                ),
                path=path,
                target_namespace=target_ns,
                message_identifier=message_identifier,
                version_suffix=version_suffix,
            )

    # Stage 7: Dependency traversal (xs:import / xs:redefine)
    dependencies: list[str] = []
    dep_elements = root.findall(f"{{{XML_SCHEMA_NS}}}import") + root.findall(
        f"{{{XML_SCHEMA_NS}}}redefine"
    )

    for dep_elem in dep_elements:
        schema_loc = dep_elem.get("schemaLocation")
        dep_ns = dep_elem.get("namespace")

        if not schema_loc:
            continue

        dep_path = (path.parent / schema_loc).resolve()
        dep_result = verify_schema(
            dep_path,
            policy=loaded_policy,
            context=context,
            _seen_paths=_seen_paths,
        )

        if not dep_result.ok:
            return SchemaVerificationResult(
                ok=False,
                stage=7,
                reason=(
                    f"Dependency '{schema_loc}' referenced by {path.name} failed verification "
                    f"at stage {dep_result.stage}: {dep_result.reason}"
                ),
                path=path,
                target_namespace=target_ns,
                message_identifier=message_identifier,
                version_suffix=version_suffix,
            )

        if dep_ns and dep_result.target_namespace and dep_ns != dep_result.target_namespace:
            return SchemaVerificationResult(
                ok=False,
                stage=7,
                reason=(
                    f"Imported schema namespace mismatch in {path.name}: declared '{dep_ns}' "
                    f"but dependency '{schema_loc}' defines '{dep_result.target_namespace}'"
                ),
                path=path,
                target_namespace=target_ns,
                message_identifier=message_identifier,
                version_suffix=version_suffix,
            )

        dependencies.append(schema_loc)

    return SchemaVerificationResult(
        ok=True,
        path=path,
        target_namespace=target_ns,
        message_identifier=message_identifier,
        version_suffix=version_suffix,
        dependencies_verified=tuple(dependencies),
    )


def cli_main(argv: Sequence[str] | None = None) -> int:
    """CLI runner for verify_schema. Returns 0 on success, 1 on any violation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify ISO 20022 XML Schemas against the schema-policy matrix."
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="XSD schema files to verify. If omitted, checks services/messaging/schemas/*.xsd",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=None,
        help="Path to schema-policy.yaml matrix",
    )
    parser.add_argument(
        "--context",
        type=str,
        default="base",
        help="Clearing context name (default: 'base')",
    )

    args = parser.parse_args(argv)

    files_to_check = list(args.files)
    if not files_to_check:
        schemas_dir = Path(__file__).resolve().parent.parent.parent / "schemas"
        if schemas_dir.is_dir():
            files_to_check = list(schemas_dir.glob("*.xsd"))

    if not files_to_check:
        print("verify_schema: no XSD files to verify.")
        return 0

    violations = 0
    for f in files_to_check:
        res = verify_schema(f, policy=args.policy, context=args.context)
        if res.ok:
            deps_str = (
                f" (deps: {', '.join(res.dependencies_verified)})"
                if res.dependencies_verified
                else ""
            )
            print(f"OK: {f.name} -> {res.message_identifier}.{res.version_suffix}{deps_str}")
        else:
            print(f"VIOLATION [Stage {res.stage}] in {f.name}: {res.reason}", file=sys.stderr)
            violations += 1

    if violations > 0:
        print(f"\nverify_schema: FAILED ({violations} violation(s) found).", file=sys.stderr)
        return 1

    print(f"\nverify_schema: PASSED ({len(files_to_check)} schema(s) verified).")
    return 0


if __name__ == "__main__":
    sys.exit(cli_main())
