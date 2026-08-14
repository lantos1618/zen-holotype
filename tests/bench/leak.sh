#!/usr/bin/env bash
# tests/bench/leak.sh -- valgrind the built compiler over one representative
# compile (`make leak`). DEFINITE leaks only, with the two deliberate
# startup-prologue blocks (argv rows, root arena state -- both live exactly
# as long as the process) suppressed by shape in tests/bench/valgrind.supp:
# only a malloc called directly from generated `main` qualifies, so any leak
# one frame deeper is still a hard failure.
set -euo pipefail

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

WORK=$(mktemp -d /tmp/zen-leak.XXXXXX)
trap 'rm -rf "$WORK"' EXIT

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
