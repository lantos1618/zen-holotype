#!/usr/bin/env bash
# scripts/ffi_verify.sh — FFI drift gate: prove Zen's hand-written foreign prototypes match the
# REAL system headers.
#
#   scripts/ffi_verify.sh [ZENC]        (default: ./zen next to the repo root)
#
# Zen's std hand-transcribes libc/libm/pthread prototypes as bodyless decls (src/std/c/libc.zen
# and friends). A transcription slip — wrong integer width, wrong arg count, pointer/integer
# confusion — still compiles fine: genc emits a bare C prototype and C's implicit trust does the
# rest, corrupting at runtime. This gate checks Zen's belief against the headers:
#
#   1. Reuse `zenc emit`: one tiny driver program per foreign-bearing std module (one emit per
#      module — co-importing them can collide in the flat namespace) lowers every foreign decl in
#      its closure to a bare C prototype in the emitted C. Extract those prototypes.
#   2. Symbols are classed by the map below:
#        abi    — pasted verbatim into a namespace next to the real #includes and compared
#                 slot-by-slot against decltype(::sym) by scripts/ffi_abi_check.h (g++ -Werror,
#                 static_assert). Catches arg-count drift, integer/float width drift, register-
#                 class confusion, callback-signature drift, unsound const direction; allows
#                 Zen's documented ABI-identical freedoms (i64-for-size_t, RawPtr<u8>-for-void*).
#        exact  — must match the header's C prototype VERBATIM (libm: Zen f64 = C double, no
#                 freedoms needed; also dodges C++'s overloaded ::sin). Compiled as a plain C
#                 redeclaration under the header — any drift is a conflicting-types hard error.
#      Symbols named zen_* / __zen_* are runtime-internal (bootstrap/zenrt.c or the genc platform
#      prelude define them) and are NOT in system headers: skipped by prefix.
#   3. Any extracted foreign symbol missing from the map (or mapped but no longer emitted) fails
#      the gate — the map cannot silently go stale.
#
# Platform: the map encodes the Linux/glibc header layout (CI's environment). Elsewhere the gate
# prints a notice and exits 0. 64-bit Linux only: off_t/pthread_t widths are checked against the
# host headers themselves, so an LP64 assumption baked into a Zen decl (e.g. lseek's i64 off_t)
# would be flagged on any platform where the header disagrees.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ZENC="${1:-$ROOT/zen}"

case "$(uname -s)" in
    Linux) ;;
    *) echo "ffi-verify: SKIP (symbol->header map targets Linux/glibc; host is $(uname -s))"; exit 0 ;;
esac
command -v gcc >/dev/null 2>&1 || { echo "ffi-verify: SKIP (gcc not found)"; exit 0; }
command -v g++ >/dev/null 2>&1 || { echo "ffi-verify: SKIP (g++ not found)"; exit 0; }
[ -x "$ZENC" ] || { echo "ffi-verify: zenc not executable: $ZENC (build with 'make' first)" >&2; exit 2; }

WORK="$(mktemp -d /tmp/zenc-ffi-verify.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

