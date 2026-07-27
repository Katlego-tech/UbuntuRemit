# UbuntuRemit

Empowering African prosperity by providing a secure, ISO 20022-compliant bridge that honors the
spirit of Ubuntu, ensuring that every remittance strengthens the bonds of community through
transparent, frictionless, and compliant cross-border exchange.

---

## What this is

A cross-border remittance platform for African corridors, built around **ASCO — the Agentic
Settlement & Compliance Orchestrator**. Three agents negotiate every transaction: a **Compliance
Sentinel** (AML/CFT/SARB), a **Liquidity Strategist** (cheapest and fastest rail across Ripple,
SWIFT and PAPSS), and a **Master Orchestrator** that holds state and emits the ISO 20022 payload.

The design bet in one line: **the models suggest, deterministic code decides.** Hard-coded
guardrails sit on both sides of the negotiation, so an LLM can rank and explain a routing choice
but can never permit a settlement. Everything runs on sovereign infrastructure (AMD Instinct
MI300X · ROCm 7.0 · vLLM), so no transaction data reaches a third-party API.

## Start here

| If you're… | Read |
| --- | --- |
| **any contributor, human or AI** | [AGENTS.md](AGENTS.md) — the contract. §2a especially. |
| **picking up work** | [STATUS.md](STATUS.md) — the live board. Read first, update last. |
| **about to write code** | [docs/design/](docs/design/) — the diagrams you build to. |
| **using Claude** | [CLAUDE.md](CLAUDE.md) |
| **using Gemini / Antigravity** | [GEMINI.md](GEMINI.md) |
| **looking for the WHAT / HOW / backlog** | [SPEC.md](SPEC.md) · [PLAN.md](PLAN.md) · [TASKS.md](TASKS.md) |

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

The services in `services/` are designed but not built, so the figures on these pages are the
mockup's static values — honest, because nothing on them claims to be a live rate or balance.
T025 wires them to real endpoints.

## How work happens here

This repo runs the [Cultivation](https://github.com/Katlego-tech) process: three shared-state files
(`AGENTS.md`, `STATUS.md`, `TASKS.md`), lane-based coordination, branch-only `main` with a pre-push
gate, and per-tool AI entry points that all funnel to `AGENTS.md`.

Two rules matter more than the rest, and both exist because work that comes back *adjacent to* what
was asked is expensive precisely because it looks finished:

1. **Nothing non-trivial is built before it's drawn.** Class, sequence and state diagrams live in
   [docs/design/](docs/design/) and are what implementations are checked against — not the prose
   around them. [docs/design-documentation.md](docs/design-documentation.md)
2. **No placeholder is ever "done".** No `TODO`, stub body, empty component, or hard-coded
   stand-in data. If the real thing can't be built yet, the task is *blocked*, and STATUS.md says
   what unblocks it. [AGENTS.md](AGENTS.md) §2a

## Layout

```
UbuntuRemit/
├── AGENTS.md · CLAUDE.md · GEMINI.md      shared-state entry points
├── SPEC.md · PLAN.md · TASKS.md · STATUS.md
├── DESIGN-DOC.template.md                 per-lane design-doc template
├── docs/
│   ├── design/                            the diagrams — build to these
│   ├── reference/                         the three ASCO source papers
│   └── *.md                               process docs
├── apps/web/                              static HTML client — the Stitch export, as-is
├── legacy/stitch-mockups/                 frozen visual reference — do not edit
└── services/                              gateway · asco · messaging · audit (planned)
```

## License

See [LICENSE](LICENSE).
