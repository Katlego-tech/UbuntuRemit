# Design — `asco` (Agentic Settlement & Compliance Orchestrator)

**Status:** agreed · **Owner:** Kirito (Claude) · **Tasks:** T040–T052 ·
**Spec:** [SPEC.md](../../SPEC.md) US2, US3

> The engine. Three agents negotiate a transfer; deterministic guardrails decide whether their
> conclusion is allowed to leave the building.

---

## 1. What this covers

The negotiation between the Compliance Sentinel, the Liquidity Strategist and the Master
Orchestrator; the hard-coded gates on either side of them; and the audit trail they emit. It does
**not** cover the entity definitions ([domain-model.md](domain-model.md)) or the wire format
([iso20022-messaging.md](iso20022-messaging.md)).

## 2. Reference material

| Kind | Where |
| --- | --- |
| Agent personas + model sizing | `docs/reference/UbuntuRemit_ ASCO Project Overview.pdf` §2 |
| Guardrail pattern, risk register | `docs/reference/UbuntuRemit_ ASCO Implementation Approach.pdf` §3–4 |
| Hardware envelope | `docs/reference/UbuntuRemit_ ASCO Research and Feasibility Paper.pdf` §4 |
| External standard | ISO 20022 pain.001 / pacs.008 |

## 3. Components

```mermaid
flowchart TB
    subgraph edge["services/gateway (FastAPI)"]
        A[pain.001 intake]
    end

    subgraph guard1["Entry guardrail — deterministic, no LLM"]
        B1[Schema validation]
        B2[Sanctions / PEP screen]
        B3[Corridor + limit check]
    end

    subgraph asco["services/asco — the orchestrator"]
        MO[Master Orchestrator<br/>deterministic state machine]
        CS[Compliance Sentinel<br/>70B reasoning model]
        LS[Liquidity Strategist<br/>32B math-optimised model]
    end

    subgraph infer["services/inference — vLLM on ROCm 7.0 / MI300X"]
        V1[(70B weights)]
        V2[(32B weights)]
    end

    subgraph guard2["Exit validator — deterministic, no LLM"]
        C1[Verdict citation check]
        C2[Rail eligibility re-check]
        C3[ISO 20022 schema validation]
    end

    subgraph out["Downstream"]
        R[(Rail adapter:<br/>Ripple / SWIFT / PAPSS)]
        K[(Kafka: asco.audit)]
    end

    A --> B1 --> B2 --> B3 --> MO
    MO <--> CS
    MO <--> LS
    CS --> V1
    LS --> V2
    MO --> C1 --> C2 --> C3 --> R
    MO -.every turn.-> K
    CS -.-> K
    LS -.-> K

    classDef hard fill:#bdf0ad,stroke:#164212,color:#002201
    classDef soft fill:#ffe088,stroke:#735c00,color:#241a00
    class B1,B2,B3,C1,C2,C3 hard
    class CS,LS soft
```

**The colouring is the point.** Green nodes are deterministic and are the only things authorised
to permit or forbid a settlement. Gold nodes are LLMs: they *suggest*, they *rank*, they *explain*
— they never decide. This is the Hybrid Guardrail Pattern from the Implementation Approach, and
it is the mitigation for the top-line risk in that document's register (non-deterministic output →
regulatory fines).

### 3.1 The sanctions list the entry gate screens against (T041a, T075)

The gate holds no list of its own: it is given a `SanctionsScreener` whose list carries a
`SanctionsListSource(name, published)`, and every SANCTIONS rejection cites that source. The first
real source is the **UN Security Council Consolidated List**, published as XML at
`https://scsanctions.un.org/resources/xml/en/consolidated.xml`.

```mermaid
flowchart LR
    X["consolidated.xml<br/>(fetched by operations)"] --> L["load_un_consolidated_list()"]
    L -->|"name = UN Security Council Consolidated List<br/>published = root @dateGenerated (UTC date)"| S[StaticSanctionsScreener]
    S --> G[EntryGuardrail]
```

