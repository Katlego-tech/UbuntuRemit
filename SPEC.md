# `UbuntuRemit` — Specification (the WHAT)

**Related:** [PLAN.md](PLAN.md) (the HOW) · [docs/design/](docs/design/) (the shapes) ·
[TASKS.md](TASKS.md) (the backlog)

---

## Overview

UbuntuRemit is a cross-border remittance platform for African corridors whose intelligence layer is
**ASCO — the Agentic Settlement & Compliance Orchestrator**. Where a conventional platform routes
payments with static rules, ASCO has three purpose-built agents negotiate each transaction: a
**Compliance Sentinel** that enforces AML/CFT and SARB rules, a **Liquidity Strategist** that finds
the cheapest and fastest rail across Ripple, SWIFT and PAPSS, and a **Master Orchestrator** that
holds state and emits the ISO 20022 payload. Deterministic, hard-coded guardrails sit on both sides
of that negotiation: the agents suggest, the validators decide.

Two kinds of actor call it — a **remitter** using the web client, and an **institutional operator**
watching the compliance console. It produces a settled payment, an ISO 20022 message trail
(pain.001 → pacs.008 → camt.053), and an append-only audit log that explains *why* every routing
decision was made.

### Goals

- Execute cross-border settlements with **zero regulatory violations** under SARB and FATF rules.
- Make every routing decision **auditable** — a structured Thought-Action-Observation record per
  agent turn, tied to the transfer, retained and replayable.
- Route for **capital efficiency**: lowest total cost within the compliance envelope, inside the
  RTGS SLA window.
- Run entirely on **sovereign infrastructure** (AMD MI300X + ROCm 7.0 + vLLM), so no transaction
  data reaches a third-party LLM API.
- Give remitters a transfer experience where compliance is **visible and explained**, not a
  black-box delay.

### Non-goals

- **Not** a wallet, a card product, a crypto exchange, or an FX speculation tool.
- **Not** a general-purpose agent framework — ASCO is domain-bound to settlement.
- **Not** multi-tenant SaaS in v1: one deploying institution, one data-residency boundary.
- **Not** a replacement for the core banking ledger; camt.053 reconciles *back* to it.
- **No** corridors beyond those explicitly configured. An unsupported corridor is a rejection, not
  a best-effort attempt.
- **Not SARB PEM-conformant, and does not claim to be.** Messages are built against the **public
  ISO 20022 base catalogue**. SARB's Usage Guidelines are published as enforceable schemas through
  SWIFT MyStandards and require participant standing this project does not have, so the constrained
  subset SARB actually enforces is unavailable to us. The design targets SAMOS and SADC-RTGS; the
  implementation is not validated against either. See
  [docs/design/iso20022-messaging.md](docs/design/iso20022-messaging.md) §3.6 — this is a stated
  boundary, not a temporary gap.

---

## Actors

### The remitter (web client)

Sends money from a funded ZAR balance to a recipient in a supported corridor. Enters amount,
recipient details, and two SARB-mandated declarations (purpose of payment, source of funds). Judges
success by: a guaranteed rate that doesn't move under them, a visible settlement timeline, and a
transfer that lands in seconds rather than days.

### The institutional operator (compliance console)

Monitors engine health, watches the live validation stream, works the escalation queue. Judges
success by being able to answer an auditor's *"why did this payment route this way?"* from the
system itself, without reconstruction.

### The auditor / regulator (indirect)

Never touches the UI. Consumes the audit trail and the ISO 20022 messages. Judges success by whether
every decision traces to a cited rule — the standard the entire product claim rests on.

---

## User stories

### US1 — Initiate a compliant transfer (P1)

**As a** remitter, **I want** to enter a recipient and my regulatory declarations and see exactly
what they will receive, **so that** I can send money without a surprise fee, rate, or rejection.

