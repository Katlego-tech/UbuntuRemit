# `UbuntuRemit` — Tasks

**Plan:** [PLAN.md](PLAN.md) · **Spec:** [SPEC.md](SPEC.md) · **Designs:** [docs/design/](docs/design/)

> One of the three shared-state files (with [AGENTS.md](AGENTS.md) and [STATUS.md](STATUS.md)).
> **One writer per task** — claim it in STATUS.md before you start.

---

## How tasks are written here

A task is a **contract**, not a reminder. The person writing it and the person (or AI) building it
are usually not the same, and the builder will implement *exactly* what the task specifies — so a
task that under-specifies gets you something plausible-looking and wrong: the right file with a
`TODO` in it, a component that renders *a* screen rather than *the* screen, a function with the
agreed name and a stubbed body.

**The task is under-specified if a competent implementer who read nothing else could build
something structurally different from what you intend.** When that's true, the fix is not a longer
sentence — it's a design doc ([docs/design-documentation.md](docs/design-documentation.md)) and a
reference to it.

### Anatomy

```
- [ ] T0nn [P] [US1] <imperative one-line summary>
      Design:  docs/design/<lane>.md §<section>        <- the structure to build to
      Files:   <paths this task creates or changes>
      Contract:<exact signature / schema / props — or the design §ref that has it>
      Verify:  <the command or check that proves it works>
      Done:    <the observable end state, in the user's or caller's terms>
```

| Field | Required when | Why it's there |
| --- | --- | --- |
| **Design** | the task creates structure (types, services, screens, flows) | gives the implementer a diagram to build to instead of a guess |
| **Files** | always, unless genuinely unknowable | stops two lanes colliding; makes "did it touch the right thing" reviewable |
| **Contract** | anything another lane or task consumes | lets parallel lanes compose instead of each inventing an interface |
| **Verify** | always | a task with no check is a task nobody can close honestly |
| **Done** | always | phrased as an outcome, so "the file exists" can't pass for "it works" |

### Rules

1. **No placeholder deliverables.** A task may not be closed with `TODO`, `FIXME`, `pass`,
   `NotImplementedError`, an empty component, hard-coded fake data standing in for a real call, or
   a function that returns a constant to make a test green. If the real thing can't be built yet,
   the task is **blocked**, not done — say so in STATUS.md and name what unblocks it.
   *The one exception:* a deliberately stubbed dependency that the task text names as a stub, with
   a follow-up task ID already written for replacing it.
2. **Every task is a vertical slice.** "Create the module skeleton" is not a task; "parse a
   pain.001 payload into a `Transfer` and reject a malformed one" is. Scaffolding is part of the
   first behavioural task, not a task of its own.
3. **Sized to one sitting.** If a task can't be finished and verified in one working session,
   split it. Long tasks are where placeholders come from — the implementer runs out of room and
   leaves a marker.
4. **Tests first, and the test must fail for the right reason.** A test that passes against an
   empty implementation is not a test. Write it, watch it fail, then implement.
5. **UI tasks name their visual reference by path.** Never "build the dashboard" — always "build
   the dashboard in `<path>/screen.png`, matching layout, tokens and copy". See
   [docs/design-documentation.md](docs/design-documentation.md) § UI is a special case.
6. **One story label per task.** If a task serves two user stories, it's two tasks.
7. **`[P]` means genuinely parallel** — disjoint files *and* no unmet dependency. If two `[P]`
   siblings both touch the same file, one of them is mislabelled.

### Good vs. bad

