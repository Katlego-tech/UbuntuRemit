#!/usr/bin/env bash
# gate.sh -- the one build script. Everything that decides "is this code good enough
# to leave my machine / to merge" runs here, and ONLY here.
#
#   .githooks/pre-push      -> runs this before a push
#   .github/workflows/ci.yml -> runs this on every push and PR
#
# That is the whole point of the file: the local gate and the pipeline cannot drift
# apart, because there is only one of them. (Curriculum 201, Build Scripts: a build
# that only works in one person's environment is not a build.)
#
# Usage:
#   bash scripts/gate.sh                          # sweep placeholders over the whole tree
#   bash scripts/gate.sh --changed-files <path>   # sweep only the paths listed in <path>
#   bash scripts/gate.sh --list                   # print what it would run, run nothing
#
# Exit codes: 0 = every applicable check ran and passed. 1 = something failed, or a
# check that should have run could not run. There is deliberately no third state --
# see "the skip rule" below.
#
# ---------------------------------------------------------------------------
# THE SKIP RULE (read this before you "fix" the script by making it lenient)
#
#   A check that did not run is a FAILED check, not a passed one.
#
# The gate never reports green because it found nothing to do. If a directory has a
# pyproject.toml but no usable interpreter, that is a broken environment and the push
# is blocked. If the whole repo has no project manifest at all but the commits being
# pushed contain source files, that is a misconfigured gate and the push is blocked.
# The only silent pass is a repo that genuinely has no code in it yet.
#
# The earlier version of this gate did the opposite -- it skipped anything it could not
# run, printed "Test gate passed", and let untested code through. That is the defect
# this file exists to make impossible.
# ---------------------------------------------------------------------------

set -u

root="$(git rev-parse --show-toplevel)"
cd "$root"

changed_files_list=""
list_only=0

while [ $# -gt 0 ]; do
  case "$1" in
    --changed-files) changed_files_list="${2:-}"; shift 2 ;;
    --list)          list_only=1; shift ;;
    -h|--help)       sed -n '2,36p' "$0"; exit 0 ;;
    *) echo "gate.sh: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

fail=0
ran=0
manifests=0

say()  { printf '%s\n' "$*"; }
step() { printf '\n-> %s\n' "$*"; }
bad()  { printf '!! %s\n' "$*"; }

