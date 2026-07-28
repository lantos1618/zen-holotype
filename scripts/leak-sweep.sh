#!/usr/bin/env bash
# The examples LEAK gate: build every examples/*.zen and run it under valgrind, failing on any
# `definitely lost` or `indirectly lost` block.
#
# Why examples and not just fixtures: the fixture corpus and the compiler had both been swept before,
# examples never had been, and half of them leaked — including one 47 KB VM and one stdlib bug
# (`std.io.stdin.read_all`'s buffer) that every stdin-reading program inherited. Examples are the code
# newcomers copy, so a leak here propagates by hand.
#
# WHAT COUNTS. `definitely lost` (no pointer to the block survives) and `indirectly lost` (the block is
# only reachable through a definitely-lost one — ignoring it would let a whole object graph disappear
# behind a single leaked root). `still reachable` does NOT count: std.text.fmt deliberately keeps a
# permanent ~21-byte thread-local digit scratch, and the actor pool keeps runtime state, both live at
# exit by design. valgrind's ERROR SUMMARY counts too — this gate exists to make programs free things,
# and the way that goes wrong is a double free or a use-after-free, which is worse than the leak.
#
# HOW IT FAILS CLOSED. Every step that could go wrong is a FAILURE, never a skip:
#   - valgrind not installed, or `examples/` missing            -> exit 2
#   - fewer than FLOOR examples swept (the file set collapsed)  -> exit 2
#   - an example fails to build, or the binary is not there     -> FAIL
#   - a run times out                                           -> FAIL
#   - valgrind output carries no leak verdict we can parse      -> FAIL
# The example list is read off the FILESYSTEM, so a new example is swept the day it lands; there is no
# second hand-maintained list that could drift out of step with the directory (docs/memory-audit-
# 2026-07-26.md is a list of gates that passed because exactly that had happened).
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

ZEN=${ZEN:-./zen}
# Overridable so the gate's own fail-closed behaviour is TESTABLE: point VALGRIND at a name that does
# not exist, or at a stub that prints nothing, and this script must go RED. A gate whose failure path
# cannot be exercised is a gate nobody has watched fail.
VALGRIND=${VALGRIND:-valgrind}
FLOOR=${LEAK_SWEEP_FLOOR:-11}
TIMEOUT=${LEAK_SWEEP_TIMEOUT:-120}

command -v "$VALGRIND" >/dev/null || { echo "::error::leak-sweep: '$VALGRIND' is not installed — the gate cannot run, so it does not pass"; exit 2; }
[ -d examples ] || { echo "::error::leak-sweep: no examples/ directory — the swept file set has drifted"; exit 2; }
[ -x "$ZEN" ] || { echo "::error::leak-sweep: no compiler at '$ZEN' — build it first (make -f bootstrap/Makefile)"; exit 2; }

T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
printf 'the cat sat\non the mat\nthe cat ran\n' > "$T/words.txt"
printf '{"a":{"b":["x",1,2.5,true,null]}}' > "$T/doc.json"

# Examples that CANNOT be swept, with the reason as an executable assertion rather than a comment:
# a skip is honoured only while the stated reason still holds, so this list can never quietly become
# a place to hide a leaking example.
#   dom_demo — a std.web.dom program; the C backend rejects it by design (`zen emit-js` is its target).
skip_reason_holds() {
  case "$1" in
    dom_demo) "$ZEN" build "examples/$1.zen" -o "$T/skipprobe" >"$T/skip.err" 2>&1 && return 1
              grep -Fq 'error[c-target]' "$T/skip.err" ;;
    *) return 1 ;;
  esac
}

# How each example is INVOKED: one "STDIN<TAB>ARGS" line per run. The default (EOF on stdin, no args)
# is deliberately weak — a filter handed an empty stream allocates almost nothing, and the leaks this
# gate was written for only appear once a program has real work to do. Anything that reads input gets
# real input here. STDIN leads because it is the field that is never empty: a leading empty field
# would be eaten by `read`'s IFS whitespace stripping, silently shifting args into the stdin slot.
invocations() {
  case "$1" in
    jq)        printf '%s\t%s\n' /dev/null ".a.b[1] $T/doc.json"
               printf '%s\t%s\n' "$T/doc.json" "."
               printf '%s\t%s\n' /dev/null ".nope $T/doc.json" ;;
    textproc)  printf '%s\t%s\n' /dev/null "$T/words.txt"
               printf '%s\t%s\n' /dev/null "grep cat $T/words.txt"
               printf '%s\t%s\n' "$T/words.txt" "re ^the.*t$" ;;
    wordfreq)  printf '%s\t%s\n' "$T/words.txt" "" ;;
    zvm)       printf '%s\t%s\n' /dev/null "-t"
               printf '%s\t%s\n' /dev/null "examples/zvm_demo.asm"
               printf '%s\t%s\n' /dev/null "-d examples/zvm_demo.asm" ;;
    *)         printf '%s\t%s\n' /dev/null "" ;;
  esac
}

