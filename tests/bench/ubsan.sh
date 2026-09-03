#!/usr/bin/env bash
# tests/bench/ubsan.sh -- run one representative compile through a compiler
# built with UndefinedBehaviorSanitizer.
#
# Silence is trusted only after two positive controls: the compiler binary
# must contain UBSan runtime hooks, and a signed-overflow canary built with the
# same sanitizer flags must produce the report named by ubsan_canary/main.reports.
set -euo pipefail

ZEN_UBSAN=${1:-./zen-ubsan}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)

if [ ! -x "$ZEN_UBSAN" ]; then
    echo "ubsan.sh: no executable at $ZEN_UBSAN (build zen-ubsan first)" >&2
    exit 2
fi
if ! command -v nm >/dev/null 2>&1; then
    echo "ubsan.sh: nm is required to verify compiler instrumentation" >&2
    exit 2
fi

WORK=$(mktemp -d "${TMPDIR:-/tmp}/zen-ubsan.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

if ! nm -D "$ZEN_UBSAN" 2>/dev/null | grep -Eq '__ubsan_handle_'; then
    if ! nm "$ZEN_UBSAN" 2>/dev/null | grep -Eq '__ubsan_handle_'; then
        echo "ubsan.sh: $ZEN_UBSAN has no UBSan runtime hook" >&2
        exit 2
    fi
fi

CANARY=$ROOT/tests/bench/ubsan_canary
if [ ! -f "$CANARY/main.c" ] || [ ! -f "$CANARY/main.reports" ]; then
    echo "ubsan.sh: tests/bench/ubsan_canary is missing its source or report contract" >&2
    exit 2
fi
mapfile -t WANT < <(
    grep -v '^[[:space:]]*#' "$CANARY/main.reports" |
        grep -v '^[[:space:]]*$'
)
if [ "${#WANT[@]}" -eq 0 ]; then
    echo "ubsan.sh: the canary report contract names no expected finding" >&2
    exit 2
fi

SAN_FLAGS=(
    -std=c99
    -O1
    -g
    -fno-omit-frame-pointer
    -fsanitize=undefined
    -fno-sanitize-recover=undefined
)
"${CC:-cc}" "${SAN_FLAGS[@]}" "$CANARY/main.c" -o "$WORK/canary" \
    >"$WORK/canary.cc" 2>&1 || {
    cat "$WORK/canary.cc" >&2
    echo "ubsan.sh: the positive-control canary failed to compile" >&2
    exit 2
}

export UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1
set +e
"$WORK/canary" >"$WORK/canary.log" 2>&1
canary_code=$?
set -e

missing=0
for want in "${WANT[@]}"; do
    if ! grep -qF -- "$want" "$WORK/canary.log"; then
        echo "ubsan.sh: the canary did not report: $want" >&2
        missing=1
    fi
done
if [ "$canary_code" -eq 0 ] || [ "$missing" -ne 0 ]; then
    cat "$WORK/canary.log" >&2
    echo "ubsan.sh: deliberate signed overflow was not stopped and reported" >&2
    exit 2
fi
echo "ubsan.sh: signed-overflow canary reported; the detector is live"

mkdir -p "$WORK/src"
cp -r "$ROOT/src/std" "$WORK/src/std"
cp "$ROOT/tests/corpus/std/vec_grows_past_eight.zen" "$WORK/src/main.zen"

echo "ubsan.sh: compiling corpus/std/vec_grows_past_eight under $ZEN_UBSAN"
set +e
"$ZEN_UBSAN" build "$WORK/src" --emit-c -o "$WORK/out.c" \
    >"$WORK/compiler.log" 2>&1
compiler_code=$?
set -e
cat "$WORK/compiler.log"

if grep -Eq 'runtime error:|UndefinedBehaviorSanitizer|SUMMARY: UndefinedBehaviorSanitizer' \
        "$WORK/compiler.log"; then
    echo "ubsan.sh: sanitizer finding in compiler run" >&2
    exit 1
fi
if [ "$compiler_code" -ne 0 ]; then
    echo "ubsan.sh: $ZEN_UBSAN exited $compiler_code" >&2
    exit 1
fi
if [ ! -s "$WORK/out.c" ]; then
    echo "ubsan.sh: compiler produced no C output" >&2
    exit 1
fi

echo "ubsan.sh: compiler run clean; instrumentation and positive control verified"