# ── symbol map: name<TAB>lane<TAB>header ─────────────────────────────────────────────────────────
# lane: abi = ABI-class check (ffi_abi_check.h), exact = verbatim C redeclare under the header.
# Every non-zen_* foreign symbol the std closure emits MUST have a row here (gate-enforced).
MAP="$WORK/map.tsv"
cat > "$MAP" <<'EOF'
calloc	abi	stdlib.h
memcpy	abi	string.h
strlen	abi	string.h
strcmp	abi	string.h
open	abi	fcntl.h
read	abi	unistd.h
write	abi	unistd.h
close	abi	unistd.h
isatty	abi	unistd.h
lseek	abi	unistd.h
unlink	abi	unistd.h
access	abi	unistd.h
mkdir	abi	sys/stat.h
rmdir	abi	unistd.h
rename	abi	stdio.h
stat	abi	sys/stat.h
opendir	abi	dirent.h
readdir	abi	dirent.h
rewinddir	abi	dirent.h
closedir	abi	dirent.h
system	abi	stdlib.h
abort	abi	stdlib.h
exit	abi	stdlib.h
getpid	abi	unistd.h
getenv	abi	stdlib.h
setenv	abi	stdlib.h
unsetenv	abi	stdlib.h
clock_gettime	abi	time.h
nanosleep	abi	time.h
popen	abi	stdio.h
pclose	abi	stdio.h
fgets	abi	stdio.h
malloc	abi	stdlib.h
realloc	abi	stdlib.h
free	abi	stdlib.h
socket	abi	sys/socket.h
bind	abi	sys/socket.h
listen	abi	sys/socket.h
accept	abi	sys/socket.h
connect	abi	sys/socket.h
setsockopt	abi	sys/socket.h
getsockname	abi	sys/socket.h
getcontext	abi	ucontext.h
makecontext	abi	ucontext.h
swapcontext	abi	ucontext.h
pthread_create	abi	pthread.h
pthread_join	abi	pthread.h
pthread_mutex_init	abi	pthread.h
pthread_mutex_lock	abi	pthread.h
pthread_mutex_unlock	abi	pthread.h
pthread_mutex_destroy	abi	pthread.h
pthread_cond_init	abi	pthread.h
pthread_cond_wait	abi	pthread.h
pthread_cond_signal	abi	pthread.h
pthread_cond_broadcast	abi	pthread.h
pthread_cond_destroy	abi	pthread.h
sin	exact	math.h
cos	exact	math.h
tan	exact	math.h
atan	exact	math.h
atan2	exact	math.h
log	exact	math.h
log2	exact	math.h
log10	exact	math.h
exp	exact	math.h
pow	exact	math.h
EOF

# ── 1. emit each foreign-bearing std module (one public symbol imported per driver) ──────────────
MODULES="
std.c.libc:getpid
std.mem.alloc:malloc
std.math:sin
std.net.socket:serve
std.time.clock:mono_ns
std.sys.os:argc
std.sys.platform:platform
std.concurrent.pool:pool_spawn
std.concurrent.coroutine:checkpoint_current
std.internal.resolve:is_import_line
"
i=0
for m in $MODULES; do
    mod="${m%%:*}"; sym="${m##*:}"
    i=$((i + 1))
    drv="$WORK/drv_$i.zen"
    printf '{ %s } = %s\nmain = () i32 { 0 }\n' "$sym" "$mod" > "$drv"
    if ! ZENC_NO_CACHE=1 "$ZENC" emit "$drv" > "$WORK/em_$i.c" 2> "$WORK/em_$i.err"; then
        echo "ffi-verify: 'zenc emit' failed for module $mod:" >&2
        cat "$WORK/em_$i.err" >&2
        exit 1
    fi
done

# ── 2. extract the bare foreign prototypes from the emitted C ────────────────────────────────────
# genc emits a bare `ret name(args);` for every function — a forward decl for Zen-defined fns,
# the WHOLE binding for foreign ones. Split on ';' (prototypes contain none), keep statement-free
# brace-free segments shaped like `type name(params)`, then drop every symbol whose emit also
# contains the matching DEFINITION (`<proto> {`): what survives is exactly the foreign surface
# (plus zen_main's forward decl, prefix-skipped later). Two passes over the same file: the first
# slurps the source for the definition lookup, the second walks the candidate segments.
extract() {
    awk 'BEGIN { RS = ";" }
    {
        gsub(/\n/, " ")
        if (FNR == NR) { src = src $0 ";"; next }
        gsub(/^[ \t]+/, ""); gsub(/[ \t]+$/, "")
        if ($0 == "") next
        if (index($0, "{") || index($0, "}") || index($0, "=") || index($0, "\"")) next
        if ($0 !~ /^[A-Za-z_]/) next
        if ($0 ~ /^(typedef|static|extern|return|if|while|for|do|else)[ (]/) next
        p = index($0, "(")
        if (p == 0) next
        if ($0 !~ /\)$/) next
        head = substr($0, 1, p - 1)
        gsub(/\*/, " * ", head)
        n = split(head, toks, /[ \t]+/)
        if (n < 2) next
        name = toks[n]
        if (name !~ /^[A-Za-z_][A-Za-z0-9_]*$/) next
        if (index(src, $0 " {") != 0) next
        print name "\t" $0
    }' "$1" "$1"
}
PROTOS="$WORK/protos.tsv"
for f in "$WORK"/em_*.c; do extract "$f"; done | awk -F'\t' '!seen[$1]++' > "$PROTOS"

