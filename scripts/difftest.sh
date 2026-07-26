#!/usr/bin/env bash
# scripts/difftest.sh — differential gate between two zenc binaries (module-system campaign, B4/R1).
#
#   scripts/difftest.sh OLD_ZENC NEW_ZENC
#
# For every program in the corpus it compares, OLD vs NEW:
#   check — `zenc check <entry>`: stdout+stderr bytes AND exit code
#   emit  — `zenc emit  <entry>`: emitted C stdout bytes AND exit code
#   run   — `zenc run   <entry>`: stdout bytes AND exit code (only where the fixture is runnable,
#           i.e. OLD's check accepted it; stderr is excluded so cc warnings can't flake the gate)
#
# Corpus:
#   tests/fixtures/zen/*.zen        — single-file fixtures (accepting AND rejecting programs)
#   examples/*.zen                  — single-file examples
#   tests/fixtures/dispatch/*/     — multi-module dirs, entry = <dir>/main.zen (adversarial
#                                     cross-module dispatch corpus: alias-UFCS, ambiguity,
#                                     teaching hints, dotted modules, trait defaults, …)
#
# Any stage diff is printed in a table. The gate exits nonzero when ANY diff is not listed in the
# allowlist (scripts/difftest-allow.txt): one `<case-id>:<stage>` per line, `#` comments — every
# entry is an individually justified, intentional behavior change. Per-diff artifacts (old/new
# captures) are left in the work dir printed at the end.
#
# Env: DIFFTEST_JOBS (parallel cases, default: nproc), DIFFTEST_ALLOW (allowlist path override).
# The compile cache is disabled (ZENC_NO_CACHE=1): both binaries must do the full pipeline.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OLD="${1:-}"
NEW="${2:-}"
if [ -z "$OLD" ] || [ -z "$NEW" ]; then
    echo "usage: scripts/difftest.sh OLD_ZENC NEW_ZENC" >&2
    exit 2
fi
OLD="$(readlink -f "$OLD")"
NEW="$(readlink -f "$NEW")"
ORIG_OLD="$OLD"
ORIG_NEW="$NEW"
[ -x "$OLD" ] || { echo "difftest: OLD not executable: $OLD" >&2; exit 2; }
[ -x "$NEW" ] || { echo "difftest: NEW not executable: $NEW" >&2; exit 2; }

ALLOW="${DIFFTEST_ALLOW:-$ROOT/scripts/difftest-allow.txt}"
JOBS="${DIFFTEST_JOBS:-$(nproc 2>/dev/null || echo 4)}"
WORK="$(mktemp -d /tmp/zenc-difftest.XXXXXX)"
export ZENC_NO_CACHE=1
RUN_TIMEOUT=90

# zen resolves `src/std` + `bootstrap/zenrt.c` relative to the project root (the binary's
# directory). Stage both compilers in a work root whose src/ + bootstrap/ symlink to this
# worktree's trees: both then resolve the SAME std sources, and only compiler-behavior diffs remain.
mkdir -p "$WORK/root"
ln -s "$ROOT/src" "$WORK/root/src"
ln -s "$ROOT/bootstrap" "$WORK/root/bootstrap"
cp "$OLD" "$WORK/root/zen-old"
cp "$NEW" "$WORK/root/zen-new"
OLD="$WORK/root/zen-old"
NEW="$WORK/root/zen-new"

# ── corpus ───────────────────────────────────────────────────────────────────────────────────────
# A case id is the entry path relative to the repo root (dispatch dirs: the DIRECTORY path).
CASES="$WORK/cases"
{
    for f in "$ROOT"/tests/fixtures/zen/*.zen; do echo "${f#"$ROOT"/}"; done
    for f in "$ROOT"/examples/*.zen; do echo "${f#"$ROOT"/}"; done
    for d in "$ROOT"/tests/fixtures/dispatch/*/; do
        [ -f "$d/main.zen" ] && echo "${d%/}" | sed "s|^$ROOT/||"
    done
} | sort > "$CASES"

# The globs above are NOT nullglob-guarded: an unmatched pattern expands to itself, so a renamed
# fixture directory yields the literal case id `tests/fixtures/zen/*.zen`, both binaries fail on it
# IDENTICALLY, no diff is recorded, and the gate prints "ZERO diffs" having compiled nothing. Assert
# the corpus instead: every case id must exist, and there must be a plausible number of them.
FLOOR=${DIFFTEST_FLOOR:-100}
ncases=$(wc -l < "$CASES")
[ "$ncases" -ge "$FLOOR" ] || { echo "difftest: FAIL — only $ncases cases (floor $FLOOR); the corpus globs did not match"; exit 2; }
while IFS= read -r c; do
    [ -e "$ROOT/$c" ] || { echo "difftest: FAIL — case path does not exist: $c"; exit 2; }
