#!/usr/bin/env bash
# OOM / allocation-failure sweep (Angle 1).
#
# Forces each of a target's allocations to fail — one at a time — and classifies the outcome. Zen
# claims "OOM-as-value": a failed allocation should surface a clean error/value, never crash. This
# sweep finds the allocation sites where that claim breaks (null-deref, double-free, heap corruption).
#
#   scripts/alloc-fuzz/oom-sweep.sh --check <file.zen>        # sweep the COMPILER checking a program
#   scripts/alloc-fuzz/oom-sweep.sh --build <file.zen>        # sweep the COMPILER building a program
#   scripts/alloc-fuzz/oom-sweep.sh --run <binary> [args...]  # sweep a COMPILED program's own allocations
#
# Sweep shape (env overridable): dense low band 1..LOW (default 96) covers startup/first allocations;
# then STEP-strided samples up to CAP (defaults auto: full range if small, else sampled). Classes:
#   OK        rc == baseline: the failed allocation was absorbed / off the critical path
#   HANDLED   clean nonzero exit or an explicit checked panic (e.g. ".expect(...)" / "allocation failed") — OOM-as-value working
#   BUG:NULL  "null pointer dereference" — an unchecked allocation result was dereferenced
#   BUG:HEAP  glibc "double free" / "corruption" / "malloc(): ..." — a corrupted heap on the error path
#   BUG:SIG   died by signal with no clean panic line
#   BUG:HANG  still running after TMO seconds — the failure path DEADLOCKED (or spun) instead of
#             reporting. Every run is wrapped in `timeout`: without it a single hang froze the whole
#             sweep, so the one failure mode that cannot be distinguished from "still working" was also
#             the one the sweep could never report. (A panic under a held lock is exactly this class:
#             `panic` unwinds into a pool worker's catch, the lock is never released, the pool hangs.)
# Findings (BUG:*) are deduped by (class, signature) into fuzz-out/oom/findings.txt.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HERE="$ROOT/scripts/alloc-fuzz"
SHIM="$HERE/oom-shim.so"
ZEN="$ROOT/zen"
OUT="$ROOT/fuzz-out/oom"; mkdir -p "$OUT"

LOW="${LOW:-96}"; STEP="${STEP:-0}"; CAP="${CAP:-0}"; TMO="${TMO:-20}"
export MALLOC_CHECK_="${MALLOC_CHECK_:-3}"   # libc aborts on detected heap corruption / double-free
export ZENC_NO_CACHE=1                        # every compiler run re-does the full frontend (deterministic allocation profile)

[ -f "$SHIM" ] && [ "$SHIM" -nt "$HERE/oom-shim.c" ] || cc -shared -fPIC -O2 "$HERE/oom-shim.c" -ldl -o "$SHIM"
[ -x "$ZEN" ] || { echo "build ./zen first (make)"; exit 1; }

mode="${1:-}"; shift || true
case "$mode" in
  --check) CMD=("$ZEN" check "$1") ;;
  --build) CMD=("$ZEN" build "$1" -o /tmp/oom-sweep.bin) ;;
  --run)   CMD=("$@") ;;
  *) grep '^#' "$0" | sed 's/^# \?//'; exit 1 ;;
esac
[ ${#CMD[@]} -gt 0 ] || { echo "no target"; exit 1; }

# baseline (no injection) rc, and the injectable allocation count.
timeout "$TMO" "${CMD[@]}" >/dev/null 2>&1; base=$?
total=$(ZALLOC_COUNT=1 LD_PRELOAD="$SHIM" timeout "$TMO" "${CMD[@]}" 2>&1 >/dev/null | grep -oE 'ZALLOC_TOTAL=[0-9]+' | cut -d= -f2)
total="${total:-0}"
echo "target: ${CMD[*]}   (per-run timeout ${TMO}s)"
echo "baseline rc=$base   injectable allocations=$total"

# build the list of N to try: dense 1..min(LOW,total), then strided samples.
[ "$CAP" -gt 0 ] && top=$CAP || top=$total
Ns=(); n=1; while [ $n -le $LOW ] && [ $n -le $total ]; do Ns+=($n); n=$((n+1)); done
if [ "$STEP" -eq 0 ]; then [ $top -gt $LOW ] && STEP=$(( (top-LOW)/400 + 1 )) || STEP=1; fi
n=$((LOW+1)); while [ $n -le $top ]; do Ns+=($n); n=$((n+STEP)); done

findings="$OUT/findings.txt"; : > "$findings"
declare -A seen
ok=0 handled=0 bug=0 nsig=0
for N in "${Ns[@]}"; do
  out=$(FAIL_AT=$N LD_PRELOAD="$SHIM" timeout "$TMO" "${CMD[@]}" 2>&1 >/dev/null); rc=$?
  line=$(printf '%s\n' "$out" | grep -iE 'panic|corrupt|double free|malloc\(\)|free\(\)|sanitizer' | head -1)
  if [ $rc -eq 124 ]; then cls=BUG:HANG; line="no exit within ${TMO}s (deadlock?)${line:+ :: $line}"
  # "null pointer dereference" (zenrt.c's SIGSEGV guard) is an UNCHECKED result being dereferenced — a
  # bug. "null pointer deref" (assert_nonnull's own panic, c_expr.zen) is the program CHECKING and aborting
  # on purpose. The two differ by four characters, so an un-anchored match filed every assert_nonnull as
  # BUG:NULL; require the full word.
  elif printf '%s' "$line" | grep -qi 'null pointer dereference'; then cls=BUG:NULL
  elif printf '%s' "$line" | grep -qiE 'double free|corrupt|malloc\(\)|free\(\)'; then cls=BUG:HEAP
  # `sanitizer` was in the EXTRACTION alternation above but in no classification branch: its only
  # effect was to make $line non-empty, which disqualified BUG:SIG and dropped an ASan abort into
  # HANDLED — i.e. "OOM-as-value working". A sanitizer report is a bug, and so is any signal exit.
  elif printf '%s' "$line" | grep -qi 'sanitizer'; then cls=BUG:SAN
  elif [ $rc -ge 128 ]; then cls=BUG:SIG; line="signal rc=$rc${line:+ :: $line}"
  elif [ $rc -eq $base ]; then cls=OK
  else cls=HANDLED
  fi
  case "$cls" in
    OK) ok=$((ok+1)) ;;
    HANDLED) handled=$((handled+1)) ;;
    BUG:*) bug=$((bug+1)); sig="${cls}::${line}"
           if [ -z "${seen[$sig]+x}" ]; then seen[$sig]=$N; nsig=$((nsig+1))
             echo "[$cls] first at FAIL_AT=$N  rc=$rc  :: $line" | tee -a "$findings"; fi ;;
  esac
done

echo "---"
echo "swept ${#Ns[@]} injection points: OK=$ok HANDLED=$handled BUG=$bug  (unique bug signatures: $nsig)"
echo "findings -> $findings"
# A sweep that injected nowhere proves nothing: LD_PRELOAD is ignored under an ASan build (see
# README), and `total` then defaults to 0, every loop runs zero times, and the script used to print
# a clean bill of health. And BUG findings — the whole point of the sweep — used to exit 0.
[ ${#Ns[@]} -gt 0 ] || { echo "FAIL: 0 injection points (LD_PRELOAD ignored? ASan build?) — nothing was swept"; exit 2; }
[ "$bug" -eq 0 ] || { echo "FAIL: $bug allocation failure(s) crashed instead of surfacing as a value"; exit 1; }
