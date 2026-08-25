#!/bin/sh
# tests/fixpoint_wired_into_test.sh -- pins the WIRING half of issue #761.
#
# The other half -- that scripts/fixpoint.sh ASSERTS staleness -- is proved by
# tests/fixpoint_asserts.sh (check + mutant). This file exists because the
# issue names TWO facts and only guarding one of them leaves the other able to
# regress invisibly:
#
#   1. the staleness branch printed OK and exited 0      <- asserts.sh
#   2. `fixpoint` was not a prerequisite of `make test`  <- THIS file
#
# Nothing else reads the Makefile's prerequisite line, so an edit that drops
# `fixpoint` from `test:` recreates half the issue with every gate green --
# exactly how the original hole survived: the strongest oracle in the project
# reported its most important negative result as OK because no target that can
# fail ever ran it.
#
# What is checked, against THIS tree's Makefile:
#   - `test:` declares `fixpoint` among its prerequisites;
#   - the `fixpoint:` recipe actually invokes ./scripts/fixpoint.sh, so the
#     prerequisite is not wired to a stub that cannot see a stale seed.
#
# exit 0  both halves of the wiring hold
# exit 1  the wiring regressed -- `make test` would pass with a stale seed
# exit 2  setup error; not a pass

set -u
me=fixpoint_wired_into_test

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || {
    printf '%s: cannot resolve repo root\n' "$me" >&2; exit 2; }
mk="$root/Makefile"
[ -f "$mk" ] || { printf '%s: %s is missing\n' "$me" "$mk" >&2; exit 2; }

bad=0

# 1. `test:` must declare fixpoint. Read only lines up to the first recipe
#    line (a tab), so the recipe's own mention of the word cannot satisfy us.
prereqs=$(sed -n '/^test:/,/^\t/p' "$mk" | sed '$d' | tr '\n' ' ')
case " $prereqs " in
    *" fixpoint "*|*"fixpoint"*) : ;;
    *) printf 'FAIL %s: make test does not declare fixpoint -- a stale seed\n' "$me" >&2
       printf '     would ship again under a green gate (#761, half 2)\n' >&2
       bad=1 ;;
esac

# 2. the fixpoint recipe must run the real gate, not a stub.
if ! sed -n '/^fixpoint:/,/^[^.#\t]/p' "$mk" | grep -q 'scripts/fixpoint\.sh'; then
    printf 'FAIL %s: the fixpoint target does not invoke scripts/fixpoint.sh\n' "$me" >&2
    bad=1
fi

if [ "$bad" -ne 0 ]; then exit 1; fi
printf 'ok   %s: make test runs fixpoint, and fixpoint runs the real gate\n' "$me"
exit 0
