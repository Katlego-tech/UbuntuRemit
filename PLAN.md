# `UbuntuRemit` — Implementation Plan (the HOW)

**Companions:** [SPEC.md](SPEC.md) (the WHAT) · [docs/design/](docs/design/) (the shapes) ·
TASKS.md (the task list)

---

## Summary

A set of Domain-Driven microservices around one deterministic orchestrator: a FastAPI gateway
accepts a **pain.001**, hard-coded entry guardrails screen it, and the **ASCO** state machine then
runs a bounded negotiation between two locally-served LLM agents — a 70B-class Compliance Sentinel
and a 32B-class Liquidity Strategist — before a second set of hard-coded validators decides whether
the resulting **pacs.008** may be submitted to a rail. The key technical bet is that
*non-determinism is confined to advice*: models rank and explain, deterministic code permits.
Everything runs on a single AMD Instinct MI300X (192 GB HBM3) under ROCm 7.0 with vLLM, so both
models are co-resident and no transaction data leaves the institution. The hard constraints are
regulatory (SARB PEM traceability, FATF Travel Rule, ISO 20022 conformance) and temporal (RTGS SLA
windows), and they are what make an unbounded agent loop unacceptable.

---

## Non-negotiables (project principles)

These are the values every change is held to. If you're also running Spec-Kit or a similar tool,
this list is the "constitution" in plain language — keep both in sync, or drop the formal
constitution and let this section be the single copy (see
docs/planning-workflow.md).

1. **Never fabricate a regulatory fact, a rate, or a compliance verdict.** Every AML/KYC/SARB
   decision, FX rate, settlement confirmation and ISO 20022 field traces to a real source document,
   a real rail response, or a deterministic validator — never to model judgement alone. A
   `ComplianceVerdict` with no cited rule is invalid by construction. A `LiquidityProposal` naming
   a rail that wasn't in its input is rejected. **This is Non-negotiable I.**
   It applies to the project's own claims as much as to its outputs: we build against the public
   ISO 20022 base catalogue and say so, rather than implying SARB PEM conformance we cannot
   demonstrate ([docs/design/iso20022-messaging.md](docs/design/iso20022-messaging.md) §3.6).
2. **The model suggests; deterministic code decides.** No LLM output permits a settlement, passes a
   schema, or overrides a guardrail. Every permit/forbid edge in
   [docs/design/asco-orchestrator.md](docs/design/asco-orchestrator.md) §3 is hard-coded.
3. **Budgets are hard.** Agent negotiation ≤ 3 exchanges; end-to-end decision inside the RTGS SLA
   window; both models resident on one MI300X node. Exceeding a budget escalates to a human — it
   never degrades into a best-effort settlement.
4. **Fail closed.** Inference timeout, malformed agent output, unavailable audit log, unreconciled
   statement: every one of these refuses or escalates. Nothing defaults to allow.
5. **Test-first.** Each user story writes failing tests before implementation.
6. **Design before code, and no placeholders.** Non-trivial lanes have a merged design doc in
   [docs/design/](docs/design/) with the diagrams implementation is checked against; nothing ships
   with a `TODO`, a stub body, or hard-coded stand-in data. Can't build the real thing → the task is
   blocked, not done. (AGENTS.md §2a · docs/design-documentation.md.)
7. **Phased delivery.** Independent user stories; each phase ends demoable.
8. **Coordinate through shared state.** STATUS.md, AGENTS.md and TASKS.md are the only coordination
   surfaces; one writer per task. **These files are deliberately untracked** — they live on the
   maintainer's machine, not in this public repo. See docs/project-structure.md § Untracked process
   files. Nothing in the build depends on them.
9. **Branch-only, always-green `main`.** No direct pushes; every change lands via PR with a green
   gate. Enforced server-side since 2026-08-07: `main` is protected, the `gate` check is required,
   and admins are not exempt.

---

## Technical Context

> **Versions below were verified against their release pages on 2026-08-06** and are pinned exactly
> in `pyproject.toml` / `uv.lock` / `docker-compose.yml` (architecture-defaults §5). Don't bump one
> from memory — re-verify. The web client pins nothing because it has no dependencies to pin: it is
> static HTML.