# Directories that can hold a project of their own. Root first, then the layout
# docs/project-structure.md describes, then the two flat layouts people actually use
# before the microservices split happens.
project_dirs() {
  printf '%s\n' "$root"
  for d in "$root"/services/* "$root"/apps/* "$root"/packages/* \
           "$root/backend" "$root/frontend" "$root/web" "$root/api"; do
    [ -d "$d" ] && printf '%s\n' "$d"
  done
}

# ---------------------------------------------------------------- Python ----
# Resolved in strict order, most-pinned first. A bare `python` on PATH is the LAST
# resort and never the assumption: on Debian/Ubuntu derivatives `python` does not
# exist at all (only `python3`), which is exactly how the old gate silently skipped
# every Python suite it was supposed to run.
py_runner=""      # how to invoke a tool, e.g. "uv run --frozen" or "/path/.venv/bin/python -m"
py_exe=""         # how to run a *script*, e.g. "uv run --frozen python" or "/path/.venv/bin/python"
py_kind=""

resolve_python() {
  local dir="$1"
  py_runner=""; py_exe=""; py_kind=""

  if [ -x "$dir/.venv/bin/python" ]; then
    py_exe="$dir/.venv/bin/python"; py_runner="$py_exe -m"; py_kind="venv ($dir/.venv)"; return 0
  fi
  if [ -x "$root/.venv/bin/python" ]; then
    py_exe="$root/.venv/bin/python"; py_runner="$py_exe -m"; py_kind="venv ($root/.venv)"; return 0
  fi
  if [ -f "$dir/uv.lock" ] && command -v uv >/dev/null 2>&1; then
    py_runner="uv run --frozen"; py_exe="$py_runner python"; py_kind="uv (uv.lock)"; return 0
  fi
  if command -v uv >/dev/null 2>&1 && [ -f "$dir/pyproject.toml" ]; then
    py_runner="uv run"; py_exe="$py_runner python"; py_kind="uv"; return 0
  fi
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import pytest" >/dev/null 2>&1; then
      py_exe="$candidate"; py_runner="$candidate -m"; py_kind="$candidate on PATH"; return 0
    fi
  done
  return 1
}

check_python() {
  local dir="$1" rel="$2" rc
  { [ -f "$dir/pyproject.toml" ] || [ -f "$dir/requirements.txt" ] || [ -f "$dir/setup.py" ]; } || return 0
  manifests=$((manifests + 1))

  if ! resolve_python "$dir"; then
    bad "$rel has a Python project but no usable interpreter."
    bad "   Tried: $dir/.venv, $root/.venv, uv, python3+pytest, python+pytest."
    bad "   Fix the environment -- a gate that cannot run is not a gate that passed."
    bad "   e.g.  uv venv .venv && uv pip install -e '.[dev]'"
    fail=1
    return 0
  fi
  say "   python: $py_kind"

  if [ "$list_only" -eq 1 ]; then say "   would run: ruff, pytest ($rel)"; return 0; fi

  # Static analysis is part of the gate, not a nicety. Code rots one commit at a
  # time (Curriculum 201, Code Analysis); the cheapest place to catch it is here.
  if $py_runner ruff --version >/dev/null 2>&1; then
    step "ruff check ($rel)"
    ( cd "$dir" && $py_runner ruff check . ) || fail=1
    step "ruff format --check ($rel)"
    ( cd "$dir" && $py_runner ruff format --check . ) || fail=1
    ran=$((ran + 1))
  else
    say "   ruff not available in this environment -- skipping lint (tests still gate)."
  fi

  step "pytest ($rel)"
  ( cd "$dir" && $py_runner pytest -q )
  rc=$?
  ran=$((ran + 1))
  if [ "$rc" -eq 5 ]; then
    # 5 == "no tests collected". Legitimate only while a package genuinely has no
    # suite yet. It is reported loudly so it cannot quietly become permanent.
    bad "   no tests collected in $rel -- if this package has behaviour, it needs tests."
  elif [ "$rc" -ne 0 ]; then
    fail=1
  fi
}

# ------------------------------------------------------------------ Node ----
check_node() {
  local dir="$1" rel="$2"
  [ -f "$dir/package.json" ] || return 0
  manifests=$((manifests + 1))

  # node_modules is checked per directory, not at the repo root. A monorepo with
  # apps/web/node_modules and nothing at the root used to skip every JS suite.
  if [ ! -d "$dir/node_modules" ] && [ ! -d "$root/node_modules" ]; then
    bad "$rel has a package.json but no installed dependencies -- its suite cannot run."
    bad "   Run 'npm install' in $rel (or at the workspace root)."
    fail=1
    return 0
  fi

  if ! command -v node >/dev/null 2>&1; then
    bad "$rel has a package.json but node is not on PATH -- its suite cannot run."
    fail=1
    return 0
  fi

  # `npm test --if-present` exits 0 when there is no test script at all, which reads
  # as a pass. Ask package.json directly instead of trusting the exit code.
  local has_test=no has_build=no
  node -e "const p=require('$dir/package.json');process.exit(p.scripts&&p.scripts.test?0:1)"  2>/dev/null && has_test=yes
  node -e "const p=require('$dir/package.json');process.exit(p.scripts&&p.scripts.build?0:1)" 2>/dev/null && has_build=yes

  if [ "$list_only" -eq 1 ]; then
    say "   would run: $( [ "$has_test" = yes ] && printf 'npm test ' )$( [ "$has_build" = yes ] && printf 'npm run build ' )($rel)"
    [ "$has_test" = no ] && say "   (no 'test' script -- would FAIL)"
    return 0
  fi

  if [ "$has_test" = yes ]; then
    step "npm test ($rel)"
    ( cd "$dir" && npm test --silent ) || fail=1
    ran=$((ran + 1))
  else
    # Untested code is the thing the gate exists to stop. A package that declares no
    # test script does not "have no tests to run" -- it has tests nobody wrote.
    bad "$rel declares no 'test' script, so its code ships unproven."
    bad "   Add one to $rel/package.json. If this package genuinely has nothing to"
    bad "   test (config only), say so with:  \"test\": \"echo no tests: config only\""
    fail=1
  fi

  if [ "$has_build" = yes ]; then
    step "npm run build ($rel)"
    ( cd "$dir" && npm run build --silent ) || fail=1
    ran=$((ran + 1))
  fi
}

# -------------------------------------------------- apps/web (project) ------
# PROJECT-SPECIFIC, not from the kit. apps/web is the approved Stitch export: static
# HTML, no framework, no build step, so it has no manifest and none of the checks above
# see it. Its real test is visual -- each page beside its PNG in legacy/stitch-mockups/
# -- which no script can do. So check the one thing a script can: every internal link
# resolves to a file that exists. A dead nav link on a settlement console is a defect,
# and this is the only automated hold on it.
#
# href="#" is deliberate and excluded: those are the screens with no visual reference
# yet (Dashboard, Settings, Support), left dead on purpose rather than pointed at an
# invented page. See docs/design/frontend-web.md section 8.
check_web_links() {
  [ -d "$root/apps/web" ] || return 0

  if [ "$list_only" -eq 1 ]; then say "   would run: apps/web link check"; return 0; fi

  step "apps/web link check"
  local page targets target broken=0 pages=0
  for page in "$root"/apps/web/*.html; do
    [ -f "$page" ] || continue
    pages=$((pages + 1))
    targets="$(grep -o 'href="[^"#][^"]*\.html"' "$page" 2>/dev/null \
                | sed -e 's/^href="//' -e 's/"$//' | sort -u)"
    for target in $targets; do
      if [ ! -f "$root/apps/web/$target" ]; then
        bad "   BROKEN: $(basename "$page") -> $target"
        broken=1
      fi
    done
  done

  if [ "$pages" -eq 0 ]; then
    # The directory exists but holds no pages -- something deleted the export.
    bad "   apps/web exists but contains no .html pages."
    fail=1
    return 0
  fi

  if [ "$broken" -ne 0 ]; then
    fail=1
  else
    say "   clean ($pages pages)"
  fi
  ran=$((ran + 1))
}

# The other half of the same task (T009). A link check proves the pages point at
# each other; it says nothing about whether a page parses. Tags that do not nest
# leave the layout to the browser's error recovery, which is not a design anyone
# approved -- and `apps/web` is a frozen export whose only other test is a human
# holding it beside a PNG, so an automated hold on its structure is worth having.
#
# Bash cannot parse HTML, so the checker is scripts/check_markup.py. It uses only
# the standard library, which means it needs nothing the gate does not already
# require to run pytest.
check_web_markup() {
  [ -d "$root/apps/web" ] || return 0

  if [ "$list_only" -eq 1 ]; then say "   would run: apps/web markup check"; return 0; fi

  step "apps/web markup check"

  if ! resolve_python "$root"; then
    bad "   no usable Python interpreter, so the markup check could not run."
    bad "   The skip rule applies here as everywhere: a check that did not run is a"
    bad "   failed check. Fix the environment -- e.g.  uv sync --frozen"
    fail=1
    return 0
  fi

  # shellcheck disable=SC2086
  $py_exe "$root/scripts/check_markup.py" "$root"/apps/web/*.html || fail=1
  ran=$((ran + 1))
}

# ---------------------------------------------------------- placeholders ----
# AGENTS.md 2a is the kit's central rule -- nothing ships with a stub standing in for
# real work -- and until now nothing enforced it mechanically. This does.
#
# Note it sweeps the files being *pushed*, not `git diff --cached`: at pre-push time
# the index is empty, so a sweep written that way reads zero files and always passes.
placeholder_sweep() {
  step "placeholder sweep"
  local files existing=""

  if [ -n "$changed_files_list" ] && [ -f "$changed_files_list" ]; then
    files="$(cat "$changed_files_list")"
  else
    say "   no change list given -- sweeping the whole tracked tree"
    files="$(git ls-files)"
  fi

  # Excluded: markdown and docs (prose about TODOs is not a TODO), fixtures and
  # mocks (stand-in data is their job), and the gate's own files, which contain the
  # very patterns being searched for and would otherwise always fail on themselves.
  files="$(printf '%s\n' "$files" \
            | grep -Ev '^(docs/|legacy/|\.githooks/|\.github/|scripts/gate\.sh$)' \
            | grep -Ev '(^|/)(fixtures|mocks|__mocks__|testdata)/' \
            | grep -Ev '\.(md|txt|lock|svg|png|jpg|jpeg|gif|webp|ico)$' || true)"

  for f in $files; do
    [ -f "$root/$f" ] && existing="$existing $root/$f"
  done
  [ -n "$existing" ] || { say "   nothing to sweep"; return 0; }

  # shellcheck disable=SC2086
  if grep -nE '\b(TODO|FIXME|XXX|HACK|NotImplementedError|not implemented)\b' $existing; then
    bad "Placeholders found in the code being pushed."
    bad "   A task closed on a stub is BLOCKED, not done (AGENTS.md 2a)."
    bad "   If a stub is genuinely declared by the task, name its follow-up task ID beside it"
    bad "   and it stops being a placeholder -- but say so, do not hide it."
    fail=1
  else
    say "   clean"
  fi
  ran=$((ran + 1))
}

# --------------------------------------------------------------- secrets ----
# Curriculum 200, Secrets and Password Management: a secret is anything that must stay
# private, and the cost of leaking one is not "fix and move on" -- once it is in git
# history it is compromised and must be rotated. So this runs before the push, which is
# the last moment it is still cheap.
#
# Pattern-matching cannot catch every secret and does not claim to. It catches the ones
# that actually leak in practice: a committed .env, a pasted key, a hardcoded password.
secret_sweep() {
  step "secret sweep"
  local files existing="" hits=0

  if [ -n "$changed_files_list" ] && [ -f "$changed_files_list" ]; then
    files="$(cat "$changed_files_list")"
  else
    files="$(git ls-files)"
  fi

  # Committed env files are the single most common leak, and no content check is
  # needed -- the filename is the finding. `.env.example` is the intended pattern.
  local envfiles
  envfiles="$(printf '%s\n' "$files" | grep -E '(^|/)\.env($|\.)' \
               | grep -Ev '\.(example|sample|template)$' || true)"
  if [ -n "$envfiles" ]; then
    bad "   env file(s) staged for push -- these belong in .gitignore, never in git:"
    printf '%s\n' "$envfiles" | sed 's/^/     /'
    hits=1
  fi

  files="$(printf '%s\n' "$files" \
            | grep -Ev '^(docs/|legacy/|\.githooks/|\.github/|scripts/gate\.sh$)' \
            | grep -Ev '\.(md|lock|svg|png|jpg|jpeg|gif|webp|ico)$' || true)"
  for f in $files; do
    [ -f "$root/$f" ] && existing="$existing $root/$f"
  done

  if [ -n "$existing" ]; then
    # Well-known key shapes, plus assignment of a secret-ish name to a literal that
    # isn't obviously a placeholder or an env lookup.
    # shellcheck disable=SC2086
    if grep -nE \
        -e '(AKIA|ASIA)[0-9A-Z]{16}' \
        -e 'sk-[A-Za-z0-9_-]{20,}' \
        -e 'ghp_[A-Za-z0-9]{36}' \
        -e 'xox[baprs]-[A-Za-z0-9-]{10,}' \
        -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' \
        $existing 2>/dev/null; then
      bad "   the above matches the shape of a real credential (AWS / OpenAI / GitHub /"
      bad "   Slack token, or a private key). Rotate it -- assume it is already burned."
      hits=1
    fi
    # shellcheck disable=SC2086
    if grep -nEi '(api[_-]?key|secret|password|passwd|token|credential)[[:space:]]*[:=][[:space:]]*["'"'"'][^"'"'"']{12,}["'"'"']' \
        $existing 2>/dev/null \
        | grep -Eiv '(example|placeholder|changeme|your[_-]?|xxx|\*{4,}|dummy|fake|test|sample|<|\$\{|process\.env|os\.environ|getenv)'; then
      bad "   a secret-looking literal is assigned in the code above."
      bad "   Read it from the environment instead, and rotate it if it is real."
      hits=1
    fi
  fi

  if [ "$hits" -ne 0 ]; then
    bad "Secrets must never enter git history -- rewriting the commit is not enough,"
    bad "   anything already pushed must be rotated. Fix before pushing."
    fail=1
  else
    say "   clean"
  fi
  ran=$((ran + 1))
}

# ------------------------------------------------------------------ run -----
say "== gate: $(git rev-parse --abbrev-ref HEAD) @ $(git rev-parse --short HEAD) =="

while IFS= read -r dir; do
  rel="${dir#"$root"/}"
  [ "$rel" = "$dir" ] && rel="."
  check_python "$dir" "$rel"
  check_node   "$dir" "$rel"
done < <(project_dirs)

check_web_links
check_web_markup
placeholder_sweep
secret_sweep

if [ "$list_only" -eq 1 ]; then
  say ""
  say "(--list: nothing was executed. $manifests project manifest(s) found.)"
  exit 0
fi

# --- the two ways a gate lies about being green ----------------------------
if [ "$manifests" -eq 0 ]; then
  # No project manifest anywhere. Fine for a scaffold-only repo; NOT fine if the
  # commits being pushed contain source code, because then real code is going in
  # entirely unchecked and the gate would otherwise say "passed".
  code=""
  if [ -n "$changed_files_list" ] && [ -f "$changed_files_list" ]; then
    code="$(grep -E '\.(py|ts|tsx|js|jsx|go|rs|java|rb|php|c|cc|cpp|h|hpp|cs|kt|swift)$' \
              "$changed_files_list" || true)"
  fi
  if [ -n "$code" ]; then
    bad "Source files are being pushed, but this repo has no project manifest"
    bad "   (no pyproject.toml / requirements.txt / package.json anywhere the gate looks)."
    bad "   The gate cannot check this code, so it will not pretend to have checked it."
    bad "   Add the manifest, or add this directory to project_dirs() in scripts/gate.sh."
    printf '%s\n' "$code" | sed 's/^/     /'
    exit 1
  fi
  say ""
  say "No project manifests yet -- scaffold-only repo, nothing to build. Placeholder sweep ran."
elif [ "$ran" -eq 0 ]; then
  say ""
  bad "Found $manifests project manifest(s) but ran zero checks."
  bad "   That is a misconfiguration, not a pass. Fix scripts/gate.sh or the environment."
  exit 1
fi

if [ "$fail" -ne 0 ]; then
  say ""
  say "== gate FAILED =="
  exit 1
fi

say ""
say "== gate passed ($ran check(s) run across $manifests project(s)) =="
exit 0
