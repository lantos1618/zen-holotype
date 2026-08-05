#!/bin/sh
# tests/determinism/check.sh
#
# gen_c is deterministic: same input, byte-identical output. The fixpoint
# oracle in PLAN.md stage 1 is worthless without it, and nondeterminism is
# invisible until it wastes a day. See README.md for the four sources this
# is designed to catch and for the two CLI flags it requires.
#
#   0  every check passed
#   1  a check failed -- gen_c is nondeterministic
#   2  the harness could not run (no binary, missing fixture, missing flag)
#
# 2 is NOT a pass. A gate that succeeds when it cannot run reads as coverage
# and guards nothing.
#
# This script is itself deterministic: the shuffles below are three fixed
# permutations, not `shuf`. A harness that fails once and passes on rerun
# teaches you to press rerun.

set -u

progname=determinism

die() {
    printf '%s: %s\n' "$progname" "$*" >&2
    exit 2
}

note() { printf '     %s\n' "$*"; }
ok()   { passed=$((passed + 1)); printf 'ok   %s\n' "$*"; }
bad()  { failed=$((failed + 1)); printf 'FAIL %s\n' "$*"; }

passed=0
failed=0
setup_error=0

# ---------------------------------------------------------------- locate

here=$(dirname -- "$0")
here=$(CDPATH= cd -- "$here" && pwd) || die "cannot resolve the script directory"
root=$(CDPATH= cd -- "$here/../.." && pwd) || die "cannot resolve the repo root"

