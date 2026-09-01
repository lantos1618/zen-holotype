#!/usr/bin/env bash
# tests/bench/asan.sh -- run one representative compile through the
# sanitizer-built compiler (zen-asan, built by `make asan`).
#
# The program staged here is corpus/std/vec_grows_past_eight.zen: small, and
# it exercises the allocator door every generated program uses (Vec growth
# through Alloc -> Mem.page -> malloc). Staging mirrors tests/run.py: a temp
# root holding std and the program as main.zen, so the compilation root is
# the staging directory and never the filesystem.
#
# THE POSITIVE CONTROL. A clean sanitizer run is meaningful only after proving
# that this binary is instrumented and this host reports a known leak. The
# compiler no longer has a deliberate process-lifetime leak, so the control is
# separate: `nm` must find ASan's initialization hook in zen-asan, then the
# leak_canary program must produce a LeakSanitizer report under the same host.
# Only after both facts hold do we trust silence from the compiler itself.
set -euo pipefail

ZEN_ASAN=${1:-./zen-asan}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)

if [ ! -x "$ZEN_ASAN" ]; then
    echo "asan.sh: no executable at $ZEN_ASAN (run \`make asan\`)" >&2
    exit 2
fi

WORK=$(mktemp -d "${TMPDIR:-/tmp}/zen-asan.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/src"
cp -r "$ROOT/src/std" "$WORK/src/std"
cp "$ROOT/tests/corpus/std/vec_grows_past_eight.zen" "$WORK/src/main.zen"

echo "asan.sh: compiling corpus/std/vec_grows_past_eight under $ZEN_ASAN"
export ASAN_OPTIONS=detect_leaks=1

set +e
"$ZEN_ASAN" build "$WORK/src" --emit-c -o "$WORK/out.c" >"$WORK/out.log" 2>&1
code=$?
set -e
cat "$WORK/out.log"

if [ "$code" -ne 0 ]; then
    echo "asan.sh: $ZEN_ASAN exited $code" >&2
    exit 1
fi

if grep -Eq "ERROR: (AddressSanitizer|LeakSanitizer)" "$WORK/out.log"; then
    echo "asan.sh: sanitizer finding in compiler run" >&2
    exit 1
fi

if ! nm -D "$ZEN_ASAN" 2>/dev/null | grep -F '__asan_init' >/dev/null; then
    echo "asan.sh: $ZEN_ASAN has no ASan initialization hook" >&2
    exit 2
fi

"${CC:-cc}" -std=c99 -O0 -g -fsanitize=address,leak \
    "$ROOT/tests/bench/leak_canary/main.c" -o "$WORK/asan-canary"
set +e
"$WORK/asan-canary" >"$WORK/canary.log" 2>&1
canary_code=$?
set -e
if [ "$canary_code" -eq 0 ] || \
   ! grep -q "LeakSanitizer: detected memory leaks" "$WORK/canary.log"; then
    cat "$WORK/canary.log"
    echo "asan.sh: deliberate leak canary was not reported" >&2
    exit 2
fi

echo "asan.sh: compiler run clean; instrumentation hook and deliberate-leak control both present"