done < "$CASES"

# ── run-stage skips ──────────────────────────────────────────────────────────────────────────────
# These programs assert OBSERVED parallelism (workers_busy: "did >1 worker actually run?"), so their
# exit code depends on machine load — under the differ's own parallel execution they flake between
# "agreed, parallel" and "agreed, but only 1 core observed" with NO compiler diff involved. Their
# check + emit stages are still compared; only the load-sensitive run stage is skipped.
RUN_SKIP="tests/fixtures/zen/pool_colorless_driver.zen
tests/fixtures/zen/pool_typed_actors_parallel.zen
tests/fixtures/zen/pool_parallel_actors.zen
tests/fixtures/zen/pool_stress_exactly_once.zen
examples/pool_actor_demo.zen"
run_skipped() {
    echo "$RUN_SKIP" | grep -qx "$1"
}
export RUN_SKIP
export -f run_skipped

# ── one case: capture both binaries, record differing stages ─────────────────────────────────────
run_case() {
    case_id="$1"
    entry="$ROOT/$case_id"
    [ -d "$entry" ] && entry="$entry/main.zen"
    slug="$(echo "$case_id" | tr '/' '_')"
    d="$WORK/out/$slug"
    mkdir -p "$d"

    "$OLD" check "$entry" > "$d/old.check" 2>&1; echo "$?" > "$d/old.check.rc"
    "$NEW" check "$entry" > "$d/new.check" 2>&1; echo "$?" > "$d/new.check.rc"
    "$OLD" emit  "$entry" > "$d/old.emit" 2> /dev/null; echo "$?" > "$d/old.emit.rc"
    "$NEW" emit  "$entry" > "$d/new.emit" 2> /dev/null; echo "$?" > "$d/new.emit.rc"
    if run_skipped "$case_id"; then
        stages="check emit"
    elif [ "$(cat "$d/old.check.rc")" = "0" ]; then
        timeout "$RUN_TIMEOUT" "$OLD" run "$entry" < /dev/null > "$d/old.run" 2> /dev/null; echo "$?" > "$d/old.run.rc"
        timeout "$RUN_TIMEOUT" "$NEW" run "$entry" < /dev/null > "$d/new.run" 2> /dev/null; echo "$?" > "$d/new.run.rc"
        stages="check emit run"
    else
        stages="check emit"
    fi

    for st in $stages; do
        if ! cmp -s "$d/old.$st" "$d/new.$st" || ! cmp -s "$d/old.$st.rc" "$d/new.$st.rc"; then
            echo "$case_id:$st" >> "$WORK/diffs.raw"
        fi
    done
}
export ROOT OLD NEW WORK RUN_TIMEOUT
export -f run_case

mkdir -p "$WORK/out"
: > "$WORK/diffs.raw"
xargs -a "$CASES" -P "$JOBS" -I {} bash -c 'run_case "$@"' _ {}

# ── report ───────────────────────────────────────────────────────────────────────────────────────
total="$(wc -l < "$CASES")"
sort "$WORK/diffs.raw" > "$WORK/diffs"
ndiff="$(wc -l < "$WORK/diffs")"
allowed=0
blocked=0

echo ""
echo "difftest: OLD=$ORIG_OLD"
echo "          NEW=$ORIG_NEW"
echo "          $total cases (check+emit always; run where OLD accepts)"
if [ "$ndiff" -eq 0 ]; then
    echo "          ZERO diffs"
    rm -rf "$WORK"
    exit 0
fi

echo ""
printf '%-62s %-6s %s\n' "CASE" "STAGE" "STATUS"
printf '%-62s %-6s %s\n' "----" "-----" "------"
while IFS= read -r line; do
    cid="${line%:*}"
    st="${line##*:}"
    status="DIFF"
    if [ -f "$ALLOW" ] && grep -q "^$line\([[:space:]]\|\$\)" "$ALLOW" 2>/dev/null; then
        status="ALLOWED"
        allowed=$((allowed + 1))
    else
        blocked=$((blocked + 1))
    fi
    printf '%-62s %-6s %s\n' "$cid" "$st" "$status"
done < "$WORK/diffs"

echo ""
echo "difftest: $ndiff diff(s): $allowed allowed, $blocked NOT allowlisted"
echo "artifacts: $WORK/out/ (old.* / new.* per case)"
[ "$blocked" -eq 0 ] && exit 0
exit 1
