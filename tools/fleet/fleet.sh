#!/bin/bash
# tools/fleet/fleet.sh — the three system calls `fleet.zen` cannot make.
#
# THIS SCRIPT MAKES NO DECISIONS. It does not know what a work list is, what
# success means, how many tries a job gets or how long to back off — all of
# that is in `fleet.zen`, which writes the lane list this reads and is called
# back into after every round. What is left here is exactly the part of a
# fleet runner Zen has no way to say today:
#
#     fork/exec       `xargs -P` below. `std.env.Env` has no process
#                     capability and there is no ffi (#748, #749); the C a
#                     Zen program emits includes no <unistd.h>.
#     wait on N       `xargs -P` again. `env.threads.spawn` does not lower
#                     (#750), so N-concurrency has no in-language spelling.
#     a timeout       `timeout(1)`. No alarm, no signal, no deadline.
#     the box lock    `flock` around the critical section (#752).
#     the clock       `date +%s` into t0/t1, which `fleet report` reads and
#                     formats, because `Env` has no clock (#751).
#
# If this file ever shrinks to nothing, Zen grew a process capability.
#
#   usage: tools/fleet/fleet.sh <worklist> <state> <lanes> [max-tries]
#
#   FLEET_CMD      the agent invocation; the prompt TEXT is appended as one
#                  argument. Default echoes, so a dry run is harmless.
#   FLEET_TIMEOUT  seconds a lane may take (default 2400)
#   FLEET_GATE     a command run once per round inside the box lock — this is
#                  the `make test` that only one of ~180 agents may run at a
#                  time. Empty means no critical section.
#   FLEET_LOCK     the lock file that serialises it (default /tmp/fleet.lock)
set -u

SELF=$(readlink -f "$0")
HERE=$(dirname "$SELF")
FLEET=${FLEET_BIN:-$HERE/../../build/fleet/fleet}

# --- the lane. xargs hands it the four fields of one lane list line. ---
if [ "${1:-}" = "--lane" ]; then
    name=$2; prompt=$3; target=$4; wait=$5
    # The backoff is fleet.zen's number, not this script's.
    [ "$wait" -gt 0 ] && sleep "$wait"
    timeout "${FLEET_TIMEOUT:-2400}" \
        ${FLEET_CMD:-echo no-FLEET_CMD-set} "$(cat "$prompt" 2>/dev/null)" \
        > "$FLEET_STATE/$name.log" 2>&1
    # THE EXIT CODE IS DELIBERATELY DISCARDED. A lane that did nothing also
    # exits 0 — that is why `fleet judge` compares the target's bytes against
    # the baseline instead of believing this number. `$target` is named here
    # only so the lane list line is self-describing to a reader.
    exit 0
fi

LIST=${1:?worklist}
STATE=${2:?state directory}
N=${3:?lane width}
K=${4:-5}
export FLEET_STATE=$STATE

mkdir -p "$STATE"
[ -x "$FLEET" ] || { echo "fleet.sh: no $FLEET — run \`make fleet\`" >&2; exit 2; }

"$FLEET" plan "$LIST" "$STATE" || exit $?
date +%s > "$STATE/t0.txt"

round=0
while [ -s "$STATE/lanes.txt" ]; do
    round=$((round + 1))
    echo "[fleet] round $round: $(wc -l < "$STATE/lanes.txt") lane(s), $N wide"
    xargs -a "$STATE/lanes.txt" -P "$N" -n 4 "$SELF" --lane
    if [ -n "${FLEET_GATE:-}" ]; then
        echo "[fleet] round $round: waiting for the box lock"
        flock "${FLEET_LOCK:-/tmp/fleet.lock}" \
            bash -c "$FLEET_GATE" >> "$STATE/gate.log" 2>&1
    fi
    "$FLEET" judge "$LIST" "$STATE" "$K"
    # 2 is "I could not check" — a missing baseline, not a failed job. Another
    # round would ask the same unanswerable question, so stop and say so.
    [ $? -eq 2 ] && break
done

date +%s > "$STATE/t1.txt"
"$FLEET" report "$LIST" "$STATE"
