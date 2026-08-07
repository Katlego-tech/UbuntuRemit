# `UbuntuRemit` — STATUS

> Source of truth for "what's going on right now." Read first, update last. Treat updating it as
> part of "done."

_Last updated: 2026-08-07 — by Kirito (via Claude)_

---

## ⇄ HANDOFF: **none**

> Leave this block here even when dormant — it is the first thing every AI reads, and it only
> works as a signal if it always lives in the same spot. Set it to `ACTIVE` and fill the rows
> when handing work to another AI or another session. See
> [docs/cross-ai-protocol.md](docs/cross-ai-protocol.md) § Handoffs.

| Field | Value |
|---|---|
| Status | 🟢 **none** |
| Raised | — |
| Reason | — |
| Document | — |
| Branch | — |
| Resume at | — |
| Blocking | — |

---

## 🎯 Current focus (claim your lane here)

| Lane | Owner | AI | Status |
|------|-------|----|--------|
| `design` | Kirito | Claude | ✅ done — all four design docs merged |
| `frontend-web` | Kirito | Claude | 🔄 6 pages ship; the 3 composed wizard steps await visual sign-off (T027) |
| `messaging` | — | — | 🟢 unclaimed and **fully unblocked** — T028–T032 all ready to start |
| `asco` | — | — | ⬜ unclaimed, blocked on Phase 3 |
| `infra` | Kirito | Claude | 🔄 PR #1 — toolchain, compose and CI all verified green; **T016 (branch protection) needs Kirito**, then the lane is done |

**Frontend lanes are Claude's by default** (AGENTS.md §1). Gemini: `messaging` and `asco` are the
lanes with the most drawn structure waiting for you — start at
[docs/design/iso20022-messaging.md](docs/design/iso20022-messaging.md).

## ⏭️ Next action

1. **T027 — walk the send-money flow and look at it.** Steps 1, 3 and 4 were composed on
   2026-07-28 with no PNG to check against, by a session that couldn't see its own output. Serve
   `apps/web`, click 1 → 2 → 3 → 4 and back. This is the shortest task on the board and the one
   holding up the most.
2. **T024 — self-host the frontend's external dependencies.** The pages currently pull Tailwind
   from `cdn.tailwindcss.com` (which compiles CSS *in the browser*), fonts from Google, and the
   avatar from `googleusercontent.com`. For a product whose premise is data sovereignty, three
   third-party requests per settlement screen is a real defect, not a nitpick. Must have zero
   visual effect — verify against the PNGs.
3. **T016 — turn on branch protection for `main`.** Needs Kirito; it's a repo setting, not code.
   Require the check named **`gate`** (one job, not the three the workflow had before T018).
   Until it's *required* server-side, the gate is opt-in and one `--no-verify` away from being
   skipped — which is the only remaining hole in "main is always green".
4. **T028–T030 — build the schema-verification pipeline.** This is now the highest-value
   unblocked work: it needs no version numbers to build, and it is what makes the versions safe to
   adopt whenever the MyStandards export arrives. Design is complete in
   `docs/design/iso20022-messaging.md` §3.4.
5. **T031/T032 — vendor the base-catalogue schemas and state the conformance boundary.** Versions
   are extracted from each XSD's own `targetNamespace` at download, never hand-typed.

## 🗓️ Timeline to `TBD`

| Phase | What | Target window | Status |
|-------|------|---------------|--------|
| Phase 0 | Design docs — the diagrams everything is built to | — | ✅ |
| Phase 1 | Setup: scaffold, pages served, hooks, CI | — | 🔄 CI green; T016 (branch protection) + T009 (markup parse) outstanding |
| Phase 2 | Frontend — the approved export ships | — | 🔄 self-hosting (T024) + endpoints (T025) pending |
| Phase 3 | ISO 20022 message layer (blocking) | — | ⬜ |
| Phase 4 | ASCO negotiation + guardrails | — | ⬜ |
| Phase 5 | Audit pipeline + rail adapters | — | ⬜ |
| Phase 6 | Hardening: determinism, FP8, latency | — | ⬜ |
| Phase 7 | Polish | — | ⬜ |

