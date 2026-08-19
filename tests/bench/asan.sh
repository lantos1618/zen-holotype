#!/usr/bin/env bash
# tests/bench/asan.sh -- run one representative compile through the
# sanitizer-built compiler (zen-asan, built by `make asan`).
#
# The program staged here is corpus/std/vec_grows_past_eight.zen: small, and
# it exercises the allocator door every generated program uses (Vec growth
# through Alloc -> Mem.page -> malloc). Staging mirrors tests/run.py: a temp
# root holding std and the program as main.zen, so the compilation root is
# the staging directory and never the filesystem.
#
# KNOWN-DELIBERATE LEAKS, two of them, both in the startup prologue and both
# process-lifetime by design: the argv rows (src/gen/gen_c/gen_c_main.zen:156,
# suppressed by name in tests/bench/lsan.supp) and the root arena state (the
# first `env.mem.alloc()` in src/zen/zen.zen, reported with its top frame in
# generated main). LSan suppressions match ANY frame, and every allocation
# in the program sits under main -- so the arena block cannot be suppressed
# by name without silencing every real leak. Instead this script reads the
# report and fails on any leak whose top application frame is NOT one of the
# two known startup sites. Do not "fix" that by widening the allowlist.
set -euo pipefail

ZEN_ASAN=${1:-./zen-asan}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)

if [ ! -x "$ZEN_ASAN" ]; then
    echo "asan.sh: no executable at $ZEN_ASAN (run \`make asan\`)" >&2
    exit 2
fi

WORK=$(mktemp -d /tmp/zen-asan.XXXXXX)
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/src"
cp -r "$ROOT/src/std" "$WORK/src/std"
cp "$ROOT/tests/corpus/std/vec_grows_past_eight.zen" "$WORK/src/main.zen"

echo "asan.sh: compiling corpus/std/vec_grows_past_eight under $ZEN_ASAN"
export ASAN_OPTIONS=detect_leaks=1
export LSAN_OPTIONS="suppressions=$ROOT/tests/bench/lsan.supp"

set +e
"$ZEN_ASAN" build "$WORK/src" --emit-c -o "$WORK/out.c" >"$WORK/out.log" 2>&1
code=$?
set -e
cat "$WORK/out.log"

if [ "$code" -eq 0 ]; then
    echo "asan.sh: clean -- no ASan/LSan report"
    exit 0
fi

# Non-zero with no LSan report is a compile error or an ASan memory error:
# both fail as-is. A leak report gets its top frames checked.
if ! grep -q "LeakSanitizer: detected memory leaks" "$WORK/out.log"; then
    echo "asan.sh: $ZEN_ASAN exited $code with no leak report; failing as-is" >&2
    exit 1
fi

# The top application frame of each leak block: the first frame that is not
# the allocator interceptor.
tops=$(awk '
    /^(Direct|Indirect) leak of/ { inblock = 1; got = 0; next }
    inblock && /^(-|SUMMARY)/     { inblock = 0; next }
    inblock && !got && / in / {
        line = $0
        sub(/.* in /, "", line); sub(/[ (].*/, "", line)
        if (line !~ /^(malloc|calloc|realloc|strdup)$/) { print line; got = 1 }
    }
' "$WORK/out.log" | sort -u)

# zg_argv_vec is suppressed upstream; what may legitimately remain is the
# root arena state, whose top frame is generated main (the zen main, or C
# main if the build inlines one step further).
known='^(main|zu_f3_3zen3zen4mainO1_t4_3std3env3env3Env)$'
bad=$(printf '%s\n' "$tops" | grep -vE "$known" || true)
if [ -n "$bad" ]; then
    echo "asan.sh: leak(s) with unexpected top frame(s): $bad" >&2
    echo "asan.sh: only the startup prologue may leak; this is a real bug" >&2
    exit 1
fi

echo "asan.sh: only the known process-lifetime startup blocks leaked" \
    "(argv rows, root arena state -- annotated above, deliberate)"
