# `UbuntuRemit` — STATUS

> Source of truth for "what's going on right now." Read first, update last. Treat updating it as
> part of "done."

_Last updated: 2026-07-27 — by Kirito (via Claude)_

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
| `frontend-web` | Kirito | Claude | ✅ the Stitch export ships as-is from `apps/web/` — approved |
| `messaging` | — | — | 🟡 unclaimed — T030 is **blocked** (see Open decisions) |
| `asco` | — | — | ⬜ unclaimed, blocked on Phase 3 |
| `infra` | — | — | ⬜ unclaimed — T008 (CI) is the next thing anyone can pick up |

**Frontend lanes are Claude's by default** (AGENTS.md §1). Gemini: `messaging` and `asco` are the
lanes with the most drawn structure waiting for you — start at
[docs/design/iso20022-messaging.md](docs/design/iso20022-messaging.md).

## ⏭️ Next action

1. **T024 — self-host the frontend's external dependencies.** The pages currently pull Tailwind
   from `cdn.tailwindcss.com` (which compiles CSS *in the browser*), fonts from Google, and the
   avatar from `googleusercontent.com`. For a product whose premise is data sovereignty, three
   third-party requests per settlement screen is a real defect, not a nitpick. Must have zero
   visual effect — verify against the PNGs.
2. **T008 — CI workflow.** The pre-push hook exists and is wired; CI does not.
3. **Unblock T030** by confirming the ISO 20022 version suffixes against the SARB PEM guide.

## 🗓️ Timeline to `TBD`

| Phase | What | Target window | Status |
|-------|------|---------------|--------|
| Phase 0 | Design docs — the diagrams everything is built to | — | ✅ |
| Phase 1 | Setup: scaffold, pages served, hooks, CI | — | 🔄 CI outstanding |
| Phase 2 | Frontend — the approved export ships | — | 🔄 self-hosting (T024) + endpoints (T025) pending |
| Phase 3 | ISO 20022 message layer (blocking) | — | ⬜ |
| Phase 4 | ASCO negotiation + guardrails | — | ⬜ |
| Phase 5 | Audit pipeline + rail adapters | — | ⬜ |
| Phase 6 | Hardening: determinism, FP8, latency | — | ⬜ |
| Phase 7 | Polish | — | ⬜ |

## 🧱 What's built so far

- **Process scaffold** from the Cultivation kit: AGENTS/SPEC/PLAN/TASKS/STATUS, `docs/`,
  `.claude/` agents + `/feature-dev`, `.githooks/pre-push` with `core.hooksPath` set.
- **Four design docs** in `docs/design/` — domain model (class diagram + state machine), ASCO
  orchestrator (sequence + component + agent JSON contracts), ISO 20022 mapping, frontend.
- **`apps/web`** — the approved Stitch export, served as static HTML. Three pages plus an
  `index.html` redirect; nine `href`s wired between them and nothing else changed.
- **`legacy/stitch-mockups/`** — the frozen visual reference, with a README on why it's kept.
- **`docs/reference/`** — the three ASCO PDFs.

## 🛠️ Environment & access

- Web client: `python3 -m http.server 5173 --directory apps/web`. No install, no build, no
  dependencies. Its test is visual — each page beside its PNG in `legacy/stitch-mockups/`.
- **Not yet provisioned:** the MI300X instance, Kafka, Postgres, any rail sandbox credentials.
- No remote configured yet — `git remote add origin <url>` is still outstanding.

## ⚠️ Open decisions / risks

- **T030 is blocked:** the Feasibility Paper names the ISO 20022 message *types* but not their
  version suffixes. `pain.001.001.09` / `pacs.008.001.08` / `camt.053.001.08` are this design's
  targets and **must be confirmed against the SARB PEM implementation guide** before anything is
  submitted. Guessing a version is a Non-negotiable I violation.
- **Four screens have no visual reference** — wizard steps 1/3/4 and Dashboard. They are
  deliberately not implemented, and their nav links stay dead rather than pointing at an invented
  page. Designing them is T021/T022. Do not "just build" them from the step-2 page by analogy.
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
- 2026-07-27 — Kirito (via Claude) — Amended the Cultivation kit itself (design-documentation
  doctrine, contract-shaped tasks, no-placeholder rules in AGENTS §2a and every entry point) and
  bootstrapped this repo from the amended version.
