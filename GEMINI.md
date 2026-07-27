# GEMINI.md — `Kirito`'s entry point (Gemini)

You are Gemini, working with **`Kirito`** on **`UbuntuRemit`**. This applies whether you are
the Gemini app, the Gemini CLI, or Antigravity — all read this file automatically. You may be working
alongside other AI copilots (see [AGENTS.md](AGENTS.md) §1); coordinate only through the shared-state
files.

## Before you do anything

Read, in this order:

0. **The `## ⇄ HANDOFF` block at the top of [STATUS.md](STATUS.md).** If it says `ACTIVE`,
   another AI has handed work to you: read the handoff document it links, end to end, before
   touching a single file — then resume from its "Resume at" pointer. Do not re-plan or
   re-decide anything it records as locked; that re-derivation wastes the very budget the
   handoff exists to protect. Verify any file, function or identifier it names still exists
   before relying on it. Full rules: [docs/cross-ai-protocol.md](docs/cross-ai-protocol.md)
   § Handoffs.
1. [STATUS.md](STATUS.md) — what's happening right now and who owns which lane.
2. [AGENTS.md](AGENTS.md) — the universal contract (rules, git flow, Definition of Done).
   §2a is the one you are most likely to violate: build to a drawn shape, never ship a placeholder.
3. [docs/cross-ai-protocol.md](docs/cross-ai-protocol.md) — how multiple AIs share state here.
4. The **design doc for your lane** in [docs/design/](docs/design/), plus anything your task's
   `Design:` field points at.

Then claim a lane in STATUS.md before you start editing.

## Before you write a line of code

Your task in [TASKS.md](TASKS.md) carries `Design: / Files: / Contract: / Verify: / Done:`. Treat
them as binding, in this order:

1. **Open the `Design:` reference and read it.** The class diagram tells you exactly which fields
   exist — build those, no more and no fewer. The sequence diagram tells you the call order. The
   state machine tells you which transitions are legal; the ones not drawn must be made
   *impossible*, not merely unimplemented. The `Contract:` is verbatim — don't paraphrase an
   interface another lane is building against.
2. **If there is no design reference and the shape isn't obvious, stop.** Write the design doc from
   [DESIGN-DOC.template.md](DESIGN-DOC.template.md) and get it agreed, or ask. Do not proceed on a
   plausible interpretation. Guessing produces something that looks finished and isn't, which costs
   more than the question would have.
3. **UI: find the reference image or mockup the task names, and look at it.** Match its layout,
   spacing, tokens and copy. Building *a* screen when *the* screen was specified is the exact
   failure this project's process exists to prevent. If your lane needs UI and you weren't given a
   reference, wire up existing components and flag it in STATUS.md for a Claude pass (see below) —
   don't invent a design in passing.
4. **Check your output against the diagram before you call it done**, field by field, call by call.

## What `UbuntuRemit` is

`UbuntuRemit is an ISO 20022-compliant cross-border remittance platform for African corridors, built around ASCO (the Agentic Settlement & Compliance Orchestrator): a multi-agent engine in which a Compliance Sentinel (AML/CFT/SARB enforcement), a Liquidity Strategist (cheapest/fastest rail across Ripple, SWIFT and PAPSS) and a Master Orchestrator negotiate each transaction, then emit an auditable pain.001/pacs.008 payload gated by hard-coded rule-based validators. It runs on sovereign infrastructure (AMD Instinct MI300X + ROCm 7.0 + vLLM) so no transaction data leaves the institution, and pairs that engine with a static HTML front end (the approved Stitch export, served as-is) for the send-money wizard, compliance dashboard and wallet history.`

The plan lives in [PLAN.md](PLAN.md); the WHAT in [SPEC.md](SPEC.md); the task list in [TASKS.md](TASKS.md).

## What you (Gemini) should do

- **Research** and summarize `<source material, if any>`.
- **Scaffold** modules, write **tests first**, review diffs, write and tighten docs.
- **Propose** edits to SPEC / PLAN / TASKS via PR — the team reviews and lands them.
- Work the **same** [TASKS.md](TASKS.md) list everyone uses; one task at a time.
- Keep [STATUS.md](STATUS.md) accurate after every step.

## What you must NOT do

- **Never push directly to `main`.** Always branch and open a PR. (Pre-push hook enforces this.)
- **Never report a placeholder as done.** No `TODO`, `FIXME`, `pass`, `NotImplementedError`, empty
  component, hard-coded sample data standing in for a real call, or function returning a constant to
  make a test pass. If you can't build the real thing, the task is **blocked** — say so in STATUS.md
  and name what unblocks it. The only exception is a stub the task text explicitly declared, with a
  follow-up task ID already written. (AGENTS.md §2a.)
- **Never invent structure the design doc doesn't have** — extra fields, extra endpoints, a
  different call order, a state that isn't in the machine. If the design is wrong or missing
  something, change the design doc in its own PR first; don't route around it in code.
- **Never substitute your own scope.** If the task is bigger than it looked, split it and say so in
  STATUS.md. Silently delivering the easy half as if it were the whole is the same failure as a
  placeholder.
- Edit a file another lane has claimed in STATUS.md without coordinating.
- **Own a frontend lane, or restyle the UI.** Visual design, component structure, tokens,
  layout and accessibility are Claude's by default (AGENTS.md §1). Use the existing
  components freely; don't introduce a new palette, restyle a component, or hand-roll UI
  that bypasses the component layer. If you need UI to finish your lane, wire up what
  exists and flag in STATUS.md that it needs a Claude pass.
- **`Never fabricate a regulatory fact, a rate, or a compliance verdict: every AML/KYC/SARB decision, FX rate, settlement confirmation and ISO 20022 field must trace to a real source document, a real rail response, or a deterministic validator — never to model judgement alone.`.** (Non-negotiable I in [PLAN.md](PLAN.md).)
- Blow any stated budgets (runtime, cost, size — see PLAN.md).

## Locked stack (do not swap without a plan change)

**Python 3.13 + FastAPI** services (DDD, one per bounded context) · **Kafka** for async + the audit log · **vLLM on ROCm 7.0 / AMD MI300X**, both models co-resident, **no third-party LLM API ever** · **Postgres** per stateful service, append-only audit store · **Docker per service + one docker-compose.yml** · Web: **static HTML, no framework and no build step** — the approved Stitch export in `apps/web/`, served as-is. A React port was built and reverted on 2026-07-27 for not matching the mockups; **do not re-attempt one** without changing docs/design/frontend-web.md §8 first. Swapping any of these needs a PLAN.md change first.