What the loader reads, verified against the published file (2026-10-10: 736 individuals, 274
entities):

| Element | Becomes |
| --- | --- |
| `CONSOLIDATED_LIST/@dateGenerated` | `SanctionsListSource.published` — required; a list with no date is refused |
| `INDIVIDUAL/FIRST_NAME … FOURTH_NAME` | one name: the present parts joined by single spaces |
| `INDIVIDUAL_ALIAS/ALIAS_NAME` | a name, **every quality** (`Good` and `Low`) — a weak alias still matches |
| `INDIVIDUAL/NAME_ORIGINAL_SCRIPT`, `ENTITY/NAME_ORIGINAL_SCRIPT` | a name |
| `ENTITY/FIRST_NAME`, `ENTITY_ALIAS/ALIAS_NAME` (`a.k.a.` and `f.k.a.`) | a name |

- **The loader never fetches.** It parses bytes it is handed, so what was screened against is
  exactly the file operations fetched and dated. The file comes from outside the institution, so
  any document carrying a `DOCTYPE` is refused (the published list has none) and entities are never
  resolved. `dateGenerated` must carry a UTC offset; `published` is its UTC date.
- **Matching is exact after normalisation** — NFKC, invisible format characters (zero-width
  spaces, soft hyphens) dropped, whitespace collapsed, case-folded; applied to both sides. That is weaker than
  production screening, which matches transliterations and near-misses. Choosing a fuzzy-match
  policy and its threshold is a compliance decision, not a coding one: **T077**, blocked on it.
- The list carries no BICs, so a UN-loaded screener screens names only.

## 4. Negotiation flow

```mermaid
sequenceDiagram
    autonumber
    participant C as Client (pain.001)
    participant G as Gateway
    participant EG as Entry guardrail
    participant MO as Master Orchestrator
    participant CS as Compliance Sentinel
    participant LS as Liquidity Strategist
    participant XV as Exit validator
    participant R as Rail adapter
    participant K as Kafka asco.audit

    C->>G: POST /transfers (pain.001)
    G->>EG: validate(schema, sanctions, limits)
    alt any hard gate fails
        EG-->>C: 422 REJECTED (cited rule)
        EG->>K: AuditRecord(actor=entry_guardrail)
        Note over EG,C: No LLM is invoked. A sanctions hit<br/>is never a matter of opinion.
    else clear
        EG->>MO: Transfer(state=INITIATED)
    end

    MO->>CS: assess(transfer) [JSON schema: ComplianceAssessment]
    CS->>K: AuditRecord(thought, action, observation)
    CS-->>MO: ComplianceVerdict{outcome, riskScore, citedRules[]}

    alt outcome == BLOCK
        MO->>XV: reject(verdict)
        XV-->>C: REJECTED + citedRules
    else outcome == ESCALATE
        MO-->>C: PENDING_REVIEW (human queue)
        Note over MO: ESCALATE is terminal for the agent loop.<br/>No agent may talk itself out of an escalation.
    else outcome == PASS
        MO->>LS: propose(transfer, constraints=verdict.constraints)
        LS->>K: AuditRecord(thought, action, observation)
        LS-->>MO: LiquidityProposal{rail, totalCost, estimatedSeconds}

        opt proposal violates a compliance constraint
            MO->>CS: challenge(proposal)
            CS-->>MO: ComplianceVerdict (revised)
            Note over MO,CS: Bounded at 3 exchanges.<br/>On exhaustion: ESCALATE, never "best effort".
        end

        MO->>XV: validate(transfer, verdict, proposal, pacs.008)
        alt exit validation fails
            XV->>K: AuditRecord(actor=exit_validator, deterministicOverride=true)
            XV-->>C: REJECTED (the LLM's conclusion was overruled)
        else
            XV->>R: submit(pacs.008)
            R-->>MO: confirmation
            MO->>K: AuditRecord(state=DELIVERED)
            MO-->>C: 202 SETTLING → DELIVERED
        end
    end
```