| Dimension | Value |
| --- | --- |
| **Language(s) + versions** | **Python 3.13.14**, pinned in `.python-version` + `uv.lock`. Confirmed compatible with vLLM 0.26.0, whose `requires-python` is `>=3.10,<3.15`. 3.14.7 is the newer line, but the locked stack is 3.13 and swapping it needs a plan change. Toolchain: uv, ruff 0.16.1, pytest 9.1.1. The web client has no language runtime — it is static HTML |
| **Architecture** | Microservices — one service per bounded context, Domain-Driven Design; financial-routing logic decoupled from LLM-inference logic so models can be swapped without touching banking rules |
| **Messaging / async** | **Kafka 4.3.1** (`apache/kafka:4.3.1`, KRaft — no ZooKeeper) — chosen over RabbitMQ specifically because the SARB PEM audit trail needs retention and replay, which is Kafka's shape, not a work queue's (architecture-defaults §2) |
| **Frontend** | **Static HTML, no framework, no build step** — the approved Stitch export in `apps/web/`, served as-is. **Deviation from architecture-defaults §3 (shadcn/ui)**: a React port was built and reverted on 2026-07-27 for not matching the mockups; reasoning and the lesson are in [docs/design/frontend-web.md](docs/design/frontend-web.md) §8 |
| **Containerization** | Docker per service + one `docker-compose.yml` for local dev (Kafka + Postgres + the services). The web client is static files behind a plain file server — no build, no runtime container |
| **Runtime/deploy target** | AMD AI Developer Cloud — MI300X instance, ROCm 7.0, vLLM. Sovereign/on-prem deployment is the product requirement, not an option |
| **Data layer** | **Postgres 18.4** (`postgres:18.4-trixie`), one per service where a service owns state; the audit store is append-only (no UPDATE/DELETE grant) |
| **Key external services/models** | Two open-weight models co-resident on one MI300X: 70B-class (Compliance Sentinel), 32B-class (Liquidity Strategist). Rails: Ripple, SWIFT, PAPSS. **No third-party LLM API, ever** |
| **Testing** | pytest (services) · a determinism harness that replays a transfer 50× and asserts an identical rail and outcome. The web client's test is visual: each page beside its PNG in `legacy/stitch-mockups/` |
| **Perf/cost goals** | Avg settlement ≈ 3 s on the Ripple corridor; agent negotiation ≤ 3 exchanges; FP8 quantisation adopted **only** after measuring reasoning degradation, never assumed |
| **Constraints** | SARB PEM (absolute traceability, RTGS, pre-execution KYC/AML) · FATF Travel Rule · **ISO 20022 base-catalogue conformance — NOT SARB Usage Guidelines (§3.6)** · data residency |
| **Scale** | Institutional throughput on the order of the console's $1.4M/hr figure; one deploying institution in v1 |

---

## Project structure (as scaffolded)

Full write-up: [docs/project-structure.md](docs/project-structure.md).

```
UbuntuRemit/
├── SPEC.md · PLAN.md                         the WHAT and the HOW
├── docs/
│   ├── design/                               THE DIAGRAMS — build to these
│   ├── reference/                            the three ASCO source PDFs
│   └── project-structure.md                  the actual layout
├── scripts/gate.sh · install-hooks.sh        the one gate, and its installer
├── apps/web/                                 static HTML client — the Stitch export, served as-is
├── legacy/stitch-mockups/                    frozen visual reference (do not edit)
├── pyproject.toml · uv.lock                  uv workspace root — pinned toolchain, lint + test config
├── .python-version                           3.13.14, exact
├── .github/workflows/ci.yml                  the gate, mirroring .githooks/pre-push
├── services/                                 gateway · asco · inference · messaging · rails · audit (none built)
└── docker-compose.yml                        Kafka + Postgres for local dev and integration tests
```

---

## Design documents

The diagrams implementation is built and reviewed against. One per non-trivial lane, merged before
that lane's implementation tasks are written — see
docs/design-documentation.md.

| Lane | Design doc | Covers |
| --- | --- | --- |
| `domain` | [docs/design/domain-model.md](docs/design/domain-model.md) | Class diagram, settlement state machine, invariants |
| `asco` | [docs/design/asco-orchestrator.md](docs/design/asco-orchestrator.md) | Negotiation sequence, guardrail components, agent JSON contracts |
| `iso20022` | [docs/design/iso20022-messaging.md](docs/design/iso20022-messaging.md) | pain.001/pacs.008/camt.053 field mapping, validation gates |
| `frontend-web` | [docs/design/frontend-web.md](docs/design/frontend-web.md) | Component tree, tokens, visual references, deviations |

---

## Build phases (MVP-first)

Mirrors TASKS.md. Each phase is independently demoable at its checkpoint.

0. **Design** — domain model + one design doc per lane. ✅ done.
1. **Setup** — repo scaffold, web app, CI, hooks. 🔄 in progress.
2. **Foundational** — schema governance first (the verification pipeline, which needs no version
   numbers to build), then the ISO 20022 message layer. Nothing negotiates until a pain.001 can be
   parsed and a pacs.008 emitted.
3. **US2** — the ASCO negotiation loop with both guardrail sets, against stub rail quotes.
4. **US3/US4** — real rail adapters, the audit pipeline, camt.053 reconciliation.
5. **US1/US5** — wire the web client to real endpoints; the remaining wizard steps and the
   escalation queue.
6. **Hardening** — determinism harness, FP8 measurement, latency against the RTGS window.
7. **Polish** — docs, placeholder sweep, release.

---

## Testing gate

- **Test-first:** every story phase writes failing tests before implementation.
- **Gate:** the [pre-push hook](.githooks/pre-push) runs lint + the fast suite; CI re-runs it plus
  anything too slow for local — the determinism harness, integration tests against a real Kafka via
  `docker-compose`, and rail smoke tests.
- **The two tests that define this project:** the determinism replay (same input → same rail), and
  the guardrail-bypass suite (a crafted uncited verdict or fabricated rail must be *rejected*, not
  passed through).

See docs/testing-strategy.md.