ZEN=${ZEN:-$root/zen}
case $ZEN in
    */*) ;;
    *)   ZEN=$(command -v -- "$ZEN" 2>/dev/null) || ZEN=${ZEN:-} ;;
esac

if [ -z "${ZEN:-}" ] || [ ! -x "$ZEN" ]; then
    die "no zen binary at '${ZEN:-<unset>}'.
     Build one first (\`make build\`), or point ZEN at it:
         ZEN=/path/to/zen $0
     This gate belongs in CI from stage 0.4, when gen_c first emits C."
fi

fixture=$here/fixture
[ -d "$fixture" ] || die "missing fixture directory: $fixture"

files=$(find "$fixture" -type f -name '*.zen' | LC_ALL=C sort)
[ -n "$files" ] || die "fixture contains no .zen files: $fixture"

nfiles=$(printf '%s\n' "$files" | wc -l | tr -d ' ')
[ "$nfiles" -ge 4 ] || die "fixture has $nfiles module(s); the shuffle check needs at least 4"

work=${TMPDIR:-/tmp}/zen-determinism.$$
mkdir -p "$work" || die "cannot create work directory $work"

cleanup() {
    if [ "${KEEP:-0}" = 1 ]; then
        printf '%s: kept %s\n' "$progname" "$work"
    else
        rm -rf "$work"
    fi
}
trap cleanup EXIT
trap 'exit 2' INT TERM

printf '%s: %s\n' "$progname" "$ZEN"
printf '%s: fixture %s (%s modules)\n' "$progname" "$fixture" "$nfiles"

# ------------------------------------------------------------- emitting

# emit <out> <newline-separated file list> [extra flags...]
#
# The file list is split on newline ONLY, so a path containing a space is
# fine and a path containing a newline is not. Nothing in this tree has one.
emit() {
    emit_out=$1
    emit_list=$2
    shift 2
    emit_ifs=$IFS
    IFS='
'
    set -f
    # shellcheck disable=SC2086
    "$ZEN" build --emit-c "$@" -o "$emit_out" $emit_list
    emit_status=$?
    set +f
    IFS=$emit_ifs
    return $emit_status
}

permute() {
    # $1: reverse | rotate | interleave
    printf '%s\n' "$files" | awk -v mode="$1" '
        { a[NR] = $0 }
        END {
            if (mode == "reverse")   { for (i = NR; i >= 1; i--) print a[i] }
            else if (mode == "rotate") { for (i = 2; i <= NR; i++) print a[i]; print a[1] }
            else { for (i = 2; i <= NR; i += 2) print a[i]
                   for (i = 1; i <= NR; i += 2) print a[i] }
        }'
}

# --------------------------------------------------- baseline (check 0)

if ! emit "$work/baseline.c" "$files" >"$work/baseline.log" 2>&1; then
    sed 's/^/     /' <"$work/baseline.log" >&2
    die "the compiler failed on the fixture; nothing to compare"
fi

[ -s "$work/baseline.c" ] || die "emitted C is empty; this gate would be vacuous"

baseline_bytes=$(wc -c <"$work/baseline.c" | tr -d ' ')
if [ "$baseline_bytes" -lt 200 ]; then
    die "emitted C is only $baseline_bytes bytes; too small to be a real comparison"
fi
note "baseline: $baseline_bytes bytes"

# ------------------------------------- 1. twice in one process

# Catches state carried from one compilation to the next: a name derived
# from a node's ADDRESS, a counter that is not reset, a cache that changes
# what the second run emits. A per-process hash seed is identical in both
# runs, so this check cannot see it -- check 2 is its pair.
if emit "$work/repeat.c" "$files" --repeat 2 >"$work/repeat.log" 2>&1 && [ -f "$work/repeat.c.2" ]; then
    if cmp -s "$work/repeat.c" "$work/repeat.c.2" && cmp -s "$work/repeat.c" "$work/baseline.c"; then
        ok "1. same input twice in one process"
    else
        bad "1. same input twice in one process: runs differ"
        note "$(cmp "$work/repeat.c" "$work/repeat.c.2" 2>&1 | head -n 1)"
    fi
else
    setup_error=1
    bad "1. same input twice in one process: --repeat 2 unsupported"
    note "README.md declares --repeat N a contract: run the pipeline N times"
    note "in one process, writing run 1 to <out> and run i to <out>.<i>."
    note "Without it the address-derived-name failure has no check at all."
fi

# ------------------------------------- 2. two processes

# Catches anything seeded per process (a randomized hash seed, a PID) and
# anything read from the environment (time zone, locale, temp directory,
# working directory). The two runs differ in all of those on purpose.
mkdir -p "$work/cwd1" "$work/cwd2" "$work/tmp1" "$work/tmp2"

(
    cd "$work/cwd1" || exit 2
    TZ=UTC LC_ALL=C TMPDIR="$work/tmp1" \
        emit "$work/proc1.c" "$files"
) >"$work/proc1.log" 2>&1
proc1=$?

(
    cd "$work/cwd2" || exit 2
    TZ=Pacific/Kiritimati LC_ALL=C.UTF-8 TMPDIR="$work/tmp2" \
        emit "$work/proc2.c" "$files"
) >"$work/proc2.log" 2>&1
proc2=$?

if [ "$proc1" -ne 0 ] || [ "$proc2" -ne 0 ]; then
    bad "2. two processes: a compile failed (see $work/proc*.log)"
    setup_error=1
elif cmp -s "$work/proc1.c" "$work/proc2.c" && cmp -s "$work/proc1.c" "$work/baseline.c"; then
    ok "2. two processes, differing TZ / locale / TMPDIR / cwd"
else
    bad "2. two processes: outputs differ"
    note "$(cmp "$work/proc1.c" "$work/proc2.c" 2>&1 | head -n 1)"
fi

# ------------------------------------- 3. shuffled input order

# Catches dependence on the order the inputs arrive in -- which on a real
# machine is readdir order, which is neither sorted nor stable across
# filesystems. Three fixed permutations, because reverse alone is passed by
# any emitter that happens to sort descending.
shuffle_failed=0
for mode in reverse rotate interleave; do
    shuffled=$(permute "$mode")
    if ! emit "$work/shuffle-$mode.c" "$shuffled" >"$work/shuffle-$mode.log" 2>&1; then
        bad "3. shuffled input order ($mode): compile failed"
        shuffle_failed=1
        setup_error=1
        continue
    fi
    if ! cmp -s "$work/shuffle-$mode.c" "$work/baseline.c"; then
        bad "3. shuffled input order ($mode): output differs from sorted order"
        note "$(cmp "$work/shuffle-$mode.c" "$work/baseline.c" 2>&1 | head -n 1)"
        shuffle_failed=1
    fi
done
[ "$shuffle_failed" -eq 0 ] && ok "3. shuffled input order (reverse, rotate, interleave)"

# ------------------------------------- 4. two trees, two paths

# The path half of "no timestamps or paths in the output". DESIGN.md puts
# file:line:col in every trap message, so paths ARE in the emitted C by
# design -- which makes "relative to the compilation root" a requirement and
# not a preference. Two copies of the same tree at different absolute paths,
# with different name lengths so a padded or aligned buffer cannot hide it.
copy_a=$work/tree-a
copy_b=$work/tree-b-with-a-considerably-longer-name

mkdir -p "$copy_a" "$copy_b"
cp -R "$fixture/." "$copy_a/" 2>/dev/null || die "cannot copy the fixture"
cp -R "$fixture/." "$copy_b/" 2>/dev/null || die "cannot copy the fixture"

files_a=$(find "$copy_a" -type f -name '*.zen' | LC_ALL=C sort)
files_b=$(find "$copy_b" -type f -name '*.zen' | LC_ALL=C sort)

if emit "$work/tree-a.c" "$files_a" >"$work/tree-a.log" 2>&1 &&
   emit "$work/tree-b.c" "$files_b" >"$work/tree-b.log" 2>&1; then
    if cmp -s "$work/tree-a.c" "$work/tree-b.c" && cmp -s "$work/tree-a.c" "$work/baseline.c"; then
        ok "4. two copies of the tree at different absolute paths"
    else
        bad "4. two copies at different paths: outputs differ"
        note "an absolute path is reaching the output; make every emitted"
        note "path relative to the compilation root"
        note "$(cmp "$work/tree-a.c" "$work/tree-b.c" 2>&1 | head -n 1)"
    fi
else
    bad "4. two copies at different paths: a compile failed"
    setup_error=1
fi

# ------------------------------------- 5. scan the emitted C

# Nearly free, and it fails informatively: it names the token, where cmp
# names a byte offset. It also fires when checks 1-4 happen to agree --
# two runs one second apart embed the same timestamp.
scan_hits=0
scan_for() {
    if LC_ALL=C grep -n -- "$1" "$work/baseline.c" >"$work/scan.tmp" 2>/dev/null; then
        bad "5. emitted C contains $2"
        note "$(head -n 1 "$work/scan.tmp")"
        scan_hits=$((scan_hits + 1))
    fi
}
scan_for_re() {
    if LC_ALL=C grep -n -E -- "$1" "$work/baseline.c" >"$work/scan.tmp" 2>/dev/null; then
        bad "5. emitted C contains $2"
        note "$(head -n 1 "$work/scan.tmp")"
        scan_hits=$((scan_hits + 1))
    fi
}

scan_for '__DATE__'  'the __DATE__ macro'
scan_for '__TIME__'  'the __TIME__ macro'
scan_for '__FILE__'  'the __FILE__ macro (positions must be literal strings from the AST)'
scan_for_re "$(printf '%s' "$work" | sed 's/[.[\*^$]/\\&/g')" 'an absolute work-directory path'
scan_for_re "$(printf '%s' "$fixture" | sed 's/[.[\*^$]/\\&/g')" 'an absolute fixture path'
# A pointer printed as hex. The fixture writes no hex literals, so within
# this fixture a 9+ digit hex constant can only have come from an address.
scan_for_re '0[xX][0-9a-fA-F]{9,}' 'a pointer-shaped hex constant'
scan_for_re '(19|20)[0-9]{2}-[01][0-9]-[0-3][0-9]' 'a date'

[ "$scan_hits" -eq 0 ] && ok "5. no timestamp, path, or pointer in the emitted C"

# ---------------------------------------------------------------- verdict

printf '%s: %s passed, %s failed\n' "$progname" "$passed" "$failed"

if [ "$failed" -gt 0 ]; then
    if [ "$setup_error" -eq 1 ]; then
        printf '%s: at least one failure was a harness/contract problem, not a\n' "$progname"
        printf '%s: determinism result. See README.md, "What the compiler must provide".\n' "$progname"
        exit 2
    fi
    printf '%s: gen_c is nondeterministic. The fixpoint oracle cannot be trusted\n' "$progname"
    printf '%s: until this is green. README.md names the four usual causes.\n' "$progname"
    exit 1
fi

exit 0