### Failure paths, explicitly

| Failure | Behaviour |
| --- | --- |
| Inference timeout (either agent) | `ESCALATE` to the human queue. **Never** default-allow. |
| Agent returns malformed JSON | One re-ask with the schema; second failure → `ESCALATE`. |
| Negotiation exceeds 3 exchanges | `ESCALATE`. No "best effort" settlement. |
| Rail rejects `pacs.008` | `FAILED`, then at most 2 alternate rails (domain-model §4). |
| Kafka unavailable | **Refuse the transfer.** An unauditable settlement is worse than a failed one — SARB PEM requires every node identifiable. |

That last row is a deliberate availability trade-off and is recorded again in §7.

## 5. Contracts — the agent handshake

Agents exchange **JSON validated against a schema**, never prose. This is the Implementation
Approach's "JSON-schema-based communication protocol to ensure agents exchange findings
deterministically without hallucinating payload structures". Both models are served with
constrained decoding against these schemas; a response that doesn't validate is not parsed
leniently, it is re-asked once and then escalated.

```jsonc
// Master Orchestrator -> Compliance Sentinel
{
  "transferId": "string (uuid)",
  "corridor": { "source": "ZAR", "target": "KES" },
  "amount": { "minorUnits": 1500000, "currency": "ZAR" },
  "declaration": { "purpose": "FAMILY_SUPPORT", "sourceOfFunds": "EMPLOYMENT_SALARY" },
  "senderProfile": { "kycTier": "L3", "countryOfResidence": "ZA", "isPep": false },
  "recipientProfile": { "countryOfResidence": "KE", "accountAgeDays": 412 },
  "priorTransfers30d": { "count": 4, "totalMinorUnits": 4200000 }
}
```

```jsonc
// Compliance Sentinel -> Master Orchestrator   (schema: ComplianceVerdict)
{
  "outcome": "PASS | ESCALATE | BLOCK",     // required
  "riskScore": 0.0,                          // required, 0.0-1.0
  "citedRules": ["FICA s21", "SARB EXCON B.4"], // required, 1-20 items, each 1-200 chars
  "rationale": "string, <= 600 chars",       // required
  "constraints": {                            // optional; binds the Liquidity Strategist
    "forbiddenRails": ["SWIFT"],              // distinct rails, at most 3
    "maxSettlementSeconds": 5                 // > 0
  }
}
```

```jsonc
// Master Orchestrator -> Liquidity Strategist
{
  "transferId": "string (uuid)",
  "corridor": { "source": "ZAR", "target": "KES" },
  "amount": { "minorUnits": 1500000, "currency": "ZAR" },
  "constraints": { "forbiddenRails": ["SWIFT"], "maxSettlementSeconds": 5 },
  "railQuotes": [
    { "rail": "RIPPLE", "feeMinorUnits": 0, "spreadBps": 12, "estimatedSeconds": 3.2 },
    { "rail": "PAPSS",  "feeMinorUnits": 1200, "spreadBps": 8, "estimatedSeconds": 11.0 }
  ]
}
```

```jsonc
// Liquidity Strategist -> Master Orchestrator   (schema: LiquidityProposal)
{
  "rail": "RIPPLE | SWIFT | PAPSS",          // required, MUST be one of the supplied railQuotes
  "totalCost": { "minorUnits": 1800, "currency": "ZAR" },  // required; integer >= 0, the transfer's own currency
  "estimatedSeconds": 3.2,                    // required, > 0, equal to the chosen rail's quote
  "rationale": "string, <= 400 chars"         // required
}
```

**`railQuotes` are supplied to the model, never invented by it.** The Strategist ranks options it
was given; a rail or a fee that wasn't in the input is a fabrication, and the exit validator
rejects the proposal outright (Non-negotiable I). Concretely it rejects a rail not quoted, an
`estimatedSeconds` different from the chosen rail's quote, and a `totalCost` below that quote's fee.
Every field marked required above is read without a default: a missing one is malformed output
(re-ask once, then escalate), never a zero.

