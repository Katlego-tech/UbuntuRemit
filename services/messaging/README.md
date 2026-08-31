# `services/messaging` — ISO 20022 Message Layer & Schema Governance

This service is responsible for building, parsing, verifying, and validating ISO 20022 messages
(`pain.001`, `pacs.008`, `camt.053`, and `head.001` Business Application Headers).

---

## ⚠ Conformance Boundary

This service builds and validates messages strictly against the **public ISO 20022 base catalogue**
hosted at [iso20022.org](https://www.iso20022.org).

**It is NOT SARB PEM-conformant and makes NO claim of SARB authorization.**

Per [docs/design/iso20022-messaging.md](../../docs/design/iso20022-messaging.md) §3.6:

| We may say | We may **NOT** say |
| :--- | :--- |
| Messages conform to the ISO 20022 base catalogue | Messages conform to SARB PEM Usage Guidelines |
| Schema versions are pinned, checksummed, and verified | Schema versions are SARB-authorised |
| The pipeline enforces version and dependency policy | The pipeline enforces SARB policy |
| The design targets SAMOS / SADC-RTGS | The implementation is accepted by SAMOS / SADC-RTGS |

SARB Usage Guidelines live on SWIFT MyStandards behind participant standing this project does not possess.
`schema-policy.yaml` carries this boundary as machine-enforceable data (`conformance.claim: ISO_20022_BASE`),
and unit tests enforce that any unearned claim of `SARB_PEM_CONFORMANT` fails the build.

---

## Vendored Schemas (`schemas/`)

All schemas in `schemas/` are admitted exclusively through the 6-stage schema verification pipeline
(`verify_schema.py`). Every schema version and SHA-256 checksum is extracted directly from the XSD
`targetNamespace` and content:

- `pain.001.001.09.xsd` (`urn:iso:std:iso:20022:tech:xsd:pain.001.001.09`) — Customer Credit Transfer Initiation
- `pacs.008.001.08.xsd` (`urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08`) — Financial Institution Customer Credit Transfer
- `camt.053.001.08.xsd` (`urn:iso:std:iso:20022:tech:xsd:camt.053.001.08`) — Bank to Customer Statement
- `head.001.001.02.xsd` (`urn:iso:std:iso:20022:tech:xsd:head.001.001.02`) — Business Application Header

---

## Verification Pipeline

To run the verification pipeline manually:

```bash
uv run python services/messaging/verify_schema.py
```

The pipeline enforces:
1. File format and presence (`.xsd`).
2. XML DOM well-formedness with root `<xs:schema>`.
3. Presence of `targetNamespace`.
4. URN regex validation: exact match on `^urn:iso:std:iso:20022:tech:xsd:([a-z]{4})\.([0-9]{3})\.([0-9]{3})\.([0-9]{2})$` (catching typos such as missing zero `iso:2022`).
5. Component suffix resolution.
6. Schema policy matrix evaluation and SHA-256 checksum verification.
7. Recursive dependency traversal for `<xs:import>` / `<xs:redefine>` including Business Application Headers.
