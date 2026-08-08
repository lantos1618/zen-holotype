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
# This script is itself deterministic: the permutations below are three
# fixed ones, not `shuf`. A harness that fails once and passes on rerun
# teaches you to press rerun.
#
# A BUILD IS A ROOT. `zen build <root> [--entry <file>] --emit-c -o <file>`
# is the whole CLI: the driver is handed a directory and finds the modules
# itself by following imports from the entry. This script used to invoke
# `zen build --emit-c <file list>`, which is the BOOTSTRAPPER's spelling and
# which the self-hosted compiler answers with `unknown argument` -- so the
# strongest property in the plan sat behind a gate that exited 2 on its
# first line and had, on the day this was fixed, never run once.
#
# THE FIXTURE IS STAGED, not compiled where it sits. A Zen program stands on
# the prelude -- `Env`, `Res`, `Ok` and `println` are `std.core` names that
# no module imports -- and the driver looks for `std/` beneath the root it
# was given. So each tree this script compiles is a fresh directory holding
# the fixture and a copy of `src/std`, which is exactly what `tests/run.py`
# does for every corpus test and for the same reason.

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

# ABSOLUTE, ALWAYS. Check 2 compiles from two different working directories
# on purpose, and the Makefile invokes this with `ZEN=./zen` -- so a
# relative binary path is `not found` in both of them, and the one check
# that exists to catch a per-process hash seed reports a harness error
# instead of a result. Resolved AFTER the -x test above, so that message
# still names the path that was actually typed.
case $ZEN in
    /*) ;;
    *)  ZEN=$(CDPATH= cd -- "$(dirname -- "$ZEN")" && pwd)/$(basename -- "$ZEN") \
            || die "cannot make '$ZEN' absolute" ;;
esac

fixture=$here/fixture
[ -d "$fixture" ] || die "missing fixture directory: $fixture"

files=$(find "$fixture" -type f -name '*.zen' | LC_ALL=C sort)
[ -n "$files" ] || die "fixture contains no .zen files: $fixture"

nfiles=$(printf '%s\n' "$files" | wc -l | tr -d ' ')
[ "$nfiles" -ge 4 ] || die "fixture has $nfiles module(s); the walk check needs at least 4"

# The prelude the fixture stands on. Missing it is a setup error and not a
# skip: compiling the fixture without it fails on `Env` in the first line of
# main.zen and says nothing at all about determinism.
prelude=$root/src/std
[ -d "$prelude" ] || die "missing prelude: $prelude
     Every Zen program stands on std.core, and the driver looks for it
     beneath the root it is given. Nothing can be compiled without it."

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

# stage <dir> -- a compilable root: the fixture, and the prelude under it.
stage() {
    mkdir -p "$1" || die "cannot create $1"
    cp -R "$fixture/." "$1/" || die "cannot copy the fixture into $1"
    cp -R "$prelude" "$1/std" || die "cannot copy the prelude into $1"
}

# emit <out> <root> [extra flags...]
#
# One root and no file list, which is the whole of why this script had to
# be rewritten. Nothing here splits a string on whitespace, so a path with
# a space in it is simply fine.
emit() {
    emit_out=$1
    emit_root=$2
    shift 2
    "$ZEN" build "$emit_root" --emit-c -o "$emit_out" "$@"
}

tree=$work/tree
stage "$tree"

# --------------------------------------------------- baseline (check 0)

if ! emit "$work/baseline.c" "$tree" >"$work/baseline.log" 2>&1; then
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
if emit "$work/repeat.c" "$tree" --repeat 2 >"$work/repeat.log" 2>&1 && [ -f "$work/repeat.c.2" ]; then
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
        emit "$work/proc1.c" "$tree"
) >"$work/proc1.log" 2>&1
proc1=$?

(
    cd "$work/cwd2" || exit 2
    TZ=Pacific/Kiritimati LC_ALL=C.UTF-8 TMPDIR="$work/tmp2" \
        emit "$work/proc2.c" "$tree"
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

# ------------------------------------- 3. a permuted module walk

# THE AXIS THAT MOVED INTO THE COMPILER. It used to shuffle a list of file
# arguments, which the self-hosted CLI does not take: it is handed a root
# and computes the module order itself, breadth-first from the entry,
# following imports. `--permute <mode>` reorders each module's imports and
# so reorders that walk -- which changes every module index, and with it the
# insertion order into every table sema and gen build. README.md, "the
# shuffle axis", says why this was kept rather than retired.
#
# Three fixed permutations, because reverse alone is passed by anything
# that happens to work backwards.

# 3a. THE INSTRUMENT, CHECKED BEFORE IT IS TRUSTED. A compiler that accepts
# `--permute` and ignores it would make 3b pass by comparing a file with
# itself -- which is the exact failure this script's header names, arrived
# at from the other side. So first: break one declaration in each module and
# read the order the diagnostics come out in. The walk reports a module when
# it reaches it, so that order IS the walk order, and it must MOVE.
broken=$work/broken
stage "$broken"
for m in alpha beta delta gamma; do
    [ -f "$broken/$m/$m.zen" ] || die "fixture has no module $m; 3a cannot instrument the walk"
    printf '\n?\n' >>"$broken/$m/$m.zen" || die "cannot write $broken/$m/$m.zen"
done

# The modules named by the lex faults, in the order they were reported.
walk_order() {
    if [ -n "$1" ]; then
        emit "$work/broken.c" "$broken" --permute "$1" 2>&1
    else
        emit "$work/broken.c" "$broken" 2>&1
    fi | sed -n 's|^\(.*\)\.zen:[0-9][0-9]*:[0-9][0-9]*: unexpected character.*|\1|p' \
       | tr '\n' ' '
}

plain_order=$(walk_order "")
instrument_ok=1
if [ -z "$plain_order" ]; then
    bad "3a. the walk is not observable: the broken fixture reported no lex fault"
    note "3a appends a junk byte to four modules and reads the order the"
    note "faults come back in. No fault means the instrument is broken, so"
    note "3b below would be comparing a file with itself."
    instrument_ok=0
    setup_error=1
fi

# 3b. THE PROPERTY. Same program, different walk, same bytes.
walk_failed=0
for mode in reverse rotate interleave; do
    if [ "$instrument_ok" -eq 1 ]; then
        mode_order=$(walk_order "$mode")
        if [ "$mode_order" = "$plain_order" ]; then
            bad "3a. --permute $mode did not reorder the walk"
            note "reported order was '$mode_order' either way, so 3b below"
            note "cannot see anything. Either the flag is ignored, or the"
            note "fixture's entry imports too few modules to permute."
            walk_failed=1
            setup_error=1
        fi
    fi
    if ! emit "$work/walk-$mode.c" "$tree" --permute "$mode" >"$work/walk-$mode.log" 2>&1; then
        bad "3b. permuted module walk ($mode): compile failed"
        sed 's/^/     /' <"$work/walk-$mode.log" >&2
        walk_failed=1
        setup_error=1
        continue
    fi
    if ! cmp -s "$work/walk-$mode.c" "$work/baseline.c"; then
        bad "3b. permuted module walk ($mode): output differs from import order"
        note "something emitted is ordered by, or named after, the order the"
        note "modules were discovered in. gen_emit.zen's \`order\` is the only"
        note "way to order a collection, and a name is a function of the"
        note "program and never of the run."
        note "$(cmp "$work/walk-$mode.c" "$work/baseline.c" 2>&1 | head -n 1)"
        walk_failed=1
    fi
done
[ "$walk_failed" -eq 0 ] && ok "3. permuted module walk (reverse, rotate, interleave)"

# ------------------------------------- 4. two trees, two paths

# The path half of "no timestamps or paths in the output". DESIGN.md puts
# file:line:col in every trap message, so paths ARE in the emitted C by
# design -- which makes "relative to the compilation root" a requirement and
# not a preference. Two copies of the same tree at different absolute paths,
# with different name lengths so a padded or aligned buffer cannot hide it.
copy_a=$work/tree-a
copy_b=$work/tree-b-with-a-considerably-longer-name

stage "$copy_a"
stage "$copy_b"

if emit "$work/tree-a.c" "$copy_a" >"$work/tree-a.log" 2>&1 &&
   emit "$work/tree-b.c" "$copy_b" >"$work/tree-b.log" 2>&1; then
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
# A pointer printed as hex. Neither the fixture nor std writes a hex literal
# this wide, so a 9+ digit hex constant can only have come from an address.
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