> ❌ `- [ ] T014 [US2] Build the compliance dashboard`
>
> Produces: *a* dashboard. Some cards, some invented metrics, a chart library nobody chose.
>
> ✅
> ```
> - [ ] T0xx [US5] Populate the Compliance Health Dashboard from the health endpoint
>       Design:  docs/design/frontend-web.md §4 (data flow), §2 (visual reference)
>       Files:   apps/web/compliance.html
>       Contract:GET /api/compliance/health -> ComplianceHealth (asco-orchestrator.md §5)
>       Verify:  serve apps/web, open compliance.html BESIDE
>                legacy/stitch-mockups/compliance_dashboard/screen.png — pixel-identical except
>                the six values that now come from the endpoint
>       Done:    all six modules read live values; no static metric remains in the markup; the
>                page still matches the PNG
> ```
>
> The ✅ version is longer, and that is the point — the ❌ version is satisfiable by anything
> dashboard-shaped, and something dashboard-shaped is what you will get.

---

## Legend

Format: `[ID] [P?] [Story] Description`

- **[ID]** — task identifier `Tnnn`, monotonically increasing, never reused.
- **[P]** — parallelizable: touches different files from its siblings and has no unmet dependency.
- **[Story]** — the label the task serves (`US1`–`USn`, `SET` setup, `FND` foundational,
  `DSN` design/documentation, `POL` polish).
- Commit format: `feat(scope): Tnnn short description` (e.g. `feat(asco): T041 bind sentinel to the verdict schema`).

Each user-story phase is ordered **Design → Tests FIRST (must FAIL) → Implementation → Checkpoint**.


---

## Phase 0 — Design ✅

- [x] T001 [DSN] `docs/design/domain-model.md` — entities, invariants, settlement state machine.
- [x] T002 [P] [DSN] `docs/design/asco-orchestrator.md` — negotiation sequence, guardrail
      components, agent handshake JSON contracts.
- [x] T003 [P] [DSN] `docs/design/iso20022-messaging.md` — pain.001/pacs.008/camt.053 field
      mapping, the three validation gates.
- [x] T004 [P] [DSN] `docs/design/frontend-web.md` — component tree, token mapping, visual
      references by path, recorded deviations.

**Checkpoint:** ✅ every Phase 2+ lane has a merged design doc; `docs/design/README.md` indexes them.

---

## Phase 1 — Setup

- [x] T005 [SET] Bootstrap the repo from the Cultivation kit (AGENTS/STATUS/SPEC/PLAN/TASKS,
      `docs/`, `.claude/`, `.githooks/pre-push`, `core.hooksPath`).
- [x] T006 [SET] Freeze the Stitch export into `legacy/stitch-mockups/` with a README explaining
      that it is the visual reference, not code.
- [x] T007 [SET] Serve the approved Stitch export from `apps/web/` (`send-money.html`,
      `compliance.html`, `wallet.html`, plus an `index.html` redirect). Static files, no build step.
- [ ] T008 [SET] CI workflow re-running the pre-push gate.
      Files:    `.github/workflows/ci.yml`
      Verify:   a PR shows the check; a deliberately broken link turns it red
      Done:     CI is required on `main` and green on the scaffold
- [ ] T009 [P] [SET] Link-and-markup check for `apps/web` in the gate: every `href` resolves to a
      file that exists (or is a deliberate `#` per frontend-web.md §8), and the HTML parses.
      Files:    `.githooks/pre-push`, `.github/workflows/ci.yml`
      Verify:   breaking one `href` fails the gate
      Done:     runs in both the hook and CI

**Checkpoint:** the three pages serve, cross-link, and match their PNGs; CI green.

---

## Phase 2 — Frontend (US1, US5)

> **Read [docs/design/frontend-web.md](docs/design/frontend-web.md) §8 before touching this phase.**
> A React port of these three screens was built and reverted on 2026-07-27 for not matching the
> mockups. The export *is* the approved design. Do not re-express it in a framework, extract shared
> partials, or "tidy" the markup — every one of those is a chance to drift from the reference, and
> the reference is the only acceptance criterion this phase has.

- [x] T010 [US1] Send-money wizard step 2 — `apps/web/send-money.html`.
- [x] T011 [US5] Compliance health dashboard — `apps/web/compliance.html`.
- [x] T012 [US1] Wallet & history — `apps/web/wallet.html`.
- [x] T013 [US1] Wire the nav between the three pages; leave links with no page behind them dead.