# One run: FAIL unless valgrind reached a verdict AND that verdict is clean.
sweep_run() {
  local name=$1 bin=$2 args=$3 stdin=$4 log=$T/vg.out
  # Delete the log FIRST. A run that never starts (missing binary, unreadable stdin) leaves the
  # PREVIOUS run's log on disk, and parsing that would report someone else's clean verdict as this
  # run's pass — a gate failing open on the one path where it learned nothing.
  rm -f "$log"
  [ -x "$bin" ] || { echo "::error::leak-sweep: $name: no binary at $bin"; return 1; }
  [ -r "$stdin" ] || { echo "::error::leak-sweep: $name: unreadable stdin fixture '$stdin'"; return 1; }
  set -f    # `re ^the.*t$` and friends are patterns, not globs
  # shellcheck disable=SC2086
  timeout "$TIMEOUT" "$VALGRIND" --leak-check=full --errors-for-leak-kinds=none --num-callers=20 \
      --log-file="$log" "$bin" $args <"$stdin" >/dev/null 2>&1
  local rc=$?
  set +f
  [ "$rc" = 124 ] && { echo "::error::leak-sweep: $name [$args] timed out after ${TIMEOUT}s"; return 1; }
  [ -s "$log" ] || { echo "::error::leak-sweep: $name [$args]: '$VALGRIND' wrote no log (exit $rc) — nothing was measured"; return 1; }

  local def ind errs
  if grep -Fq 'All heap blocks were freed' "$log"; then
    def=0; ind=0
  else
    def=$(sed -n 's/.*definitely lost: \([0-9,]*\) bytes.*/\1/p' "$log" | head -1 | tr -d ,)
    ind=$(sed -n 's/.*indirectly lost: \([0-9,]*\) bytes.*/\1/p' "$log" | head -1 | tr -d ,)
  fi
  errs=$(sed -n 's/.*ERROR SUMMARY: \([0-9]*\) errors.*/\1/p' "$log" | tail -1)
  # No parseable verdict means the run told us NOTHING — that is a failure, not a pass.
  [ -n "$def" ] && [ -n "$ind" ] && [ -n "$errs" ] || {
    echo "::error::leak-sweep: $name [$args]: no leak verdict in valgrind output (exit $rc)"
    sed -n '1,25p' "$log" >&2
    return 1
  }
  [ "$def" = 0 ] && [ "$ind" = 0 ] && [ "$errs" = 0 ] && {
    printf '  ok   %-18s %s\n' "$name" "[$args]"
    return 0
  }
  echo "::error::leak-sweep: $name [$args]: definitely lost $def B, indirectly lost $ind B, $errs valgrind errors"
  grep -E 'lost in loss record|^==[0-9]+==    (at|by) ' "$log" | head -40 >&2
  return 1
}

swept=0
bad=0
for f in $(find examples -name '*.zen' | LC_ALL=C sort); do
  name=$(basename "$f" .zen)
  if skip_reason_holds "$name"; then
    printf '  skip %-18s (not a C-target program)\n' "$name"
    continue
  fi
  bin=$T/lk_$name
  if ! "$ZEN" build "$f" -o "$bin" >"$T/build.err" 2>&1; then
    echo "::error file=$f::leak-sweep: $name failed to build — the gate cannot sweep what will not compile"
    sed -n '1,15p' "$T/build.err" >&2
    bad=1
    continue
  fi
  swept=$((swept + 1))
  while IFS=$'\t' read -r stdin args; do
    sweep_run "$name" "$bin" "$args" "$stdin" || bad=1
  done < <(invocations "$name")
done

# A sweep that swept nothing would otherwise `exit 0` having proved nothing.
[ "$swept" -ge "$FLOOR" ] || { echo "::error::leak-sweep: only $swept examples swept (floor $FLOOR) — the file set collapsed"; exit 2; }
[ "$bad" = 0 ] && echo "leak-sweep: $swept examples leak-free"
exit $bad
