# Project structure

The current, actual layout. Keep it in sync when the shape changes — a stale structure doc is worse
than none, because it actively misleads a session that trusted it.

**Status marks:** ✅ exists and is real · 🔄 exists, partially real · ⬜ designed, not built.

## The tree

```
UbuntuRemit/
├── README.md                      ✅ human overview + quick start
├── AGENTS.md                      ✅ the contract (every session reads this)
├── STATUS.md                      ✅ LIVE board — read first, update last
├── CLAUDE.md · GEMINI.md          ✅ per-tool entry points, both funnel to AGENTS.md
├── AI_ENTRYPOINT.template.md      ✅ spare, for a third tool joining later
├── SPEC.md · PLAN.md · TASKS.md   ✅ the planning documents
├── DESIGN-DOC.template.md         ✅ copied per lane to docs/design/<lane>.md
├── docs/
│   ├── design/                    ✅ THE DIAGRAMS — implementation is checked against these
│   │   ├── README.md              ✅ index + reading order
│   │   ├── domain-model.md        ✅ class diagram, settlement state machine, invariants
│   │   ├── asco-orchestrator.md   ✅ negotiation sequence, guardrails, agent JSON contracts
│   │   ├── iso20022-messaging.md  ✅ pain.001/pacs.008/camt.053 mapping, validation gates
│   │   └── frontend-web.md        ✅ component tree, tokens, visual references, deviations
│   ├── reference/                 ✅ the three ASCO source PDFs (overview, approach, feasibility)
│   ├── design-documentation.md    ✅ draw-before-you-build doctrine
│   ├── planning-workflow.md       ✅ SPEC → PLAN → design → TASKS → STATUS
│   ├── cross-ai-protocol.md       ✅ collision avoidance + handoffs
│   ├── architecture-defaults.md   ✅ microservices/Kafka/Docker/latest-LTS stance
│   ├── git-workflow.md            ✅ branch-only, commit format, the hook
│   ├── testing-strategy.md        ✅ the gate
│   ├── project-structure.md       ✅ this file
│   └── HANDOFF.template.md        ✅ unfilled until a handoff happens
├── pyproject.toml                 ✅ uv workspace root — pinned toolchain, ruff + pytest config
├── uv.lock                        ✅ every dependency pinned, committed
├── .python-version                ✅ 3.13.14 exactly
├── .claude/                       ✅ code-explorer/architect/reviewer, /feature-dev, frontend-design
├── .githooks/pre-push             ✅ blocks direct pushes to main + runs the test gate
├── .github/workflows/ci.yml       ✅ T008 — the same checks, server-side and unbypassable
├── apps/
│   └── web/                       ✅ static HTML — the Stitch export, no build step
│       ├── index.html             ✅ redirect to send-money.html; no UI of its own
│       ├── send-money.html        ✅ wizard step 2 — self-contained
│       ├── compliance.html        ✅ compliance health dashboard — self-contained
│       ├── wallet.html            ✅ wallet & history — self-contained
│       └── README.md              ✅ how to serve it, what changed, the rules
├── legacy/
│   ├── README.md                  ✅ why it's kept, and the rules
│   ├── stitch-mockups/            ✅ the frozen visual reference — DO NOT EDIT
│   └── stitch_send_money_wizard.zip  ✅ the original export, intact
├── services/                      ⬜ one directory per bounded context — all designed, NONE created
│   ├── gateway/                   ⬜ FastAPI intake, pain.001 parsing, auth
│   ├── asco/                      ⬜ orchestrator + agents + entry/exit guardrails
│   ├── inference/                 ⬜ vLLM on ROCm 7.0, both models on one MI300X
│   ├── messaging/                 ⬜ ISO 20022 build/parse/validate, vendored XSDs — T028 starts here
│   ├── rails/                     ⬜ Ripple · SWIFT · PAPSS adapters
│   └── audit/                     ⬜ Kafka asco.audit consumer → append-only store
└── docker-compose.yml             🔄 Kafka + Postgres real and running; service entries are T063
```

## Why this shape

**Monorepo, hard service boundaries inside it.** The Implementation Approach requires
financial-routing logic to be decoupled from LLM-inference logic so models can be swapped without
touching banking rules — that's a service boundary, not a module boundary. But the services share a
domain vocabulary (`Transfer`, `Money`, `ComplianceVerdict`) and one design-doc set, and splitting
them across repos would put the diagrams out of reach of the code they specify.

**`services/asco` is one service, not three.** The three agents are personas served by one
orchestrator process; they are not independently deployable and don't own separate state. Splitting
them would create a distributed transaction across a negotiation that has to be atomic and
auditable. `services/inference` *is* separate, because a model server has a completely different
scaling and hardware profile from orchestration logic.

**`services/` has no directories in it yet, deliberately.** The toolchain that will build them is
real and pinned (`pyproject.toml`, `uv.lock`, `.python-version`), the gate that will check them runs
locally and in CI, and the infrastructure they will talk to comes up with `docker compose up`. What
does not exist is a `services/<name>/` containing an empty `__init__.py` — that is the "empty
component" AGENTS.md §2a forbids, and it would also have to guess where the shared domain entities
live, which is an open question in [design/domain-model.md](design/domain-model.md) §9. Each service
directory gets created by the first task that puts real code in it: `messaging` at T028,
`asco` at T040, `audit` at T050.

**`apps/web` is three self-contained HTML files, and stays that way.** No framework, no build step,
no shared partials — the duplication across the three pages is deliberate. The export is the
*approved* design, and every abstraction extracted from it is a chance to drift from the reference.
A React port was built and reverted on 2026-07-27 for exactly that reason; the decision and the
lesson are in [design/frontend-web.md](design/frontend-web.md) §8.

Whatever the client eventually becomes, it stays **thin**: no business rule lives there. A fee, a
limit, or a compliance decision computed in the client is a rule that can be bypassed with devtools.

**`legacy/` is frozen, not dead.** It's the visual reference every UI task is specified against.
See [../legacy/README.md](../legacy/README.md).

## Run it

```bash
# Web client. No install, no build.
python3 -m http.server 5173 --directory apps/web    # http://localhost:5173
# Its test is visual: open each page beside its PNG in legacy/stitch-mockups/.

# Python toolchain. Installs Python 3.13.14 and the locked tools into .venv/.
uv sync --frozen
uv run ruff check .
uv run pytest          # exits 5 ("no tests collected") until the first service lands

# Infrastructure: Kafka 4.3.1 (KRaft) + Postgres 18.4, for integration tests.
docker compose up -d
docker compose ps      # both report healthy
# Postgres is on host port 55432, not 5432 — sibling projects hold the default.
docker compose down    # add -v to discard the volumes

# Services themselves are not implemented. `docker compose up` starts the
# infrastructure they will use, not the services.
```

## Status

Everything under `services/` is **designed but not built** — the diagrams in [design/](design/) are
complete enough to implement from, and `TASKS.md` Phases 3–5 give the order. The scaffold around
them is done and verified: the toolchain resolves, the gate runs locally and in CI, and Kafka and
Postgres come up healthy.

`apps/web` is real and serves, but is static: the figures on the pages are the mockup's values, and
the pages load Tailwind, fonts and one image from third-party hosts. T024 self-hosts those
dependencies; T025 wires the pages to real endpoints once Phase 3 lands. Neither is cosmetic —
a settlement console that compiles its CSS in the browser from a CDN is not a production artefact.