- [ ] T024 [POL] Self-host the three external runtime dependencies.
      Design:   docs/design/frontend-web.md §3 (the `ext` subgraph), §8
      Files:    `apps/web/*.html`, `apps/web/assets/`
      Contract: no page issues a request to a host other than our own
      Verify:   load each page with devtools Network + offline after first load; **then open each
                one beside its PNG** — this change must have zero visual effect
      Done:     Tailwind is a built stylesheet not a CDN compiler, fonts and the avatar are local,
                and the pages are byte-for-byte identical in appearance
      Why:      `cdn.tailwindcss.com` compiles in the browser (not a production mechanism) and a
                sovereign-deployment product must not phone out to render a settlement screen

- [ ] T025 [US1/US5] Populate the pages from live endpoints, once Phase 3 lands.
      Design:   docs/design/frontend-web.md §4, §6 · domain-model.md §3
      Files:    `apps/web/*.html` (+ a small fetch script per page)
      Contract: `GET /api/session`, `/api/fx/quote`, `/api/compliance/health`, `/api/wallet`,
                `/api/transfers` — shapes in domain-model.md §3
      Verify:   each page beside its PNG, values now live; loading and error states defined
      Done:     no static figure remains that is presented as a rate, balance or verdict
      Note:     BLOCKED until Phase 3. Until then the static mockup values stay, and they are
                honest — nothing on these pages claims to be live.

- [ ] T026 [P] [POL] Accessibility audit of the export.
      Verify:   keyboard traversal, axe run, contrast check on the gold-on-light badges
      Done:     findings written up in frontend-web.md §10 with a fix task each — the export has
                no focus-visible styling, unlabelled decorative icons, and a colour-only chart

- [ ] T021 [US1] **Design** wizard steps 1 (Amount), 3 (Compliance) and 4 (Review).
      Design:   produces `docs/design/send-money-wizard.md` — there is currently NO visual
                reference for these three steps (frontend-web.md §10)
      Done:     a merged design doc with a named visual reference; only then may build tasks be
                written. Do not build these from the step-2 page by analogy.
- [ ] T022 [US5] **Design** the Dashboard screen — no Stitch export exists for it, and its nav
      link is deliberately dead rather than pointing at an invented page.
      Done:     merged design doc + visual reference; the build task is written afterwards

**Checkpoint:** the three pages serve with no external hosts and no static figure presented as live.

---

## Phase 3 — Foundational: the message layer (US3, blocking)

- [ ] T030 [FND] Vendor and pin the ISO 20022 XSDs.
      Design:   docs/design/iso20022-messaging.md §2
      Files:    `services/messaging/schemas/`
      Verify:   checksum test; the build fails if a schema file changes unreviewed
      Done:     **exact version suffixes confirmed against the SARB PEM guide**, not guessed
                (this task is BLOCKED on iso20022-messaging.md §9 question 1)
- [ ] T031 [FND] Failing tests for pain.001 round-tripping.
      Verify:   `pytest services/messaging` — fails because the builder doesn't exist
      Done:     one test per mapped field in iso20022-messaging.md §4
- [ ] T032 [FND] Build + parse pain.001, with the §4 mapping expressed as data, not branches.
      Contract: `build_pain001(Transfer) -> str`, `parse_pain001(str) -> Transfer`
      Verify:   `pytest services/messaging` green; XSD conformance on the golden message
      Done:     round-trip lossless for every mapped field; amounts are decimal strings from
                minor units, never floats
- [ ] T033 [P] [FND] pacs.008 builder, same shape.
- [ ] T034 [P] [FND] camt.053 parser + reconciliation against `Transfer.reference`.
      Done:     a one-minor-unit mismatch leaves the transfer unreconciled and raises — it does
                NOT mark it delivered
