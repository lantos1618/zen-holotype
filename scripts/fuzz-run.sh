#!/usr/bin/env bash
# Mutation-based crash fuzzer for the Zen compiler. Portable fallback for when AFL isn't available
# (see fuzz-afl.sh for the coverage-guided campaign). Loops: pick a random corpus seed, apply random
# byte/structure mutations, feed it to the ASan compiler under a timeout, and log anything that trips
# a sanitizer, crashes by signal, or hangs.
#
#   ./scripts/fuzz-run.sh [ITERS] [SECONDS_PER_RUN]
#   ITERS=20000 ./scripts/fuzz-run.sh          # env or positional; defaults 5000 iters, 5s/run
#
# Findings land in ./fuzz-out/crashes/ (the exact mutated input) with a matching .log (the report).
# Crashes are deduped by sanitizer signature so a thousand hits of one bug collapse to one file.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASAN="$ROOT/zen-asan"
[ -x "$ASAN" ] || "$ROOT/scripts/fuzz-build.sh" "$ASAN"

ITERS="${1:-${ITERS:-5000}}"
PER="${2:-${PER:-5}}"
OUT="$ROOT/fuzz-out"; CR="$OUT/crashes"
mkdir -p "$CR"
export ASAN_OPTIONS="detect_leaks=0:abort_on_error=1:halt_on_error=1:detect_stack_use_after_return=1"
export UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"
export PYTHONUNBUFFERED=1    # so progress lines land in a redirected log live, not at exit

mapfile -t SEEDS < <(find "$ROOT/tests/fixtures/zen" "$ROOT/examples" -name '*.zen' 2>/dev/null)
[ ${#SEEDS[@]} -gt 0 ] || { echo "no seeds"; exit 1; }

python3 "$ROOT/scripts/fuzz_mutate.py" "$ITERS" "$PER" "$CR" "$ASAN" "${SEEDS[@]}"