# ── 3. map completeness both ways ────────────────────────────────────────────────────────────────
fail=0
while IFS=$'\t' read -r name proto; do
    case "$name" in
        zen_*|__zen_*) continue ;; # runtime-internal: defined by zenrt.c / the genc prelude
    esac
    if ! grep -q "^$name	" "$MAP"; then
        echo "ffi-verify: UNMAPPED foreign symbol '$name' ($proto;) — add a row to the map in scripts/ffi_verify.sh" >&2
        fail=1
    fi
done < "$PROTOS"
while IFS=$'\t' read -r name lane header; do
    if ! grep -q "^$name	" "$PROTOS"; then
        echo "ffi-verify: map lists '$name' but the std closure no longer emits it — drop the stale row" >&2
        fail=1
    fi
done < "$MAP"
[ "$fail" = 0 ] || exit 1

# ── 4a. exact lane: verbatim C redeclaration under the real header ───────────────────────────────
STRICT="$WORK/verify_exact.c"
{
    echo "/* generated by scripts/ffi_verify.sh — Zen foreign prototypes redeclared VERBATIM under"
    echo "   the system headers: any drift is a conflicting-types hard error. */"
    echo "#include <stdint.h>"
    awk -F'\t' '$2 == "exact" { print "#include <" $3 ">" }' "$MAP" | sort -u
    join -t"$(printf '\t')" <(awk -F'\t' '$2 == "exact" { print $1 }' "$MAP" | sort) <(sort "$PROTOS") \
        | cut -f2 | sed 's/$/;/'
} > "$STRICT"
if ! gcc -std=gnu11 -fsyntax-only -Wall -Werror -Werror=builtin-declaration-mismatch "$STRICT" 2> "$WORK/exact.err"; then
    echo "ffi-verify: DRIFT in the exact lane (libm) — Zen decl vs system header:" >&2
    cat "$WORK/exact.err" >&2
    exit 1
fi

# ── 4b. abi lane: slot-by-slot ABI-class comparison against decltype(::sym) ──────────────────────
ABI="$WORK/verify_abi.cc"
{
    echo "// generated by scripts/ffi_verify.sh — Zen foreign prototypes vs system headers."
    echo "#include <cstdint>"
    echo "#include <cstddef>"
    awk -F'\t' '$2 == "abi" { print "#include <" $3 ">" }' "$MAP" | sort -u
    echo '#include "ffi_abi_check.h"'
    echo "namespace zen_ffi {"
    join -t"$(printf '\t')" <(awk -F'\t' '$2 == "abi" { print $1 }' "$MAP" | sort) <(sort "$PROTOS") \
        | cut -f2 | sed 's/$/;/'
    echo "}"
    awk -F'\t' '$2 == "abi" { print "ZEN_FFI_CHECK(" $1 ")" }' "$MAP"
} > "$ABI"

# -Wno-ignored-attributes: glibc decorates prototypes with nonnull/warn_unused_result/…;
# attributes are not part of the function TYPE and are irrelevant to the ABI contract, but g++
# warns when a decorated function is used as a template argument.
if ! g++ -std=gnu++17 -fsyntax-only -Werror -Wno-ignored-attributes -I"$ROOT/scripts" "$ABI" 2> "$WORK/abi.err"; then
    echo "ffi-verify: DRIFT in the abi lane — Zen decl vs system header (the incomplete-type" >&2
    echo "diagnostic prints both signatures: drift<zen-belief, header-truth, false>):" >&2
    cat "$WORK/abi.err" >&2
    exit 1
fi

n_abi=$(awk -F'\t' '$2 == "abi"' "$MAP" | wc -l)
n_exact=$(awk -F'\t' '$2 == "exact"' "$MAP" | wc -l)
n_skip=$(grep -cE '^(zen_|__zen_)' <(cut -f1 "$PROTOS"))
echo "ffi-verify: OK — $((n_abi + n_exact)) foreign prototypes verified against system headers ($n_abi abi-class + $n_exact exact); $n_skip runtime-internal symbols skipped"
