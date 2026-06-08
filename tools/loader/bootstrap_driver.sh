#!/usr/bin/env bash
# ONE-TIME BOOTSTRAP of the std.resolve loader driver.
#
# The loader driver (tools/loader/loader_driver.zen) is itself a multi-module Zen program, so building it
# needs a flat single module — exactly the job the loader does. Chicken-and-egg: we can't run the loader
# to build the loader. This script does that flatten ONCE, generically (no per-program file list baked
# in), so the resulting `loader` binary can then flatten every OTHER program (and re-flatten itself).
#
# It is the loader's analogue of `zenc` being built from the committed bootstrap/zenc.gen.c: a trusted
# bootstrap that the self-hosted tool supersedes. It performs the SAME two dedup levels std.resolve does,
# but in awk:
#   • PER-MODULE: each module file appended once (the closure list below is the driver's transitive set).
#   • PER-NAME:   strip `{ … } = std.X` import lines, then keep only the FIRST top-level decl of each
#     name — a decl runs from a COLUMN-0 head (`name[*] =/:` or `Name.impl(`) to the next column-0 head;
#     a later same-named head + its body are dropped. This resolves string.free / mem.free / alloc.free.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${1:-/tmp/loader_flat.zen}"

# The driver's transitive closure, dependency-first (deps before dependents so the dep's decl wins the
# per-name dedup, matching std.resolve.load_closure's emission order). Hand-listed ONLY for this one-time
# bootstrap; the loader discovers the closure itself for all other programs.
CLOSURE=(
  "$ROOT/zen/std/mem.zen"
  "$ROOT/zen/std/str.zen"
  "$ROOT/zen/std/string.zen"
  "$ROOT/zen/std/alloc.zen"
  "$ROOT/zen/std/lex.zen"
  "$ROOT/zen/std/io.zen"
  "$ROOT/zen/std/resolve.zen"
  "$ROOT/tools/loader/loader_driver.zen"
)

# strip imports + per-name-first-decl dedup, in one awk pass over the concatenated closure.
cat "${CLOSURE[@]}" | awk '
  function is_ws(c){ return c==" " || c=="\t" }
  {
    line=$0
    # drop `{ … } = std.X` import lines (the std.resolve / generate.py strip predicate).
    s=line; sub(/^[ \t]+/,"",s)
    if (s ~ /^\{ / && line ~ /= std\./) next

    # is this a COLUMN-0 top-level decl head?  ident run at col 0, then `*`/space then `=`/`:`,
    # OR `.impl(` (a method-impl block: a decl boundary that is ALWAYS kept, never deduped).
    if (line ~ /^[A-Za-z_][A-Za-z0-9_]*[*]?[ ]*[=:]/ ) {
      match(line, /^[A-Za-z_][A-Za-z0-9_]*/); name=substr(line, 1, RLENGTH)
      if (name in seen) { keeping=0 }     # later duplicate decl → drop it + its body
      else { seen[name]=1; keeping=1; print line }
      next
    }
    if (line ~ /^[A-Za-z_][A-Za-z0-9_.<>]*\.impl/) { keeping=1; print line; next }

    # a continuation line (indented, `}`, comment, blank): emit iff the current decl is kept.
    if (keeping) print line
  }
' > "$OUT"

echo "bootstrap: closure = ${#CLOSURE[@]} files -> $OUT ($(wc -l < "$OUT") lines)"
