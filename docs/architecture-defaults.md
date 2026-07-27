# Architecture defaults

Every project this kit bootstraps starts from the same defaults, unless a project has a real reason
to deviate. These aren't non-negotiables in the [PLAN.md](../PLAN.md) sense (they're personal
convention, not project law) — but they're the answer when nothing in the spec forces a different
choice, so the tooling (`code-architect`, `feature-dev`) checks here before inventing something else.

## 1. Microservices by default

One service per bounded context, each with its own datastore where that's reasonable, rather than a
single monolith with internal modules. A new capability that doesn't obviously belong inside an
existing service's boundary gets its own service, not a new module bolted onto the nearest one.

**Deviate when:** the project is small enough (a weekend build, a hackathon, a single-purpose tool)
that service boundaries would be pure overhead before there's a second team or a second scaling
need. If you deviate, say so in PLAN.md's Technical Context and note it as a conscious choice, not an
oversight — the FrameFlow/OmniCaption projects this kit was distilled from were both time-boxed
enough that a single deployable made sense; that's a legitimate reason, "it's easier right now" alone
often isn't once more than one service is actually in play.

## 2. Async messaging via a broker

Services talk to each other asynchronously through a message broker rather than direct
service-to-service HTTP calls wherever the interaction can tolerate it (anything that isn't a
synchronous read the caller is blocking on). Pick **Kafka** or **RabbitMQ** per project and record
the choice + why in PLAN.md's Technical Context table:

- **Kafka** — high-throughput event streams, multiple independent consumers replaying the same log,
  event sourcing / audit trail requirements.
- **RabbitMQ** — task/work-queue routing, simpler pub-sub needs, lower operational overhead when the
  project doesn't need log retention or replay.

Synchronous HTTP/gRPC between services is still fine for request/response calls where the caller
genuinely needs an immediate answer — the default is "prefer async," not "never call synchronously."

## 3. `shadcn/ui` on the frontend

New frontend work builds on `shadcn/ui` (Radix primitives + Tailwind + CVA) as the component layer,
not a heavier all-in-one UI framework — it's copy-paste-owned code in your own tree, so it doesn't
lock you into someone else's design system. See
[.claude/skills/frontend-design/SKILL.md](../.claude/skills/frontend-design/SKILL.md): the stock
theme is exactly the "looks AI-generated" default that skill exists to avoid, so treat installed
components as unstyled structure and put a real token system (palette, type, radius, motion) on top.

## 4. Docker for every service

Every service (and the frontend, if it needs its own runtime rather than static hosting) ships with
its own `Dockerfile`, and local dev spins the whole system up with one `docker-compose.yml` at the
repo root — the services, the broker (Kafka/RabbitMQ), and any datastore. This is what makes
"microservices + a broker" actually runnable on a laptop instead of only in a deployed environment,
and it's the same mechanism [docs/testing-strategy.md](testing-strategy.md) leans on for integration
tests that need a real broker/datastore rather than a mock.

**Deviate when:** a service is trivial enough to run bare (a static frontend deployed to a CDN, a
single script with no dependencies) — containerizing it would be ceremony with no payoff. Note the
exception in `docs/project-structure.md` rather than silently leaving it out of `docker-compose.yml`.

## 5. Latest long-term-stable release, then pin it

For every language, runtime, framework, broker, and base image, choose the **latest long-term-stable
(LTS) / stable release** available at the time the project starts — not the version you happen to
remember, and not a bleeding-edge preview. Then **pin the exact version** so the choice is
reproducible:

- **Verify, don't assume.** An AI copilot's training cutoff lags reality — check the current LTS
  (the project's release page / `endoflife.date` / the registry) before writing a version number,
  rather than pinning whatever was current at training time. If you can't verify, say so instead of
  guessing.
- **Pin exactly, everywhere.** Lockfiles committed (`package-lock.json`, `poetry.lock`, `uv.lock`,
  `go.sum`, …); Docker base images tagged to a concrete version (`FROM node:22-bookworm-slim`, never
  `FROM node:latest`); broker/datastore images tagged, not `:latest`.
- **LTS over newest-of-all** where a project publishes an LTS track (Node, Python, Java, Postgres,
  Ubuntu base images…): take the newest release *on the LTS line*, not a shorter-support current
  release, unless the project specifically needs something only the newer line has.

**Deviate when:** a dependency's LTS is genuinely too old to carry a feature you need, or the project
is a throwaway experiment where reproducibility doesn't matter. Record the versions actually chosen
in PLAN.md's Technical Context (the `Language(s)` / `Runtime` rows), and note any deliberately
non-LTS pick there.

## Where this shows up

- [PLAN.template.md](../PLAN.template.md)'s Technical Context table has `Architecture`, `Messaging`,
  `Frontend`, and `Containerization` rows pre-filled with these defaults — overwrite them per project
  instead of leaving them blank.
- [docs/project-structure.md](project-structure.md)'s example tree assumes a `services/<name>/` shape,
  a broker, and a `docker-compose.yml` at the root.
- [docs/testing-strategy.md](testing-strategy.md)'s integration layer uses `docker-compose` to stand
  up the real broker + datastore instead of mocking them.
- PLAN.md's `Language(s)` / `Runtime` rows record the exact LTS versions chosen (default 5).
- `.claude/agents/code-architect.md` checks this file before defaulting a greenfield design choice.
- `.claude/commands/feature-dev.md`'s architecture-design phase points every candidate approach at it.
