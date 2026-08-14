#!/usr/bin/env bash
# scripts/profile.sh -- `make profile`. A frame-pointer build of the compiler
# (zen-fp, never clobbering ./zen) self-compiles under `perf record -g`, and
# the output lands in tests/bench/out/:
#
#   perf.data        raw recording
#   report.txt       `perf report --stdio`
#   stacks.txt       `perf script` output (unfolded)
#   flamegraph.svg   only when stackcollapse-perf.pl AND flamegraph.pl are on
#                    PATH; they are never vendored into this repo
#
# perf needs kernel permission. When it refuses, this prints the current
# /proc/sys/kernel/perf_event_paranoid value and exits 2 -- a harness that
# cannot run is not a failed profile.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

CC=${CC:-cc}
OUT=tests/bench/out
mkdir -p "$OUT"

if ! command -v perf >/dev/null 2>&1; then
    echo "profile.sh: no perf on PATH" >&2
    exit 2
fi

echo "profile.sh: building zen-fp (frame pointers, -O2 -g)"
"$CC" -O2 -fno-omit-frame-pointer -g -std=c99 seed/zen.c -o zen-fp

echo "profile.sh: perf record -g -- ./zen-fp build src --emit-c"
if ! perf record -g -o "$OUT/perf.data" -- \
        ./zen-fp build src --emit-c -o "$OUT/self-compile.c" \
        >"$OUT/record.stdout" 2>"$OUT/record.stderr"; then
    cat "$OUT/record.stderr" >&2
    paranoid=$(cat /proc/sys/kernel/perf_event_paranoid 2>/dev/null || echo "?")
    echo "profile.sh: perf record failed; /proc/sys/kernel/perf_event_paranoid" >&2
    echo "profile.sh: is $paranoid -- try: sudo sysctl kernel.perf_event_paranoid=-1" >&2
    exit 2
fi

perf report --stdio -i "$OUT/perf.data" >"$OUT/report.txt" 2>/dev/null
perf script -i "$OUT/perf.data" >"$OUT/stacks.txt" 2>/dev/null
echo "profile.sh: $OUT/report.txt and $OUT/stacks.txt written"

if command -v stackcollapse-perf.pl >/dev/null 2>&1 \
        && command -v flamegraph.pl >/dev/null 2>&1; then
    stackcollapse-perf.pl "$OUT/stacks.txt" >"$OUT/stacks.folded"
    flamegraph.pl "$OUT/stacks.folded" >"$OUT/flamegraph.svg"
    echo "profile.sh: $OUT/flamegraph.svg written"
else
    echo "profile.sh: no flamegraph (install FlameGraph and put" \
        "stackcollapse-perf.pl and flamegraph.pl on PATH)"
fi
