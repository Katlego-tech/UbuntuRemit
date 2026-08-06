# Code analysis

> Software rots. It decays every time we add a feature, make an adjustment, fix a defect. Every
> single commit carries a chance of reducing the overall health of the codebase, and over time that
> accumulates until the pace of delivery slows down.
> — Curriculum 201, *Code Analysis*

That is the whole argument. Nobody decides to make a codebase worse; it happens one reasonable-looking
commit at a time. Analysis is how you see it happening while it is still cheap to reverse.

This matters more on a repo where several AI copilots write code in parallel, not less. Each of them
is locally reasonable and none of them has read the whole codebase this week.

## The two kinds

### Static analysis — reading the code

Run by a tool, on the source, without executing it. Catches unused imports, shadowed names, unreached
branches, type errors, dangerous constructs, formatting drift.

This is **part of [the gate](git-workflow.md#the-gate)**, not a thing you run when you remember to.
`scripts/gate.sh` runs the linter and the formatter check before the tests, in the hook and in CI.

| Language | Lint | Format | Types |
|---|---|---|---|
| Python | `ruff check` | `ruff format --check` | `pyright` / `mypy` |
| TypeScript / JS | `eslint` | `prettier --check` | `tsc --noEmit` |

Two rules keep this from becoming noise:

- **Fail the build, don't collect warnings.** A warning nobody must fix is a warning everybody
  ignores, and a 400-warning baseline tells you nothing about the commit in front of you.
- **Fix the rule or fix the code — never silence a finding in passing.** A blanket `# noqa` is the
  same failure as a stubbed function: it makes the check report a state that isn't true. If a rule is
  genuinely wrong for this project, turn it off in the config, in its own commit, with a reason.

### Behavioural analysis — reading the history

Static analysis reads the code as it is now. Behavioural analysis reads `git log` and asks *which
code is actually costing us*, which is a different and usually more useful question. A gnarly file
nobody has touched in a year is not your problem. A gnarly file three people touched last week is.

```bash
# Hotspots: what changes most often?
git log --format= --name-only --since=3.months | sort | uniq -c | sort -rn | head -20

# Coupling: which files keep changing together? (candidates for a missing abstraction)
git log --format='%H' --name-only --since=3.months | awk 'NF' | ...

# Knowledge risk: who is the only person who has touched this?
git log --format='%an' --since=1.year -- path/to/file | sort | uniq -c | sort -rn
```

Read the top of the hotspot list against the complexity of those files. **High churn × high
complexity is where refactoring pays**; everywhere else it is mostly redecorating. On a project using
this kit, the hotspot list is also a design signal: a file that every lane keeps editing is usually a
boundary that the design docs drew in the wrong place.

## Refactoring

Refactoring is changing structure **without changing behaviour** — which is only a meaningful claim
if the behaviour is pinned by tests. So:

1. The tests must be green *before* you start. If they aren't, you are debugging, not refactoring.
2. If the code isn't covered, write the characterization tests first — tests that assert what it
   currently does, right or wrong. That's the safety net.
3. Change structure. Run the gate. Repeat in small steps.
4. **Refactoring commits change no behaviour and no tests.** Keep them separate from feature commits
   (`chore(lane): T0xx extract ...`) so a reviewer can trust the diff without re-reading the logic —
   and so `git bisect` stays useful.

A refactor that needs its tests rewritten to pass is not a refactor. It is a behaviour change wearing
a refactor's commit message, and it should be reviewed as one.

## Where this shows up

- [`scripts/gate.sh`](../scripts/gate.sh) runs lint + format checks before tests, locally and in CI.
- [AGENTS.md](../AGENTS.md) §8 Definition of Done: "lint/format clean" — this is what enforces it.
- [git-workflow.md](git-workflow.md#the-gate) — why the gate has no skip state.
- `.claude/agents/code-reviewer.md` — human/AI review catches what tools can't: naming, boundaries,
  whether the code matches its design doc.
