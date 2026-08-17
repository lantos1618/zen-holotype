# scripts/emit-runs.awk
# Find consecutive statements that all write into ONE buffer -- the runs a
# single `fmt` call would collapse.
#
# WHY THE OBVIOUS SCAN UNDERCOUNTS. A first survey looked for `add_bytes` /
# `write` / `writeln` on one receiver and stopped a run at anything else. That
# misses the commonest shape in `gen_c`, because a HELPER WRITES TOO:
#
#     out.add_bytes(sym.view()).try();
#     out.add_bytes("(").try();
#     write_arg(be, ix.base,  0, f, sig, ctx, out).try();   <-- also writes `out`
#     out.add_bytes(", ").try();
#     write_arg(be, ix.index, 1, f, sig, ctx, out).try();   <-- also writes `out`
#     out.add_bytes(")").try();
#
# Six statements, one buffer, one line of C. The scan that stops at `write_arg`
# reports two runs of two and hides the whole shape.
#
# SO AN EMIT IS EITHER FORM:
#   - a method on the buffer            `out.add_bytes(..)`, `be.writeln(..)`
#   - a call whose LAST argument is it  `write_arg(be, .., out)`, `sym_gen(n, ..)`
# The second is the convention this tree already follows: a writer takes the
# buffer last and answers `Res<(), AllocError>`. That is why it can be detected
# without types.
#
# WHAT A RUN IS NOT. Anything between two emits that is not itself an emit into
# the same buffer breaks the run -- a `.match`, a `loop`, an `indent()`, a
# binding, a call that answers a value. Those are real boundaries, not scanner
# limitations: the collapsed form has to be one expression.
#
# HONEST LIMITS, so nobody reads the number as gospel:
#   - LINE ORIENTED. A statement wrapped over several lines is counted at its
#     first line only, so runs containing wrapped calls are undercounted. This
#     is a lead generator; `bootstrap/cst.py` is the parser if it ever needs to
#     be exact (STYLE.md:23, "parse, don't grep").
#   - It does not know a hole must be a `str`. A run holding a `usize` write
#     still collapses, but around a writer that needs its own buffer -- see
#     `open_ordinal_test` in gen_c_cap.zen for the shape.
#
# USAGE
#   find src -name '*.zen' | xargs awk -f scripts/emit-runs.awk            # runs
#   find src -name '*.zen' | xargs awk -f scripts/emit-runs.awk -v mode=ledger
#
# `mode=ledger` prints `"path": n,` lines, ready to paste into a count-keyed
# ledger in scripts/style.py so the backlog ratchets down and cannot grow --
# the same shape as IMPORT_OWED and UFCS_OWED.

# A run must contain at least one METHOD-form write (`buf.add_bytes(..)`).
# Without that, "the last argument is a bare name" matches things that are not
# buffers at all -- `false` out of a match arm was the first false positive.
# The method form is what proves the name is a buffer; the helper form alone
# proves nothing.
function flush(   len) {
    len = line - start
    if (recv != "" && n >= 2 && direct >= 1) {
        runs++; saved += n - 1; per_file[FILENAME] += n - 1
        if (mode != "ledger")
            printf "%s:%d-%d: %d writes into `%s` -> 1 fmt (saves %d)\n",
                   FILENAME, start, last, n, recv, n - 1
    }
    recv = ""; n = 0; direct = 0
}

FNR == 1 { flush() }

{
    line = FNR
    s = $0
    sub(/^[ \t]+/, "", s)

    # strip a trailing comment, but not one inside a string
    if (s ~ /^\/\//) { flush(); next }
    if (s == "") next

    who = ""; is_direct = 0

    # form 1: `buf.method(` where method is a known byte writer
    if (match(s, /^[A-Za-z_][A-Za-z0-9_]*\.(add_bytes|add_byte|write|writeln|fmt)\(/)) {
        who = substr(s, 1, index(s, ".") - 1); is_direct = 1
    }
    # form 2: a call whose LAST argument is a bare name -- `f(a, b, out)`
    else if (match(s, /^[A-Za-z_][A-Za-z0-9_.]*\(.*\)(\.try\(\))?;?$/)) {
        inner = substr(s, index(s, "(") + 1)
        # last argument = text after the final top-level comma
        depth = 0; cut = 0
        for (i = 1; i <= length(inner); i++) {
            ch = substr(inner, i, 1)
            if (ch == "(" || ch == "[" || ch == "{") depth++
            else if (ch == ")" || ch == "]" || ch == "}") depth--
            else if (ch == "," && depth == 0) cut = i
        }
        if (cut > 0) {
            arg = substr(inner, cut + 1)
            sub(/\).*$/, "", arg)
            gsub(/[ \t]/, "", arg)
            if (arg ~ /^[A-Za-z_][A-Za-z0-9_]*$/) { who = arg; is_direct = 0 }
        }
    }

    if (who == "") { flush(); next }
    if (who != recv) { flush(); recv = who; start = line }
    n++; last = line; direct += is_direct
}

END {
    flush()
    if (mode == "ledger") {
        for (f in per_file) printf "    \"%s\": %d,\n", f, per_file[f]
    } else {
        printf "\n%d run(s), %d call(s) collapsible\n", runs, saved
    }
}
