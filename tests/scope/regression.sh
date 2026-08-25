#!/usr/bin/env bash
# THE REGRESSION TEST FOR ISSUE #765, which is about commits, not programs --
# so this cannot be a corpus/.zen file: what went wrong was that af2f9af7
# landed three features (LSP code actions, @meta M0/M1, module resolution)
# across 113 files under a subject reading `style:`, and nothing in the
# process flagged it. The guard is the gate in scripts/scope.py; what THIS
# file guards is the gate itself, against the real offender out of the log.
#
# Runs FIVE predictions written down before the first run:
#   A. scope.py flags af2f9af7 (exit 1), naming BOTH kinds of contraband --
#      the src/ file added inside a declared sweep and the rewritten
#      .expected files.
#   B. an honestly scoped commit passes -- f1f66060, `std:` touching only
#      src/std/, on main's own log.
#   C. a sweep that lands alone passes -- d9a65c6b, `fmt:` modifying src/
#      only -- sweeps are legal, smuggling is not.
#   D. the gate is WIRED IN -- `make test` runs it -- because a check
#      outside make test goes stale unobserved (the Makefile's own
#      grammar-test/bench-allocs story).
#   E. the #791 rules: a DELETED or RENAMED .expected IS contraband inside
#      a sweep (`status in "AM"` was a substring test that let D and R
#      through), and make scope's empty-range branch audits the tip rather
#      than announcing nothing is being proposed.
# Without the gate this exits 2 (harness could not run -- never a pass); on a
# mutated gate it exits 1 here and `make scope` goes red.
#
# Exit codes follow the house convention (docs/STYLE.md): 0 pass, 1 violation,
# 2 could not run.

set -u
cd "$(dirname "$0")/../.."

REV_BAD=af2f9af7826506c73b30e735e32c079330f2a625   # the issue #765 offender

if [ ! -f scripts/scope.py ]; then
    echo "regression: scripts/scope.py missing -- the #765 gate is gone"
    exit 2
fi
if ! git rev-parse -q --verify "$REV_BAD" >/dev/null; then
    echo "regression: $REV_BAD not in this clone (shallow?) -- cannot run"
    exit 2
fi

failures=0
check() { # check <name> <predicted> <actual>
    if [ "$2" = "$3" ]; then
        echo "PASS $1"
    else
        echo "FAIL $1 (predicted $2, got $3)"
        failures=$((failures + 1))
    fi
}

out=$(python3 scripts/scope.py "$REV_BAD" 2>&1); rc=$?
check "A.offender-flagged(exit=1)"        "1" "$rc"
# Matched as FINDING LINES, not by bare substrings: the gate's static advice
# footer mentions .expected too, and "lsp_action.zen" appears in any output,
# so a substring match would pass even with the rule deleted (found by
# mutating the gate -- the test must go red when the rule goes).
case "$out" in *"lsp_action.zen (added inside a sweep)"*) a=yes ;; *) a=no ;; esac
check "A.names-added-src-file"            "yes" "$a"
case "$out" in *"(expectation changed inside a sweep)"*) b=yes ;; *) b=no ;; esac
check "A.names-expectation-diffs"         "yes" "$b"

out=$(python3 scripts/scope.py f1f66060 2>&1); rc=$?
check "B.scoped-commit-passes(exit=0)"    "0" "$rc"

out=$(python3 scripts/scope.py d9a65c6b 2>&1); rc=$?
check "C.lonely-sweep-passes(exit=0)"     "0" "$rc"

# D. THE WIRING PREDICTION. A/B/C pin the gate's RULES; this one pins the
# WIRING -- the exact disease the Makefile documents for grammar-test and
# bench-allocs: a check outside `make test` is a check nobody runs, so it
# goes stale unobserved. Drop `scope` from the `test:` prerequisite line and
# the gate keeps passing standalone right up until nothing ever audits
# another commit. Predicted before the first run, from the issue's ask.
if grep -Eq '^test:.*\bscope\b' Makefile; then
    echo "PASS D.make-test-runs-the-gate"
else
    echo "FAIL D.make-test-runs-the-gate (predicted 'scope' on the test: prerequisites, got none)"
    failures=$((failures + 1))
fi

