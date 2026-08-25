#!/usr/bin/env bash
# THE REGRESSION TEST FOR ISSUE #765, which is about commits, not programs --
# so this cannot be a corpus/.zen file: what went wrong was that af2f9af7
# landed three features (LSP code actions, @meta M0/M1, module resolution)
# across 113 files under a subject reading `style:`, and nothing in the
# process flagged it. The guard is the gate in scripts/scope.py; what THIS
# file guards is the gate itself, against the real offender out of the log.
#
# Runs FOUR predictions written down before the first run:
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

if [ "$failures" -gt 0 ]; then
    echo "regression: $failures prediction(s) broken -- the #765 gate is not doing its job"
    exit 1
fi
echo "regression: all predictions hold -- af2f9af7 stays flagged, honest commits stay legal"
exit 0
