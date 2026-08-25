#!/usr/bin/env bash
# scripts/asan_corpus.sh -- every corpus program, compiled and run under
# AddressSanitizer and UndefinedBehaviorSanitizer, with a positive control.
#
# WHAT THIS BUYS. The corpus asserts what a program PRINTS. That oracle is
# blind to a program that prints the right thing for the wrong reason:
# tests/corpus/struct-equality/str_field_compares_bytes_not_pointers read
# three answers out of freed memory for its whole life and printed exactly
# what it was supposed to (#788). A sanitizer asks a different question --
# "did this program touch memory it does not own" -- and it is the only
# oracle in the tree that can see that class at all.
#
# ------------------------------------------------------------------------
# THE CANARY, AND WHY THIS SCRIPT REFUSES TO RUN WITHOUT ONE
# ------------------------------------------------------------------------
# A sanitizer is not a property of the source. It is a property of how the
# source was BUILT, and the build can take the detector away without taking
# the flag away. At -O2 gcc inlines the callee in tests/asan-canary/main.zen,
# the stack frame ASan would have poisoned never exists, and a KNOWN LIVE
# stack-use-after-return (#785) runs clean and prints the correct answer.
# The first sweep of this corpus was built that way. It reported 698
# programs clean with that bug sitting inside it, and the only reason
# anyone found out was that the known-bad program had been injected into
# the run as a live control.
#
# So: tests/asan-canary/main.zen is compiled with the SAME $SAN_CFLAGS
# string and the SAME $ASAN_OPTIONS this script is about to hand the sweep
# -- one variable, used twice, so the control cannot drift from the thing
# it controls -- and every substring in tests/asan-canary/main.reports must
# come back. If it does not, this script exits 2 and DOES NOT RUN THE
# SWEEP. A gate that cannot detect anything must say so, not pass.
#
# It is the REPORT that is asserted and not the exit status. A program can
# exit non-zero for a dozen reasons that have nothing to do with a
# sanitizer being wired up, and every one of them would read as a healthy
# canary.
#
# ------------------------------------------------------------------------
# -fno-sanitize-recover=undefined IS LOAD-BEARING
# ------------------------------------------------------------------------
# ASan aborts on its first report, so tests/run.py sees a non-zero exit and
# calls the test failed. GCC's UBSan does NOT: it prints to stderr, ignores
# `log_path` entirely, and exits 0. run.py compares STDOUT to .expected and
# throws stderr away, so a recovering UBSan finding is invisible to the
# runner's verdict -- the gate would go green over it. Making UBSan fatal
# is how detection is decoupled from the runner: the sanitizer puts its own
# finding in the exit status instead of trusting somebody downstream to
# read its output.
#
# The corpus was NOT clean under this until #789 was fixed. 191 of 698
# programs reported `memcpy(dst, NULL, 0)` out of `Arena.realloc`, which is
# what every Vec and every String does the first time it grows. At that
# rate a real finding is invisible, which is why a suppressions file would
# have been the wrong answer -- it would have silenced the class, and the
# class had two more members in it (see that commit).
#
# ------------------------------------------------------------------------
# COST, measured on 16 cores at -j8: 87s sanitized against 71s plain, for
# 699 programs. Cost is not why this is not in `make test`; it is out
# because ASan's shadow map wants ~20x the address space and a loaded box
# running several of these at once will start killing things.
# ------------------------------------------------------------------------
#
# Usage:
#     scripts/asan_corpus.sh                  # ./zen, -j$(nproc)
#     ZEN=build/zen scripts/asan_corpus.sh
#     SAN_CFLAGS='... -O2 ...' scripts/asan_corpus.sh   # watch it refuse
#
# Exit codes, and they mean what tests/run.py's mean:
#     0  every corpus program ran clean under both sanitizers
#     1  a program reported -- a real finding, or a real regression
#     2  the gate could not run: no compiler, no canary, a quiet canary,
#        or a selection that matched nothing. 2 IS NOT A PASS.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
ZEN=${ZEN:-$ROOT/zen}
CC=${CC:-cc}
JOBS=${JOBS:-$(nproc 2>/dev/null || echo 4)}