# E. THE #791 PREDICTIONS. The gate's own fixtures pin its table; these call
# the functions directly so a regression in the RULES (not just the table)
# goes red here. The first three take the statuses diff-tree actually emits:
# D and R were exactly the ones `status in "AM"` waved through, and '' is in
# "AM" too, because that was a substring test on a string.
#
# E4 exercises make scope's empty-range branch AS THE ISSUE FOUND IT: on main
# itself, where origin/main..HEAD is empty BY CONSTRUCTION. Running
# `make scope` in THIS worktree can never reach that branch -- a lane proposes
# commits over origin/main -- and would recurse besides, because make scope
# runs this file and this file would run make scope. So the check clones this
# repository SHARED (alternates: no object copies), detaches HEAD at
# origin/main, and runs the real `make scope` there: same recipe, same
# wiring, empty range by construction. SCOPE_791_EMPTY_RANGE_GUARD keeps the
# clone's own copy of this file from spawning a second clone -- one nesting
# level, no deeper.
e() { python3 - "$@" <<'PYEOF'
import importlib.util, os, shutil, subprocess, sys, tempfile
spec = importlib.util.spec_from_file_location("scope", "scripts/scope.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
which = sys.argv[1]
if which == "expected-touched":
    bad = m.sweep_contraband({"tests/corpus/x/main.expected": sys.argv[2]})
    print("yes" if bad else "no")
elif which == "empty-status":
    bad = m.sweep_contraband({"tests/corpus/x/main.expected": ""})
    print("no" if not bad else "WRONG")
elif which == "make-scope-empty-range":
    rev = subprocess.run(["git", "rev-parse", "origin/main"],
                         capture_output=True, text=True)
    if rev.returncode != 0:
        print("no-origin-main")
        raise SystemExit(0)
    tmp = tempfile.mkdtemp(prefix="scope791.")
    try:
        clone = os.path.join(tmp, "at-main")
        made = subprocess.run(["git", "clone", "--shared", "--quiet",
                               os.getcwd(), clone],
                              capture_output=True, text=True)
        if made.returncode != 0:
            print("clone-failed")
            raise SystemExit(0)
        subprocess.run(["git", "-C", clone, "checkout", "--quiet",
                        "--detach", rev.stdout.strip()],
                       capture_output=True, check=True)
        # PIN THE CLONE'S origin/main TO THE DETACHED SHA. The clone snapshots
        # its remote-tracking ref at clone time, and main moves under the test
        # on a busy box: if the snapshot lands one commit behind the sha we
        # detached at, origin/main..HEAD is NON-empty inside the clone and the
        # empty-range branch never fires -- a spurious proposes-nothing. Pinning
        # makes the range empty BY CONSTRUCTION, not by timing (#791).
        subprocess.run(["git", "-C", clone, "update-ref",
                        "refs/remotes/origin/main", rev.stdout.strip()],
                       capture_output=True, check=True)
        # HEAD detached at origin/main makes the audited range empty BY
        # CONSTRUCTION; the GATE measured is still THIS tree's -- its
        # Makefile and scripts/scope.py are overlaid, because origin/main's
        # are the unfixed ones and a guard must fail on them, not pass.
        shutil.copy("Makefile", os.path.join(clone, "Makefile"))
        shutil.copy("scripts/scope.py",
                    os.path.join(clone, "scripts/scope.py"))
        tdir = os.path.join(tmp, "tmp")
        os.makedirs(tdir)
        env = dict(os.environ, TMPDIR=tdir, SCOPE_791_EMPTY_RANGE_GUARD="1")
        out = subprocess.run(["make", "scope"], cwd=clone,
                             capture_output=True, text=True, env=env).stdout
        ok = ("auditing the tip itself" in out
              and "nothing is being proposed" not in out)
        print("audits" if ok else "proposes-nothing")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
PYEOF
}
check "E.deleted-expected-is-contraband(D)"  "yes" "$(e expected-touched D)"
check "E.renamed-expected-is-contraband(R)"  "yes" "$(e expected-touched R)"
check "E.empty-status-not-a-pass-card"       "no"  "$(e empty-status)"
case "$(uname)" in MINGW*|MSYS*) ;; *)
    if [ -n "${SCOPE_791_EMPTY_RANGE_GUARD:-}" ]; then
        : # nested inside E4's clone -- stopping here is what bounds the descent
    else
        check "E.empty-range-audits-the-tip" "audits" "$(e make-scope-empty-range)"
    fi
    ;;
esac

if [ "$failures" -gt 0 ]; then
    echo "regression: $failures prediction(s) broken -- the #765 gate is not doing its job"
    exit 1
fi
echo "regression: all predictions hold -- af2f9af7 stays flagged, honest commits stay legal"
exit 0
