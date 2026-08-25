#!/usr/bin/env bash
# tests/bench/leak.sh -- valgrind the built compiler over one representative
# compile (`make leak`). DEFINITE leaks only, with the two deliberate
# startup-prologue blocks (argv rows, root arena state -- both live exactly
# as long as the process) suppressed by shape in tests/bench/valgrind.supp:
# only a malloc called directly from generated `main` qualifies, so any leak
# one frame deeper is still a hard failure.
#
# THE POSITIVE CONTROL. Valgrinding a binary proves nothing about that
# binary: hand this script any ordinary executable -- a wrapper earlier on
# PATH, a stale path, a compiler built without anything in it -- and the
# run reports zero errors and exits 0 over a program valgrind never
# examined, indistinguishable from a clean tree. Silence must mean "the
# detector ran and found nothing", never "nothing was being detected", so
# the detector is made to SPEAK first: tests/bench/leak_canary/main.c is a
# known live one-frame-below-main leak compiled and run here with THIS
# script's own flag string, and both substrings in leak_canary/main.reports
# must come back before the real subject runs. A quiet canary exits 2 and
# gates nothing.
set -uo pipefail

ZEN=${1:-./zen}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)

if [ ! -x "$ZEN" ]; then
    echo "leak.sh: no executable at $ZEN (run \`make build\`)" >&2
    exit 2
fi
if ! command -v valgrind >/dev/null 2>&1; then
    echo "leak.sh: no valgrind on PATH" >&2
    exit 2
fi

WORK=$(mktemp -d "${TMPDIR:-/tmp}/zen-leak.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

# ------------------------------------------------------------------------
# the positive control
# ------------------------------------------------------------------------

CANARY=$ROOT/tests/bench/leak_canary
if [ ! -f "$CANARY/main.c" ] || [ ! -f "$CANARY/main.reports" ]; then
    echo "leak.sh: tests/bench/leak_canary/ is missing main.c or main.reports;" >&2
    echo "  without a positive control this gate proves nothing -- refusing to run" >&2
    exit 2
fi
mapfile -t WANT < <(grep -v '^[[:space:]]*#' "$CANARY/main.reports" | grep -v '^[[:space:]]*$')
if [ "${#WANT[@]}" -eq 0 ]; then
    echo "leak.sh: tests/bench/leak_canary/main.reports names no report to expect;" >&2
    echo "  a canary that asserts nothing is not a canary -- refusing to run" >&2
    exit 2
fi

cc -O0 -g "$CANARY/main.c" -o "$WORK/canary.bin" >"$WORK/canary.cc" 2>&1 || {
    cat "$WORK/canary.cc" >&2
    echo "leak.sh: the canary itself failed to compile; not gating on it" >&2
    exit 2
}

echo "leak.sh: canary -- tests/bench/leak_canary/main.c, same flags as the gate"
if ! valgrind --leak-check=full --show-leak-kinds=definite \
        --errors-for-leak-kinds=definite --error-exitcode=1 \
        --suppressions="$ROOT/tests/bench/valgrind.supp" \
        "$WORK/canary.bin" >"$WORK/canary.out" 2>"$WORK/canary.log"; then
    # The suppression file may legitimately have been widened until the
    # block no longer reports -- but then this gate's only remaining
    # failure mode is "the detector says nothing", which is exactly what
    # the canary exists to rule out. Refuse loudly rather than pass.
    echo "" >&2
    echo "leak.sh: THE CANARY IS QUIET. tests/bench/leak_canary/main.c is a known," >&2
    echo "  live leak one frame below main and valgrind did not report it under" >&2
    echo "  this script's own flags and suppressions." >&2
    echo "" >&2
    sed 's/^/  | /' "$WORK/canary.log" >&2 | tail -20
    echo "" >&2
    echo "  The usual cause is tests/bench/valgrind.supp being widened until it" >&2
    echo "  swallows leaks whose caller is NOT generated main -- at which point" >&2
    echo "  this gate cannot fail on anything and must say so instead of passing." >&2
    exit 2
fi

missing=0
for want in "${WANT[@]}"; do
    if ! grep -qF -- "$want" "$WORK/canary.log"; then
        echo "leak.sh: the canary did not report: $want" >&2
        missing=1
    fi
done
if [ "$missing" -ne 0 ]; then
    echo "leak.sh: the canary ran but did not produce every expected substring;" >&2
    echo "  whatever this gate would have said next, its detector is unproven." >&2
    exit 2
fi
echo "leak.sh: canary reported ${#WANT[@]} expected finding(s) -- the detector is live"

# ------------------------------------------------------------------------
# the real subject
# ------------------------------------------------------------------------

mkdir -p "$WORK/src"
cp -r "$ROOT/src/std" "$WORK/src/std"
cp "$ROOT/tests/corpus/std/vec_grows_past_eight.zen" "$WORK/src/main.zen"

echo "leak.sh: $ZEN under valgrind, definite leaks only"
if valgrind --leak-check=full --show-leak-kinds=definite \
        --errors-for-leak-kinds=definite --error-exitcode=1 \
        --suppressions="$ROOT/tests/bench/valgrind.supp" \
        "$ZEN" build "$WORK/src" --emit-c -o "$WORK/out.c" \
        >"$WORK/stdout" 2>"$WORK/valgrind.log"; then
    grep -E "definitely lost|ERROR SUMMARY|suppressed:" "$WORK/valgrind.log" || true
    echo "leak.sh: clean -- no definite leaks" \
        "(startup prologue blocks suppressed by name in tests/bench/valgrind.supp)"
else
    cat "$WORK/valgrind.log" >&2
    echo "leak.sh: DEFINITE LEAK or valgrind error, see the log above" >&2
    exit 1
fi
