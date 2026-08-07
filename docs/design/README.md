# Design documents

One per non-trivial lane, named after it, so `feat/<lane>` ↔ `docs/design/<lane>.md`.
Start from DESIGN-DOC.template.md; rules and the
which-diagram-when table are in ../design-documentation.md.

Diagrams are **Mermaid in fenced code blocks**, never images — they diff in a PR and every
assistant can read and write them.

| Lane | Doc | Status | Covers |
| --- | --- | --- | --- |
| `domain` | [domain-model.md](domain-model.md) | agreed | Class diagram for every core entity, the transfer state machine, invariants |
| `asco` | [asco-orchestrator.md](asco-orchestrator.md) | agreed | Multi-agent negotiation sequence, the hybrid-guardrail component diagram, the agent handshake JSON contracts |
| `iso20022` | [iso20022-messaging.md](iso20022-messaging.md) | agreed | Schema-version governance (MyStandards → policy matrix → verification pipeline), pain.001 → pacs.008 → camt.053 mapping, validation gates |
| `frontend-web` | [frontend-web.md](frontend-web.md) | agreed | Page structure, token mapping, visual references by path, deviations from the mockups |
| `send-money-wizard` | [send-money-wizard.md](send-money-wizard.md) | agreed, **visually unverified** | The three wizard steps that were never exported — steps 1, 3, 4 |

## Reading order for a new session

1. **[domain-model.md](domain-model.md)** — the nouns. Nothing else makes sense first.
2. **[asco-orchestrator.md](asco-orchestrator.md)** — the verb. How a transfer gets decided.
3. **[iso20022-messaging.md](iso20022-messaging.md)** — what leaves the building, in what shape.
4. **[frontend-web.md](frontend-web.md)** — only if you're touching UI (and read AGENTS.md §1
   first: frontend lanes are Claude's by default).

## The one rule that matters

**These diagrams are the specification; the prose around them is commentary.** If your
implementation has a field the class diagram doesn't, a call the sequence diagram doesn't, or a
state transition the machine doesn't, you are building something else. Change the diagram in its
own PR and get it agreed, or build what's drawn. See ../../AGENTS.md §2a.