## 6. Structure

| Path | New? | Responsibility |
| --- | --- | --- |
| `services/gateway/` | planned | FastAPI intake, pain.001 parsing, auth |
| `services/asco/orchestrator/` | built (T042, T046) | State machine & negotiation coordinator — **deterministic, no LLM calls** |
| `services/asco/agents/sentinel.py` | built (T043) | Compliance Sentinel prompt + schema binding; **refuses to exist without an inference client** |
| `services/asco/agents/strategist.py` | built (T044) | Liquidity Strategist prompt + schema binding; **refuses to exist without an inference client** |
| `services/asco/guardrails/entry.py` | built (T040, T041, T041a, T071) | Schema, sanctions, limits — the sanctions list and the limit table are both injected with a named, dated source and cited on every rejection; no figure lives in code |
| `services/asco/guardrails/exit.py` | built (T045) | Citation check, rail re-check, ISO 20022 validation |
| `services/inference/` | client built (T078); servers **blocked** (T079, MI300X) — [inference.md](inference.md) | `VllmChatClient`, the `LLMClient` both agents call vLLM through; the two vLLM servers on one MI300X node |
| `services/audit/` | built (T050, T051, T050a) | `KafkaAuditLogger` (acks=all, fails closed) → `asco.audit` → `KafkaAuditConsumer` → Postgres, writer role holds SELECT + INSERT only; triggers as the second wall. The production topic's retention is a SARB PEM figure not yet sourced — **T050b** |
| `services/rails/` | router built (T055); adapters **blocked** (T052-T054, sandbox credentials) | Bounded-retry router over injected adapters; no adapter ships yet |

## 7. Decisions & alternatives

| Decision | Chosen | Rejected, and why |
| --- | --- | --- |
| Orchestrator implementation | deterministic Python state machine | an LLM orchestrator — a non-deterministic controller makes the whole audit trail unreproducible |
| Agent framework | explicit schema-bound calls | AutoGen/LangGraph free-form chat — free-form turns are what produce unparseable payloads under load |
| Negotiation bound | 3 exchanges, then ESCALATE | unbounded — RTGS SLA windows are hard deadlines |
| Model placement | both models co-resident on one MI300X (192GB HBM3) | two nodes — the Feasibility Paper sizes 70B + 32B onto a single node; two nodes doubles cost for no latency win |
| Quantisation | FP8, measured before adoption | assuming FP4 is fine — the risk register allows FP8/FP4 for latency, but reasoning degradation must be measured, not assumed |
| Audit unavailable | refuse the transfer | settle-and-log-later — an unauditable settlement violates SARB PEM traceability |

Deviations from ../architecture-defaults.md: none.

## 8. How this is verified

- **Determinism harness:** the same transfer replayed 50× against a pinned model + seed produces
  the same `outcome` and the same `rail`. Variance here is a release blocker.
- **Guardrail bypass test:** a crafted Sentinel response of `{"outcome":"PASS","citedRules":[]}`
  must be rejected by the exit validator, not passed through.
- **Fabricated-rail test:** a Strategist proposal naming a rail absent from `railQuotes` is
  rejected and audited with `deterministicOverride=true`.
- **Escalation test:** inference timeout produces `ESCALATE`, never `PASS`.
- **Audit completeness:** every terminal state has ≥ 1 `AuditRecord` per participating actor.

## 9. Open questions

- [ ] Which sanctions list provider, and what is its refresh SLA? The entry guardrail's
      correctness is bounded by this and it cannot be stubbed.
- [ ] Human-review queue: who staffs `ESCALATE`, and what is the SLA before a transfer expires?
- [ ] Are `railQuotes` pulled synchronously per transfer, or from a cached book? Affects whether
      `FxQuote.source` can ever be `FALLBACK_CACHED` on a live settlement.
