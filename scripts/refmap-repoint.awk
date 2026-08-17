# scripts/refmap-repoint.awk
# Repoint docs/GENC_REFERENCE_MAP.md from `refmap.py`'s OWN report, in ONE pass.
#
# WHY THIS EXISTS AS A TOOL. Any change to bootstrap/gen_c.py shifts the line
# numbers the reference map claims, so `make refmap` goes red on work that had
# nothing to do with the map. Three separate lanes have each hand-rolled this
# repair, and hand-patching it CORRUPTS the document: it has turned (1953-2000)
# into (1953-1923), because a coordinate rewritten twice is rewritten wrong.
#
# THE TWO HAZARDS, both of which have actually bitten:
#
#   1. SEQUENTIAL substitution chains. One doc line can carry two claims that
#      SWAP -- `erase 6609 -> 6481-6498` beside `parse_int 6498 -> 6596-6609`.
#      Apply them one after another and the second rewrites what the first just
#      wrote. So every substitution on a line is located in the ORIGINAL text,
#      staged behind a placeholder, and resolved together.
#   2. A `path:line` claim is ALSO a bare number, so a naive number pass fires
#      twice on the same digits. Matching is literal and each span is claimed
#      once, longest first, so 4697 cannot eat part of 46970.
#
# WHAT IT WILL NOT DO, AND WHY THAT IS THE DESIGN. `refmap.py` declines to pin a
# symbol it finds in dozens of places -- `Ok`, `main`, `slot`, `NULL`. Those
# claims are LEFT ALONE and listed on stderr, because repointing one at a
# similar name destroys the information the claim carried, which is exactly the
# objection refmap states when it refuses. Measured on a 7-line synthetic
# insertion: 107 stale -> 23, and all 23 residual were of that kind.
#
# Repair those BY HAND, and ask a different question -- not "where is this
# symbol" but "where did line N go":
#
#   diff <(git show <old-ref>:bootstrap/gen_c.py) bootstrap/gen_c.py
#
# A shift tool driven by that diff was written and DELETED rather than shipped:
# a doc line can hold one ambiguous claim beside one this script already fixed,
# so the two tools rewrite the same line and oscillate. One sound tool plus a
# handful of judged edits beats two that fight. If the residual ever grows past
# a handful, the fix is for `refmap.py` to emit a disambiguating anchor, not for
# a second rewriter to guess.
#
# USAGE
#   python3 scripts/refmap.py | awk -f scripts/refmap-repoint.awk
#   make refmap        # then judge whatever it still names, by the diff above

BEGIN {
    doc = "docs/GENC_REFERENCE_MAP.md"
    OLD = "\001"; NEW = "\002"          # placeholder fences: never in the doc
    n_amb = 0; n_edit = 0
}

# `sym` OLD -- `sym` is defined at NEW        (the common form)
# gen_c.py:OLD -- `sym` is defined at NEW     (a path claim)
# "quoted" OLD -- it reads at NEW             (a quoted-text claim)
$0 ~ ("^" doc ":[0-9]+: ") {
    line = $0
    sub("^" doc ":", "", line)
    colon = index(line, ":")
    ln = substr(line, 1, colon - 1) + 0
    rest = substr(line, colon + 2)

    at = index(rest, " -- ")
    if (at == 0) next
    left = substr(rest, 1, at - 1)
    right = substr(rest, at + 4)

    # the claimed coordinate is the last token of the left half
    nf = split(left, lf, " ")
    old = lf[nf]
    sub(/^[^:]*:/, "", old)             # a path claim carries `gen_c.py:` first
    if (old !~ /^[0-9]+(-[0-9]+)?$/) next

    # the actual location is what follows "at " in the right half
    if (match(right, / at [0-9]/) == 0) next
    new = substr(right, RSTART + 4)
    sub(/ +--.*$/, "", new)             # refmap may append advice
    sub(/[ \t]+$/, "", new)
    if (new ~ /,/) {                    # ambiguous -- refmap says it means little
        amb[++n_amb] = $0
        next
    }
    if (new !~ /^[0-9]+(-[0-9]+)?$/) next

    k = ++n_edit
    e_ln[k] = ln; e_old[k] = old; e_new[k] = new
    has[ln] = 1
    next
}

# "says gen_c.py is 7037 lines; it is 7135"
/says .* is [0-9]+ lines; it is [0-9]+/ {
    n = split($0, w, " ")
    for (i = 1; i <= n; i++) {
        if (w[i] == "lines;") { count_old = w[i-1] }
        if (w[i] == "is" && i == n - 0) { count_new = w[n] }
    }
    count_new = w[n]
    next
}

END {
    # read the doc
    nl = 0
    while ((getline l < doc) > 0) src[++nl] = l
    close(doc)

    touched = 0
    for (ln in has) {
        text = src[ln]

        # stage: longest old first, each claimed once, placeholder per edit
        for (pass = 0; pass < 2; pass++) {
            for (k = 1; k <= n_edit; k++) {
                if (e_ln[k] != ln || done[k]) continue
                want = (pass == 0) ? (length(e_old[k]) > 4) : 1
                if (!want) continue
                i = index(text, e_old[k])
                if (i == 0) continue
                text = substr(text, 1, i - 1) OLD k NEW \
                       substr(text, i + length(e_old[k]))
                done[k] = 1; touched++
            }
        }

        # resolve every placeholder to its new coordinate
        for (k = 1; k <= n_edit; k++) {
            if (e_ln[k] != ln || !done[k]) continue
            tag = OLD k NEW
            i = index(text, tag)
            if (i > 0)
                text = substr(text, 1, i - 1) e_new[k] \
                       substr(text, i + length(tag))
        }
        src[ln] = text
    }

    if (count_old != "" && count_new != "")
        for (i = 1; i <= nl; i++)
            if (index(src[i], count_old " lines")) {
                sub(count_old " lines", count_new " lines", src[i]); break
            }

    tmp = doc ".repoint"
    for (i = 1; i <= nl; i++) print src[i] > tmp
    close(tmp)
    system("mv " tmp " " doc)

    printf "repointed %d coordinates\n", touched
    if (count_new != "") printf "line count %s -> %s\n", count_old, count_new
    if (n_amb > 0) {
        printf "%d ambiguous claim(s) LEFT ALONE -- repair by line shift:\n", n_amb > "/dev/stderr"
        for (i = 1; i <= n_amb; i++) printf "  %s\n", amb[i] > "/dev/stderr"
    }
}
