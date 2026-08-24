#!/bin/bash
# tools/fleet/tests/oracle.sh -- the thing that RUNS tools/fleet.
#
# `make fleet` compiled this program and stopped there, which is how a real
# bug lived in `report` from the day it was written: every job that was not
# marked done was counted as FAILED, including a job the runner had never
# looked at. Compiling proves a program parses and types. It proves nothing
# about what it answers, and this repository keeps rediscovering that a
# check nothing runs is a check that guards nothing.
#
# WHAT IT COVERS. plan, judge and report end to end over a checked-in work
# list, with three jobs standing for the three things a lane can leave
# behind: a target whose bytes changed, a target that did not, and a job
# with no baseline at all. Plus a malformed work list, which is where
# `fleet_text.zen`'s field splitting and the duplicate-name rule live.
#
# WHAT IT DOES NOT. No agent, no fork/exec, no lock and no clock -- so
# `fleet.sh` is not exercised by anything here, and neither is the round
# loop it drives. THE LANE IS THE ORACLE'S OWN `printf`: a lane that did
# something is simulated by writing to the target, which is exactly the
# only evidence `fleet judge` ever had. That substitution is honest
# precisely because the predicate is bytes-against-a-snapshot and never
# the child's exit code.
#
#   0  the run matched tools/fleet/tests/expected.txt
#   1  it did not -- the diff is printed
#   2  the harness could not run (no binary, missing fixture)
#
# 2 is NOT a pass, for the reason tests/determinism/check.sh gives: a gate
# that succeeds when it could not run reads as coverage.

set -u

progname=fleet-oracle

die() {
    printf '%s: %s\n' "$progname" "$*" >&2
    exit 2
}

here=$(dirname -- "$0")
here=$(CDPATH= cd -- "$here" && pwd) || die "cannot resolve the script directory"
root=$(CDPATH= cd -- "$here/../../.." && pwd) || die "cannot resolve the repo root"

FLEET=${FLEET_BIN:-$root/build/fleet/fleet}
[ -x "$FLEET" ] || die "no $FLEET -- run \`make fleet\`"
[ -f "$here/expected.txt" ] || die "no $here/expected.txt -- there is nothing to compare against"

tmp=$(mktemp -d) || die "cannot make a temp directory"
trap 'rm -rf "$tmp"' EXIT

cp -R "$here/prompts" "$here/targets" "$here"/*.list "$tmp/" || die "cannot stage the fixture"
mkdir -p "$tmp/state"
cd "$tmp" || die "cannot enter $tmp"

out=$tmp/actual.txt

# Every step is echoed with its exit status, because the status IS half of
# what this program promises: 2 is "I could not check" and 1 is "I checked
# and it failed", and a fixture that only diffed stdout would let those two
# swap places without a word.
step() {
    printf '$ fleet %s\n' "$*" >> "$out"
    "$FLEET" "$@" >> "$out" 2>&1
    printf 'exit %d\n\n' "$?" >> "$out"
}

step plan plan.list state

# THE LANE. `fleet.sh` would have run an agent here; the agent's only
# observable effect on a verdict is the target's bytes, so the oracle
# writes them itself. `stuck` and `never` are left alone.
printf 'a lane did something\n' >> targets/changed.txt

# max-tries 1, so `stuck` is out of tries after this single round and the
# fixture needs no second one.
step judge judge.list state 1

# The clock `Env` does not have (#751), written the way fleet.sh writes it.
# Fixed integers, so the reported wall time is the same on every machine.
printf '1000\n' > state/t0.txt
printf '1090\n' > state/t1.txt

step report judge.list state
step plan bad.list state

diff -u "$here/expected.txt" "$out" || {
    printf '%s: the run does not match expected.txt (above)\n' "$progname" >&2
    exit 1
}
printf 'fleet: oracle green -- %d step(s) over %s\n' \
    "$(grep -c '^\$ fleet ' "$out")" "$(basename "$here")"
