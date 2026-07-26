#!/usr/bin/env bash
# Run every known-good Zen program through the ASan compiler. Silent memory bugs (OOB reads,
# use-after-free, integer-UB) frequently surface just by exercising valid inputs under sanitizers,
# so this corpus pass is high-value on its own — no mutation required.
#
#   ./scripts/fuzz-corpus.sh            # builds zen-asan if missing, checks + builds the corpus
#
# Reports every input that trips a sanitizer or a signal (segv/abort). A non-sanitizer nonzero exit
# (a normal `check` rejection or type error) is NOT a finding — those are the compiler doing its job.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASAN="$ROOT/zen-asan"
# A FAILED asan build must not turn the corpus green: without $ASAN every probe exits 127 with
# "No such file or directory", which matches no sanitizer pattern and is < 128, so the sweep would
# report `N files, 0 sanitizer hits` and exit 0 having run nothing.
[ -x "$ASAN" ] || "$ROOT/scripts/fuzz-build.sh" "$ASAN" || { echo "fuzz-corpus: FAIL — could not build $ASAN"; exit 2; }
[ -x "$ASAN" ] || { echo "fuzz-corpus: FAIL — $ASAN is missing after build"; exit 2; }

# detect_leaks=0: arena allocator never frees, so leaks are expected and would bury real hits.
export ASAN_OPTIONS="detect_leaks=0:abort_on_error=1:halt_on_error=1:detect_stack_use_after_return=1"
export UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1"

corpus=$(find "$ROOT/tests/fixtures/zen" -name '*.zen' 2>/dev/null; \
         find "$ROOT/examples" -name '*.zen' 2>/dev/null)
# An empty corpus is a broken run, not a clean one — the guard fuzz-run.sh:26 already has.
[ -n "$corpus" ] || { echo "fuzz-corpus: FAIL — no corpus files found under tests/fixtures/zen or examples"; exit 2; }
hits=0 n=0
for f in $corpus; do
  n=$((n+1))
  for mode in check build; do
    out=$("$ASAN" "$mode" "$f" -o /tmp/fuzz-corpus.out 2>&1)
    rc=$?
    # Sanitizer error => "runtime error" (UBSan) or "==NNN==ERROR" (ASan); signal => rc>=128.
    if echo "$out" | grep -qE 'runtime error:|AddressSanitizer|LeakSanitizer|__asan|__ubsan' || [ $rc -ge 128 ]; then
      echo "=== SANITIZER HIT: $mode $f (rc=$rc) ==="
      echo "$out" | grep -E 'runtime error:|ERROR|SUMMARY|#[0-9]' | head -12
      hits=$((hits+1))
    fi
  done
done
echo "corpus: $n files, $hits sanitizer hits"
exit $([ $hits -eq 0 ] && echo 0 || echo 1)