**Acceptance criteria:**
- [ ] Selecting a destination corridor requotes the recipient total from a live interbank rate.
- [ ] Purpose of payment and source of funds come from closed, SARB-reportable taxonomies.
- [ ] The quoted rate is held for a stated window, and that window is shown — not implied.
- [ ] An unsupported corridor is refused with a reason, never partially attempted.
- [ ] Monetary values are exact to the minor unit end to end; no float in any layer.

### US2 — Negotiate the settlement (P1)

**As** the platform, **I want** the Compliance Sentinel and Liquidity Strategist to negotiate the
rail inside a compliance envelope, **so that** transfers settle cheaply without ever settling
illegally.

**Acceptance criteria:**
- [ ] Agents exchange only schema-validated JSON; a malformed response is re-asked once, then escalated.
- [ ] The Strategist may only select from rails supplied in its input — a fabricated rail is rejected.
- [ ] A verdict with empty `citedRules` is rejected by the exit validator, not passed through.
- [ ] Negotiation is bounded at 3 exchanges; on exhaustion the transfer escalates, never "best effort".
- [ ] Inference timeout produces an escalation, never an approval.
- [ ] The same transfer replayed against a pinned model and seed yields the same rail and outcome.

### US3 — Emit and validate ISO 20022 (P1)

**As** the platform, **I want** every message built and validated against the official schema,
**so that** the payment is accepted by the rail and reportable to SARB.

**Acceptance criteria:**
- [ ] pain.001 is the only entry format; nothing enters ASCO as loose JSON.
- [ ] Amounts serialise as decimal strings derived from minor units.
- [ ] Purpose maps to `ExternalPurpose1Code`; source of funds rides in `SplmtryData`, never `Purp`.
- [ ] `EndToEndId` reuse is a hard rejection.
- [ ] All three gates (XSD → field rules → business rules) run deterministically, with no model involved.

### US4 — Audit and reconcile (P1)

**As** an operator or auditor, **I want** every decision recorded and every settlement reconciled,
**so that** I can defend any individual payment.

**Acceptance criteria:**
- [ ] One append-only audit record per agent turn, carrying thought, action and observation.
- [ ] Every terminal transfer state has ≥ 1 audit record per participating actor.
- [ ] A transfer whose camt.053 entry doesn't match stays unreconciled and alerts — never
      auto-adjusted, never silently marked delivered.
- [ ] If the audit log is unavailable, the transfer is refused rather than settled unrecorded.

### US5 — Operate the compliance console (P2)

**As** an institutional operator, **I want** live engine health, settlement throughput and the
validation stream on one screen, **so that** I see degradation before a customer reports it.

**Acceptance criteria:**
- [ ] Engine module status, corridor node count and processing capacity render from live telemetry.
- [ ] The settlement chart is readable without colour vision and offers a table view.
- [ ] The escalation queue is reachable and shows why each transfer escalated.

---

## Acceptance criteria (system-level)

- [ ] **Zero uncited compliance verdicts**, in any environment, at any time.
- [ ] **No artifact claims regulatory conformance the project cannot demonstrate.** No document,
      code comment, log line or UI string implies SARB PEM conformance while the `samos` /
      `sadc_rtgs` contexts in `schema-policy.yaml` are empty. Enforced by a build check, not by
      good intentions — the product claim is auditability, and overclaiming defeats it first.
- [ ] **No fabricated data reaches a user or a message**: rates, rails, fees and verdicts trace to a
      real source, a real rail response, or a deterministic validator. (Non-negotiable I.)
- [ ] **`main` is always green** — branch-only, PR-gated, CI-enforced.
- [ ] **No placeholders in shipped code** — no `TODO`, stub body, or hard-coded stand-in data.
      The web client's static mockup figures are the one declared exception (T025 replaces them),
      and nothing on those pages is presented as a live rate, balance, or verdict.
- [ ] **Every non-trivial lane has a merged design doc** in `docs/design/` before its
      implementation tasks are written.
- [ ] No transaction data leaves the deploying institution's infrastructure.
