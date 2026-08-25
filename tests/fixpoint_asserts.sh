#!/bin/sh
# tests/fixpoint_asserts.sh -- proof that scripts/fixpoint.sh ASSERTS seed
# staleness instead of reporting it. Written for issue #761.
#
# On 2026-08-24 a122b99f shipped a stale seed/zen.c to main. Nothing that
# could fail said so: both branches of the staleness comparison printed
# `fixpoint: OK`, `fixpoint` was not in `make test`, and there was no CI.
# The branch now asserts (exit 1, FAILED on stderr) and `make test` runs it.
# This file exists because a green `make fixpoint` on an honest tree proves
# neither half of that sentence. It runs the gate TWICE against throwaway
# copies of this tree:
#
#   ./tests/fixpoint_asserts.sh check    the honest tree passes: exit 0,
#                                        the `seed is current` banner, no
#                                        stderr. Guards against the assert
#                                        over-firing onto every commit.
#   ./tests/fixpoint_asserts.sh mutant   the exact lie a122b99f shipped --
#                                        compiler fine, seed stale -- must
#                                        be REJECTED: nonzero exit, `is
#                                        stale` and regeneration advice on
#                                        stderr, no OK banner anywhere.
#                                        Guards against the assert silently
#                                        regressing back to reporting.
#
# THE MUTATION IS ONE TRAILING NEWLINE ON THE COPY'S seed/zen.c. Whitespace
# cannot change what the C compiles to, so every stage still agrees: stage2
# == stage3 holds and ONLY the seed-vs-stage1 comparison can notice. That
# isolation is the point -- it exercises exactly the branch the issue is
# about and nothing else in the chain.
#
#   exit 0  every requested check passed
#   exit 1  a check FAILED -- the gate reported OK on a stale seed, or
#           rejected an honest one
#   exit 2  setup error (missing tree files); not a pass
#
# Scratch lives under ${TMPDIR:-$PWD/.lane-tmp} -- never bare /tmp, whose
# zen-tests.* directories sibling lanes wipe.

set -u

progname=fixpoint_asserts

die() {
    printf '%s: %s\n' "$progname" "$*" >&2
    exit 2
}

mode=${1:-}
case $mode in
    check|mutant) ;;
    *) die "usage: tests/fixpoint_asserts.sh check|mutant" ;;
esac

here=$(dirname -- "$0")
here=$(CDPATH= cd -- "$here" && pwd) || die "cannot resolve the script directory"
root=$(CDPATH= cd -- "$here/.." && pwd) || die "cannot resolve the repo root"

for needed in scripts/fixpoint.sh seed/zen.c src/std/std.zen; do
    [ -f "$root/$needed" ] || die "$root/$needed is missing"
done

scratch_base=${TMPDIR:-$root/.lane-tmp}
mkdir -p "$scratch_base" || die "cannot create $scratch_base"
W=$(mktemp -d "$scratch_base/fxasserts.XXXXXXXX") || die "mktemp failed"
trap 'rm -rf "$W"' EXIT INT TERM

cp -r "$root/src" "$root/seed" "$root/scripts" "$W/" || die "copy failed"

if [ "$mode" = mutant ]; then
    # The lie a122b99f shipped: bytes that compile identically, so the
    # chain is sound and only the seed comparison can see them.
    printf '\n' >>"$W/seed/zen.c"
fi

cd "$W" || die "cannot enter scratch"
sh "$W/scripts/fixpoint.sh" >stdout.txt 2>stderr.txt
rc=$?

if [ "$mode" = check ]; then
    if [ "$rc" -ne 0 ]; then
        printf 'FAIL %s: honest tree rejected (exit %d)\n' "$progname" "$rc" >&2
        sed 's/^/     /' stderr.txt >&2
        exit 1
    fi
    if ! grep -q 'seed is current' stdout.txt; then
        printf 'FAIL %s: honest tree passed but without the current-seed banner:\n' "$progname" >&2
        sed 's/^/     /' stdout.txt >&2
        exit 1
    fi
    if [ -s stderr.txt ]; then
        printf 'FAIL %s: honest tree produced stderr:\n' "$progname" >&2
        sed 's/^/     /' stderr.txt >&2
        exit 1
    fi
    printf 'ok   %s: honest tree passes with the current-seed banner\n' "$progname"
    exit 0
fi

# mutant: the stale seed must be a FAILURE, loudly.
bad=0
if [ "$rc" -eq 0 ]; then
    printf 'FAIL %s: stale seed exited 0 -- the assert has regressed to a report\n' "$progname" >&2
    bad=1
fi
if ! grep -q 'seed/zen.c is stale' stderr.txt; then
    printf 'FAIL %s: stale seed not named on stderr\n' "$progname" >&2
    bad=1
fi
if ! grep -q 'Regenerate with' stderr.txt; then
    printf 'FAIL %s: no `make seed` remediation on stderr\n' "$progname" >&2
    bad=1
fi
if grep -q 'fixpoint: OK' stdout.txt stderr.txt; then
    printf 'FAIL %s: an OK banner was printed for a stale seed\n' "$progname" >&2
    bad=1
fi
[ "$bad" -eq 0 ] && printf 'ok   %s: stale seed rejected (exit %d, FAILED + remediation on stderr)\n' "$progname" "$rc"
exit "$bad"