# ONE STRING, USED TWICE. The canary below and the sweep at the bottom are
# handed this same variable; that is the whole mechanism by which the
# control controls anything. Override it to demonstrate the refusal.
SAN_CFLAGS=${SAN_CFLAGS:-"-std=c11 -O0 -g -fsanitize=address,undefined -fno-sanitize-recover=undefined"}

# detect_leaks=0 because LeakSanitizer fires on EVERY program in the
# corpus: a Zen program's arena is process-lifetime by design and is never
# handed back, so `println("hi")` alone reports 16 bytes still reachable.
# Leaks have their own gate -- `make asan` and `make leak`, which know
# which startup blocks are deliberate. This one is about memory a program
# touches that it does not own.
export ASAN_OPTIONS=${ASAN_OPTIONS:-detect_leaks=0}

if [ ! -x "$ZEN" ]; then
    echo "asan_corpus.sh: no executable at $ZEN (run \`make build\`)" >&2
    exit 2
fi
if ! command -v "$CC" >/dev/null 2>&1; then
    echo "asan_corpus.sh: no C compiler on PATH: $CC" >&2
    exit 2
fi

WORK=$(mktemp -d "${TMPDIR:-/tmp}/zen-asan-corpus.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

# ------------------------------------------------------------------------
# the canary
# ------------------------------------------------------------------------

CANARY=$ROOT/tests/asan-canary
if [ ! -f "$CANARY/main.zen" ] || [ ! -f "$CANARY/main.reports" ]; then
    echo "asan_corpus.sh: tests/asan-canary/ is missing main.zen or main.reports;" >&2
    echo "  without a positive control this sweep proves nothing -- refusing to run" >&2
    exit 2
fi

# The expectation file must actually expect something. An empty ledger
# read as "nothing to check" is how a gate goes vacuous by deletion.
mapfile -t WANT < <(grep -v '^[[:space:]]*#' "$CANARY/main.reports" | grep -v '^[[:space:]]*$')
if [ "${#WANT[@]}" -eq 0 ]; then
    echo "asan_corpus.sh: tests/asan-canary/main.reports names no report to expect;" >&2
    echo "  a canary that asserts nothing is not a canary -- refusing to run" >&2
    exit 2
fi

# Staged exactly the way tests/run.py stages a corpus test: a root holding
# `std` and the program as main.zen, so a module path resolves inside the
# staging directory and never out into the filesystem.
mkdir -p "$WORK/canary"
ln -s "$ROOT/src/std" "$WORK/canary/std"
cp "$CANARY/main.zen" "$WORK/canary/main.zen"

echo "asan_corpus.sh: canary -- tests/asan-canary/main.zen (#785), same flags as the sweep"
"$ZEN" build "$WORK/canary" --entry main.zen --emit-c -o "$WORK/canary.c" >"$WORK/canary.build" 2>&1
if [ $? -ne 0 ]; then
    cat "$WORK/canary.build" >&2
    echo "asan_corpus.sh: the canary no longer compiles -- fix it or replace it," >&2
    echo "  but do not run a sweep whose detector is unproven" >&2
    exit 2
fi

# shellcheck disable=SC2086
$CC $SAN_CFLAGS -w "$WORK/canary.c" -o "$WORK/canary.bin" >"$WORK/canary.cc" 2>&1
if [ $? -ne 0 ]; then
    cat "$WORK/canary.cc" >&2
    echo "asan_corpus.sh: the C compiler rejected the canary with SAN_CFLAGS=$SAN_CFLAGS" >&2
    exit 2
fi

"$WORK/canary.bin" >"$WORK/canary.out" 2>"$WORK/canary.err"
canary_code=$?

missing=0
for want in "${WANT[@]}"; do
    if ! grep -qF -- "$want" "$WORK/canary.err"; then
        echo "asan_corpus.sh: the canary did not report: $want" >&2
        missing=1
    fi
done

if [ "$missing" -ne 0 ]; then
    echo "" >&2
    echo "asan_corpus.sh: THE CANARY IS QUIET. tests/asan-canary/main.zen is a known," >&2
    echo "  live, unfixed memory error (#785) and this build of it did not report." >&2
    echo "  Whatever this sweep would have printed next, it would have printed with" >&2
    echo "  or without a bug in the tree, so it is not being run." >&2
    echo "" >&2
    echo "  SAN_CFLAGS = $SAN_CFLAGS" >&2
    echo "  ASAN_OPTIONS = $ASAN_OPTIONS" >&2
    echo "  canary exit = $canary_code" >&2
    echo "  canary stdout = $(head -c 200 "$WORK/canary.out")" >&2
    echo "  canary stderr = $(head -c 400 "$WORK/canary.err")" >&2
    echo "" >&2
    echo "  The usual cause is optimisation: at -O2 the frame ASan would poison is" >&2
    echo "  inlined away and this program prints the RIGHT answer. Keep -O0. The" >&2
    echo "  other cause is that #785 got fixed, in which case retire the canary" >&2
    echo "  deliberately and write down what replaced it." >&2
    exit 2
fi

echo "asan_corpus.sh: canary reported ${#WANT[@]} expected finding(s) -- the detector is live"

# ------------------------------------------------------------------------
# the sweep
# ------------------------------------------------------------------------

# run.py's own contract: exit 2 for a selection that matched nothing, which
# is this gate's empty-input rule already enforced one level down.
mkdir -p "$WORK/tests"
echo "asan_corpus.sh: sweeping corpus/* at -j$JOBS with $SAN_CFLAGS"
TMPDIR="$WORK/tests" CFLAGS="$SAN_CFLAGS" \
    "${PYTHON:-python3}" "$ROOT/tests/run.py" \
    --zen "$ZEN" --cc "$CC" --filter 'corpus/*' --jobs "$JOBS" \
    >"$WORK/sweep.log" 2>&1
sweep_code=$?
cat "$WORK/sweep.log"

if [ "$sweep_code" -eq 0 ]; then
    echo "asan_corpus.sh: clean"
    exit 0
fi

# ------------------------------------------------------------------------
# WHAT THE RUNNER CANNOT TELL YOU. run.py compares stdout to .expected, so
# an ASan abort reaches it as "stdout does not match .expected (got 0
# bytes)" and the actual report -- the file, the line, the frame that freed
# it -- is on a stderr it discarded. Every failure gets re-run here with
# its work directory kept, so the finding is printed as a finding.
# ------------------------------------------------------------------------
mapfile -t failed < <(sed -n 's/^FAIL \([^:]*\):.*/\1/p' "$WORK/sweep.log")
if [ "${#failed[@]}" -eq 0 ]; then
    echo "asan_corpus.sh: run.py exited $sweep_code with no FAIL line -- harness error, above" >&2
    exit "$sweep_code"
fi

echo ""
echo "========================================================================"
echo "sanitizer output for ${#failed[@]} failing program(s)"
echo "========================================================================"
for id in "${failed[@]}"; do
    keep="$WORK/keep/$id"
    mkdir -p "$keep"
    TMPDIR="$keep" CFLAGS="$SAN_CFLAGS" \
        "${PYTHON:-python3}" "$ROOT/tests/run.py" \
        --zen "$ZEN" --cc "$CC" --filter "$id" --jobs 1 --keep \
        >/dev/null 2>&1
    prog=$(find "$keep" -type f -name prog -perm -u+x 2>/dev/null | head -1)
    echo ""
    echo "--- $id"
    if [ -z "$prog" ]; then
        echo "    (no binary was produced -- the compile itself failed; see above)"
        continue
    fi
    "$prog" >/dev/null 2>"$keep/err"
    echo "    exit $?"
    sed 's/^/    | /' "$keep/err" | head -30
done

exit "$sweep_code"