## 🧱 What's built so far

- **Process scaffold** from the Cultivation kit, realigned to the 2026-08-06 kit revision (T018):
  AGENTS/SPEC/PLAN/TASKS/STATUS, `docs/` (now incl. `code-analysis`, `iteration-rituals`,
  `security-basics`), `.claude/` agents + `/feature-dev`, and the rebuilt gate —
  `scripts/gate.sh` run by both `.githooks/pre-push` and CI, installed with `bash install-hooks.sh`.
- **Four design docs** in `docs/design/` — domain model (class diagram + state machine), ASCO
  orchestrator (sequence + component + agent JSON contracts), ISO 20022 mapping, frontend.
- **`apps/web`** — six pages of static HTML, no build step.
  - **Exported (PNG-backed):** `send-money.html` (wizard step 2), `compliance.html`, `wallet.html`.
    Unchanged from the Stitch export apart from link wiring.
  - **Composed (no PNG):** `send-amount.html`, `send-compliance.html`, `send-review.html` — the
    three wizard steps that were never exported, built 2026-07-28 from the design system and the
    exported pages' vocabulary. Chrome copied byte-for-byte from step 2 by script and verified
    identical. **Not yet visually signed off (T027).**
- **`legacy/stitch-mockups/`** — the frozen visual reference, with a README on why it's kept.
- **`docs/reference/`** — the three ASCO PDFs.
- **Code skeleton** — uv workspace (`pyproject.toml`, `uv.lock`, `.python-version`),
  `docker-compose.yml` (Kafka + Postgres, both verified healthy), and one gate in
  `scripts/gate.sh` run by both the pre-push hook and CI — green in both, 5 checks.
  **`services/` is still empty** — see the 2026-08-06 Log entry for why.

## 🛠️ Environment & access

- Web client: `python3 -m http.server 5173 --directory apps/web`. No install, no build, no
  dependencies. Its test is visual — each page beside its PNG in `legacy/stitch-mockups/`.
- Gate: `bash install-hooks.sh` once per clone, then `bash scripts/gate.sh` any time. It prints how
  many checks it ran — **zero checks is a failure, not a pass.**