- [ ] T035 [FND] The three validation gates (XSD → field rules → business rules).
      Design:   docs/design/iso20022-messaging.md §5
      Verify:   one negative test per rejection reason, each asserting the *specific* rejection
      Done:     `EndToEndId` reuse is a hard rejection; no model participates in validation

**Checkpoint:** a pain.001 can be accepted, validated, and turned into a conformant pacs.008.

---

## Phase 4 — US2: the ASCO negotiation loop

- [ ] T040 [US2] Failing tests for the entry guardrail (schema, sanctions, limits).
      Done:     tests fail because the guardrail doesn't exist — not because they error
- [ ] T041 [US2] Entry guardrail. **No LLM is invoked** — a sanctions hit is never a matter of opinion.
      Design:   docs/design/asco-orchestrator.md §3, §4
- [ ] T042 [US2] Master Orchestrator as a deterministic state machine over
      `docs/design/domain-model.md` §4.
      Verify:   exhaustive test over `TransferState × TransferState` — every transition not in the
                diagram raises
      Done:     the orchestrator makes zero LLM calls of its own
- [ ] T043 [P] [US2] Compliance Sentinel: prompt + constrained decoding bound to the
      `ComplianceVerdict` schema.
      Contract: asco-orchestrator.md §5, verbatim
      Done:     an empty `citedRules` cannot be constructed; malformed output is re-asked once
                then escalates
- [ ] T044 [P] [US2] Liquidity Strategist, bound to the `LiquidityProposal` schema.
      Done:     a proposal naming a rail absent from `railQuotes` is rejected and audited with
                `deterministicOverride=true`
- [ ] T045 [US2] Exit validator — citation check, rail re-check, ISO 20022 validation.
      Verify:   the guardrail-bypass suite: a crafted `{"outcome":"PASS","citedRules":[]}` must be
                rejected, not passed through
- [ ] T046 [US2] Bound the negotiation at 3 exchanges; exhaustion escalates.
      Done:     no "best effort" path exists in the code
- [ ] T047 [US2] Fail-closed behaviours: inference timeout → ESCALATE, Kafka down → refuse.
      Verify:   fault-injection tests for each row of asco-orchestrator.md §4's failure table

**Checkpoint:** a transfer negotiates end to end against stub rail quotes and cannot be talked
into an uncited approval.

---

## Phase 5 — US4: audit & rails

- [ ] T050 [US4] Append-only audit store (no UPDATE/DELETE grant) consuming Kafka `asco.audit`.
- [ ] T051 [US4] `AuditRecord` emission on every agent turn and guardrail decision.
      Verify:   every terminal state has ≥ 1 record per participating actor
- [ ] T052 [P] [US4] Ripple rail adapter.
- [ ] T053 [P] [US4] PAPSS rail adapter.
- [ ] T054 [P] [US4] SWIFT rail adapter.
- [ ] T055 [US4] Bounded retry on `FAILED` — at most 2 alternate rails, per domain-model §4.

**Checkpoint:** a settlement completes on a real rail and reconciles from camt.053.

---

## Phase 6 — Hardening

- [ ] T060 [POL] Determinism harness: replay one transfer 50× against a pinned model + seed.
      Done:     identical `outcome` and `rail` every time; variance is a release blocker
- [ ] T061 [POL] Measure FP8 (and FP4) reasoning degradation before adopting either.
      Done:     a number in PLAN.md, not an assumption
- [ ] T062 [POL] Latency against the RTGS SLA window, under concurrent load.
- [ ] T063 [POL] `docker-compose.yml` — every service + Kafka + Postgres, so integration tests use
      a real broker rather than a mock.

---

## Phase 7 — Polish

- [ ] T070 [POL] Fill `docs/project-structure.md` with the real tree once `services/` exists.
- [ ] T071 [POL] Placeholder sweep: no `TODO`/`FIXME`/stub body/hard-coded sample data remains
      outside tasks that declared it, and each declared one has an open follow-up ID.
- [ ] T072 [POL] Close every open question in `docs/design/*.md` §10, or convert it to a task.
