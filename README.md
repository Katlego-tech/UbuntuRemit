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

The services in `services/` are designed but not built, so the figures on these pages are the
mockup's static values — honest, because nothing on them claims to be a live rate or balance.
T025 wires them to real endpoints.

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
├── libs/domain/                           the shared domain entities — built, 100 tests
└── services/                              gateway · asco · messaging · audit (planned)
```

## License

None. This repository carries no licence, so default copyright applies: all
rights reserved, and no permission to use, copy, modify or distribute is
granted. Ask before reusing anything here.
