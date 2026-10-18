# UbuntuRemit

A backend prototype for cross-border remittances on African corridors. It builds and parses
ISO 20022 messages and validates them against the base ISO 20022 schemas (see the conformance
boundary below for exactly what that does and doesn't mean).

---

## What this is

A Python/FastAPI backend built around **ASCO, the Agentic Settlement & Compliance Orchestrator**.
Two LLM-backed agents take part in each transfer: a **Compliance Sentinel** (AML/CFT checks) and a
**Liquidity Strategist** (ranks the rails it is given quotes for). A **Master Orchestrator** holds
the transfer's state, but it is a deterministic state machine, not a model: it makes no LLM calls.

The design bet in one line: **the models suggest, deterministic code decides.** Fail-closed
guardrails sit on both sides of the agents (UN sanctions-list screening, PEP escalation, KYC-tier
transfer limits on the way in; validation of the agents' output on the way out), so a model can
rank and explain a routing choice but can never approve a settlement. The agents are tested with
scripted model responses; they have **not yet been run against a live model**.

Payment rails (Ripple, SWIFT, PAPSS) sit behind an adapter interface with a fallback router that
retries a failed settlement on another rail. No real rail adapter exists yet: real integrations
wait on sandbox access.

It is designed for self-hosted inference, so that no transaction data would reach a third-party
LLM API. A vLLM client for both agents exists, but the target hardware (an AMD Instinct MI300X) is
not provisioned, so no model has been served.

## Where it stands

A backend prototype that **does not run end to end yet**. 336 unit tests plus 7 integration tests
(against the compose Postgres and Kafka).

| Part | State |
| --- | --- |
| `libs/domain` | Built. The shared entities (`Transfer`, `Money`, the transfer state machine). |
| `services/messaging` | Built. pain.001, pacs.008, camt.053 and head.001, validated against the official XSDs. |
| `services/asco` | Built. The two agents, the orchestrator state machine and the entry/exit guardrails. Agents tested with scripted model responses only. |
| `services/audit` | Built. Append-only Postgres audit store fed from Kafka, enforced with database grants and triggers. |
| `services/gateway` | Built. FastAPI endpoints with every outside source injected; an endpoint whose source isn't configured answers 503 and names it. |
| `services/rails` | Interface and fallback router only. No real adapter until sandbox access. |
| `services/inference` | Client only (`VllmChatClient`). No model server until the MI300X is provisioned. |
| Start-up wiring | Not built. Nothing yet constructs the gateway's sources (model clients, sanctions list, audit logger) at start-up, so the services don't run together. |
| Web client | Static mockup pages, not connected to the backend. |

> ### ⚠ Conformance boundary
>
> UbuntuRemit builds ISO 20022 messages against the **public base catalogue** at iso20022.org.
> It is **not SARB PEM-conformant and does not claim to be.** SARB publishes its Usage Guidelines
> — the constrained subset it actually enforces — as schemas on SWIFT MyStandards, which requires
> participant standing this project does not have.
>
> The design *targets* SAMOS and SADC-RTGS. The implementation is validated against neither.
> Reasoning, and the exact list of what may and may not be claimed:
> [docs/design/iso20022-messaging.md](docs/design/iso20022-messaging.md) §3.6.

## Start here

| If you're… | Read |
| --- | --- |
| **about to write code** | [docs/design/](docs/design/) — the diagrams you build to. |
| **looking for the WHAT / HOW** | [SPEC.md](SPEC.md) · [PLAN.md](PLAN.md) |
| **wondering how the repo is laid out** | [docs/project-structure.md](docs/project-structure.md) |

## Set up your clone

```bash
bash install-hooks.sh    # once per clone, by everyone — core.hooksPath is never cloned
uv sync --frozen         # Python 3.13.14 + the locked toolchain into .venv/
bash scripts/gate.sh     # every check the hook and CI run, in one script
docker compose up -d     # Kafka + Postgres, for integration tests
```

## Run the web client

Static HTML — no build step, no framework, no dependencies.

```bash
python3 -m http.server 5173 --directory apps/web
# http://localhost:5173  →  send-money.html
```

Pages: `send-money.html` (wizard step 2), `compliance.html` (compliance health dashboard),
`wallet.html` (wallet & history). Each *is* the approved Stitch export, and each has a PNG in
`legacy/stitch-mockups/` — **open the page beside its PNG before and after any change.** That
comparison is the entire acceptance test for this directory.

A React port was built and reverted on 2026-07-27 for not matching the mockups; see
[docs/design/frontend-web.md](docs/design/frontend-web.md) §8 before considering another rewrite.

The pages aren't connected to the services yet, so the figures on them are the mockup's static
values — honest, because nothing on them claims to be a live rate or balance. T025 wires them to
real endpoints.

## How work happens here

Branch-only `main`, protected server-side: no direct pushes, and the `gate` check must be green
before a PR can merge. Every check lives in one place — [`scripts/gate.sh`](scripts/gate.sh) — which
the pre-push hook and CI both run, so local green and pipeline green mean the same thing. The gate
has **no skip state**: a check that couldn't run fails the push rather than reporting green, because
a skipped check and a passed check look identical to whoever reads the output.

Two rules matter more than the rest, and both exist because work that comes back *adjacent to* what
was asked is expensive precisely because it looks finished:

1. **Nothing non-trivial is built before it's drawn.** Class, sequence and state diagrams live in
   [docs/design/](docs/design/) and are what implementations are checked against — not the prose
   around them.
2. **No placeholder is ever "done".** No `TODO`, stub body, empty component, or hard-coded
   stand-in data. If the real thing can't be built yet, the task is *blocked*, and what unblocks it
   is written down. The gate enforces this mechanically on every push.

The day-to-day collaboration process (the shared board, lane claiming, the per-tool AI entry points)
is kept out of this repo deliberately — it's working process, not product. It lives on the
maintainer's machine, bootstrapped from the Cultivation kit.

## Layout

```
UbuntuRemit/
├── SPEC.md · PLAN.md                      the WHAT and the HOW
├── scripts/gate.sh                        every check, run by the hook and CI alike
├── install-hooks.sh                       run once per clone
├── docs/
│   ├── design/                            the diagrams — build to these
│   ├── reference/                         the three ASCO source papers
│   └── project-structure.md               the actual layout
├── apps/web/                              static HTML client — the Stitch export, as-is
├── legacy/stitch-mockups/                 frozen visual reference — do not edit
├── libs/domain/                           the shared domain entities
└── services/                              gateway · asco · messaging · audit · rails · inference
```

## License

None. This repository carries no licence, so default copyright applies: all
rights reserved, and no permission to use, copy, modify or distribute is
granted. Ask before reusing anything here.
