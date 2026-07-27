# Git workflow

The point: **`main` is always green and demo-ready**, and the *only* way code reaches `main` is a
**reviewed, CI-green Pull Request** — never a direct push.

## The rule

> **Nobody pushes directly to `main`. All work happens on branches and merges via Pull Request, only
> after the gate runs clean and tests pass.**

The one common exception: the **initial scaffold commit** (this kit, filled in) is often pushed
straight to `main` once, to seed the repo. From that point on, direct pushes are disabled (local hook
+ server-side branch protection).

## Branch model

- **`main`** — protected. Only updated by merging a PR. Always green, always demo-able.
- **Feature branches** — all real work: `feat/<lane>` (e.g. `feat/parser`) · `fix/<thing>` ·
  `docs/<thing>` · `chore/<thing>`.

## The loop (every change)

1. Read [STATUS.md](../STATUS.md), pick/confirm a task in [TASKS.md](../TASKS.md), claim your
   **lane** in STATUS.md.
2. `git switch -c feat/<lane>` — branch off fresh `main`.
3. Build the change **with its tests**.
4. `git push -u origin feat/<lane>` — the **pre-push hook runs the tests** and **blocks the push if
   they fail** (and blocks any attempt to push straight to `main`).
5. Open a **Pull Request into `main`**.
6. **Wait for green CI** + a quick review from another contributor.
7. **Merge the PR.** Tick the task `[x]` in TASKS.md, update STATUS.md (+ Log line).
8. Delete the branch. `git switch main && git pull`.

## Merge requirements (all must be true before merging a PR)

- ✅ CI green on the branch/PR.
- ✅ Tests pass (the pre-push hook proved it locally too).
- ✅ At least one review from another contributor.
- ✅ Task ticked in TASKS.md; STATUS.md updated.
- ✅ No unresolved conflicts with `main`.

## Two layers of "no direct push to main"

1. **Local pre-push hook** (`.githooks/pre-push`) — refuses to push to `main` and runs the test suite
   on every push. Enable once per clone:
   ```bash
   git config core.hooksPath .githooks
   ```
2. **Server-side branch protection** (GitHub/GitLab/etc.) — the real gate, since the local hook is
   opt-in and bypassable. Turn on: require a PR before merging, require the CI status check, require
   at least one approval, and disallow bypassing those rules for everyone (including admins, if the
   platform allows it).

## Commit messages

Small commits, clear messages, reference the task:
```
feat(parser): T007 add screenplay parsing service
fix(compliance): T029 correct rounding in ratio calc
docs: T035 confirm judging rubric
```

`<type>(<lane>): <TASK-ID> <summary>` — `<type>` is `feat`/`fix`/`docs`/`chore`; `<lane>` matches the
lane labels in [cross-ai-protocol.md](cross-ai-protocol.md); `<TASK-ID>` ties the commit back to
TASKS.md.

## Emergency bypass

Only when genuinely necessary (e.g. the hooks themselves are broken):
```bash
git push --no-verify
```
`--no-verify` skips the pre-push hook. Use sparingly, announce it in STATUS.md, and follow up
immediately to restore the gate — CI still checks the PR regardless.

## Secrets & artifacts

Never commit `.env`, credentials, uploaded user content, or generated artifacts — see `.gitignore`.

---

## A working pre-push hook to start from

Save as `.githooks/pre-push`, `chmod +x` it, and enable with `git config core.hooksPath .githooks`.
It blocks direct pushes to `main` and runs whichever test/lint tooling it finds installed, skipping
gracefully (with a visible message) for anything not set up yet — CI is the backstop for those.

```bash
#!/usr/bin/env bash
# UbuntuRemit pre-push gate.
# Enable once per clone:  git config core.hooksPath .githooks
#
# Enforces two things:
#   1. Branch-only workflow — direct pushes to `main` are rejected (open a PR instead).
#   2. The test gate — the suite must pass before code leaves your machine.
#
# Emergency bypass (use sparingly, never to push a red main):  git push --no-verify

set -u
protected="refs/heads/main"

# --- 1. Block direct pushes to main -----------------------------------------
while read -r local_ref local_sha remote_ref remote_sha; do
  if [ "$remote_ref" = "$protected" ]; then
    echo "❌  Direct pushes to 'main' are not allowed."
    echo "    Push a feature branch and open a PR:  git push origin feat/<lane>"
    exit 1
  fi
done

echo "🔎  Running the test gate before push..."
fail=0
root="$(git rev-parse --show-toplevel)"

# --- 2. Python service(s) — add one block per service directory ------------
for svc in services/api services/worker; do
  dir="$root/$svc"
  [ -d "$dir" ] || continue
  if python -c "import pytest" >/dev/null 2>&1; then
    echo "→ pytest ($svc)"
    ( cd "$dir" && python -m pytest -q ) || fail=1
  else
    echo "⏭️  pytest not importable locally — skipping $svc (CI still runs it)."
  fi
  if command -v ruff >/dev/null 2>&1; then
    echo "→ ruff check ($svc)"
    ( cd "$dir" && ruff check . ) || fail=1
  fi
done

# --- 3. Node app(s) ----------------------------------------------------------
for app in apps/web apps/mobile; do
  [ -f "$root/$app/package.json" ] || continue
  if [ -d "$root/node_modules" ]; then
    echo "→ npm test ($app)"
    ( npm test --workspace "$app" --silent --if-present ) || fail=1
  else
    echo "⏭️  deps not installed — skipping $app (CI still runs it)."
  fi
done

if [ "$fail" -ne 0 ]; then
  echo "❌  Test gate failed. Fix it before pushing (or --no-verify only for a green branch)."
  exit 1
fi

echo "✅  Test gate passed. Pushing."
exit 0
```

> 📝 **Customize:** replace the service/app loops with whatever your real project has (one Python
> package, a monorepo, a single Node app — delete what doesn't apply). The two invariants to keep are
> the branch-block at the top and "skip with a visible message, never fail silently" for tooling that
> isn't installed yet.