- Python toolchain: `uv sync --frozen` (Python 3.13.14, ruff 0.16.1, pytest 9.1.1 — all locked).
- Kafka + Postgres: `docker compose up -d`. Kafka on `localhost:29092`, Postgres on
  **`localhost:55432`** (not 5432 — FrameFlow's db holds the default on this machine).
- **Not yet provisioned:** the MI300X instance, any rail sandbox credentials.
- Remote is `git@github.com:Katlego-tech/UbuntuRemit.git`. **Branch protection on `main` is still
  off** (T016) — right now only the local, bypassable hook stands between anyone and a direct push.

## ⚠️ Open decisions / risks

- **DECIDED 2026-07-27 — we are not SARB PEM-conformant, and we say so.** SARB's Usage Guidelines
  live on SWIFT MyStandards behind participant standing this project does not have. Rather than
  block the message layer indefinitely, or adopt the reference paper's *illustrative* version table
  as if it were authoritative (the Non-negotiable I violation the blocker existed to prevent), we
  build against the **public ISO 20022 base catalogue** and state the boundary in SPEC.md, README.md
  and `iso20022-messaging.md` §3.6. `schema-policy.yaml` carries it as data (`conformance.claim`,
  `source` per context) and a build check enforces it. **This is a stated boundary, not a gap** —
  don't "fix" it by quietly upgrading the claim.
- **Consequence:** the structural-equivalence check (§3.3) is inert — we're using the permissive
  base schema, so there's nothing constrained to compare against. The code stays and activates if
  an export ever arrives. Where a SARB narrowing is cheap and safe we take it anyway
  (`ChargeBearer` treated as mandatory); where it isn't, we don't invent one.
- **A correct suffix is necessary but NOT sufficient.** A vendor file named `pacs.008.001.08.xsd`
  with the right namespace can still carry the permissive *base* ISO constraints rather than the
  SARB-constrained subset (e.g. `ChargeBearer` `[0..1]` vs `[1..1]`). It compiles, runs, and is
  rejected at the SARB gateway. Verification must assert structural equivalence.
- **The BAH was missing from our design.** Every message is enveloped by a Business Application
  Header (`head.001.001.xx`), itself version-governed and pulled in via `xs:import`. `domain-model.md`
  §3 now carries it on `SettlementInstruction`; which header and which version is open (T033).
- **UG2026 lands November 2026** for SADC-RTGS — within months. An argument for versions as
  refreshed data, never literals in source.
- **Wizard steps 1/3/4 are built but unverified.** The project leader authorised expanding the UI
  on 2026-07-27, which is what unblocked T021 — the earlier "stop and say so" rule wasn't wrong,
  it was waiting on exactly that authorisation. They have no PNG, so `send-money.html` and
  `compliance.html` are the reference, and **T027 (a human looking at them) is outstanding.**
- **Dashboard still has no reference and is still not built** (T022). Its nav link stays dead
  rather than pointing at an invented page. Same authorisation applies; nobody has started it.
- **The frontend pages carry static mockup figures** (T025 replaces them). This is the one
  sanctioned exception to the no-placeholder rule, and it's honest: nothing on those pages claims
  to be a live rate, balance, or verdict.
- **Three third-party runtime dependencies** on every page — Tailwind CDN, Google Fonts, a
  hot-linked avatar (T024). The Tailwind one compiles CSS in the browser and is not a production
  mechanism.
- **Accessibility of the export is unassessed** (T026): no focus-visible styling, unlabelled
  decorative icons, a colour-only settlement chart with no table view.
- **Deviation from architecture-defaults §3 (shadcn/ui):** no component framework at all. The
  export is the approved design; see `docs/design/frontend-web.md` §8.
- FP8/FP4 quantisation is a *hypothesis* for hitting the RTGS window, not a decision — T061
  measures it before anyone commits.

## 🗒️ Log

- 2026-08-07 — Kirito (via Claude) — **T008 green.** CI ran for the first time once the GitHub
  Actions outage cleared: `== gate passed (5 check(s) run across 1 project(s)) ==` on PR #1 — the
  same count `scripts/gate.sh` reports locally, so it passed because it ran, not because it found
  nothing to do. ruff check, ruff format, pytest, the `apps/web` link check, the placeholder sweep
  and the secret sweep all executed against ruff 0.16.1 + pytest 9.1.1 resolved from `uv.lock`.
  T008's `Done` used to include "required on `main`", which is a repo setting rather than anything
  this task can deliver; that half now lives solely in **T016**, so neither task can hide behind
  the other. T016 must require the check named **`gate`** — one job, not the three the workflow had
  before T018.

- 2026-08-06 — Kirito (via Claude) — **Realigned to the new Cultivation kit (T018).** The kit was
  rebuilt the same day around one idea: *a check that did not run is a failed check.* Every check now
  lives in `scripts/gate.sh`, which both the pre-push hook and CI run, so the two cannot drift; the
  hook is reduced to branch policy plus working out the change set. Adopted wholesale, plus the
  three new process docs (`code-analysis`, `iteration-rituals`, `security-basics`) and refreshed
  `testing-strategy` / `architecture-defaults` / `git-workflow`. Two deliberate local deviations:
  the `apps/web` link check was folded **into** `gate.sh` rather than left in the hook (the kit has
  no equivalent, and T009 would otherwise have been lost), and CI keeps this repo's exact,
  verified action pins instead of the kit's floating `@v4`/`@v5` majors, with the Node steps
  dropped because nothing here uses Node. New in the gate for free: a **secret sweep**. Verified by
  exit code on four paths — clean tree → 0, broken `href` → 1, `NotImplementedError` → 1,
  AWS-shaped key → 1.
- 2026-08-06 — Kirito (via Claude) — **Code skeleton (T014, T015; T008 written but unproven).**
  uv workspace pinning
  Python 3.13.14 + ruff 0.16.1 + pytest 9.1.1; `docker-compose.yml` with Kafka 4.3.1 (KRaft) and
  Postgres 18.4, both verified healthy from cold; CI mirroring the pre-push hook. Every version was
  read off a release page or registry today, not recalled. Three things worth knowing:
  **(a)** `services/` is still empty on purpose — six directories holding an `__init__.py` is the
  "empty component" §2a forbids, and placing the shared entities first needs the open question now
  recorded in `domain-model.md` §9 (T017). **(b)** Two real defects fixed in `.githooks/pre-push`:
  the placeholder sweep read `git diff --cached`, which is *always empty* at pre-push time, so it
  had never scanned anything; and the Python gate probed an ambient `pytest` instead of the pinned
  one. **(c)** `domain-model.md` §5–6 named `services/ledger|compliance|liquidity`, a topology no
  other document uses — reconciled in its own commit before any code was written. LICENSE removed
  at Kirito's request; README now states all-rights-reserved.
- 2026-07-28 — Kirito (via Claude) — Built wizard steps 1, 3 and 4 (`send-amount`,
  `send-compliance`, `send-review`) on the leader's authorisation to expand the UI. Design first
  (`docs/design/send-money-wizard.md`), then generation: chrome spliced byte-for-byte from step 2
  by script rather than re-typed, so the three pages cannot drift from it. No new component,
  colour or spacing value invented. Step 3 renders the ASCO negotiation agent-by-agent with cited
  rules as a first-class element — the product claim is explicability, and a spinner explains
  nothing. **Stated before delivery this time: these are visually unverified (T027).**
- 2026-07-27 — Kirito (via Claude) — Bootstrapped the repo from the Cultivation kit. Froze the
  Stitch export into `legacy/`, moved the three ASCO PDFs into `docs/reference/`.
- 2026-07-27 — Kirito (via Claude) — Wrote the four design docs in `docs/design/` before any
  application code, per the amended process (AGENTS.md §2a).
- 2026-07-27 — Kirito (via Claude) — Built `apps/web` as a React 19 / Vite / Tailwind v4 port of
  the three screens.
- 2026-07-27 — Kirito (via Claude) — **Reverted that port and deleted it.** It did not look like
  the mockups. `apps/web` is now the Stitch export served as-is, with only the nav `href`s wired.
  The lesson is written into `docs/design/frontend-web.md` §8 rather than only fixed in passing:
  a port is a *fidelity* task, its acceptance criterion is "indistinguishable from the PNG", and a
  session with no way to see its own output should have treated that task as blocked rather than
  reporting it done with the visual check deferred.
- 2026-07-27 — Kirito (via Claude) — **Closed the MyStandards path deliberately.** Kirito chose the
  public base-catalogue route: build real schemas and a real pipeline, and state plainly that this
  is not SARB conformance. T031 is no longer blocked — it's now "vendor from iso20022.org with
  provenance", and T032 threads the boundary through SPEC/README/design docs with a build check so
  it can't erode. The whole `messaging` lane is unblocked.
- 2026-07-27 — Kirito (via Claude) — Parsed `docs/reference/SARB ISO 20022 Suffix Verification.pdf`.
  It did **not** confirm the version suffixes — it established that there is nothing to confirm
  statically: SARB's authority is a MyStandards portal export, and the paper's own version table is
  illustrative. Restructured `iso20022-messaging.md` around schema governance (new §3), split
  validation into schema-admission vs. runtime (§6), added the BAH to `domain-model.md`, and
  reordered Phase 3 so the verification pipeline (T028–T030, unblocked) is built before any schema
  is vendored. T031 is now the single blocker and it is an access request, not research.
- 2026-07-27 — Kirito (via Claude) — Amended the Cultivation kit itself (design-documentation
  doctrine, contract-shaped tasks, no-placeholder rules in AGENTS §2a and every entry point) and
  bootstrapped this repo from the amended version.
