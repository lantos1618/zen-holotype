#!/usr/bin/env python3
"""No comment block may sit immediately above a copy of itself.

Found 2026-08-10 during the comment-compression campaign: `gen_c_inline.zen`
held about twelve identical paragraphs pasted back-to-back, and
`gen_c_settle.zen` held six. Together that is over a hundred lines of prose
saying a thing a second time. Nobody wrote it twice on purpose -- it is what a
merge or a bad copy leaves behind, and it survives because a reader who has
already read the paragraph does not notice reading it again.

It is worth a gate rather than a one-time sweep because the artifact recurs
every time a header is copied to make a section banner and then edited on one
side only. That drift is invisible in review: both copies are correct prose,
and the diff shows only the edited one.

ADJACENT, AND ONLY ADJACENT, and the narrowing was forced by a false positive
worth recording. The first version of this gate flagged any block repeated
anywhere in a file, and it reported `sema_call.zen:278` against `:551`: the
same three lines -- "a named helper rather than a `.then` inside the loop
body: a loop binding read inside a nested closure does not resolve" -- above
`keep_one` and again above `keep_fitting`. That is not an artifact. It is one
explanation correctly given for two sibling helpers two hundred lines apart,
and deleting either copy would leave a function undocumented.

So the rule is adjacency: a block, then nothing but blank lines, then the same
block again. Nobody writes that on purpose, and there is no legitimate shape it
collides with. A copy that has drifted to a second home is somebody's judgement
about where a reader needs it, and this gate has no business overruling that.

WHAT COUNTS AS A BLOCK: a run of consecutive lines whose first non-space
characters are `//`, at least MIN_BLOCK lines long. Shorter runs are excluded
because a two-line label above sibling declarations is a label, not prose, and
gating it would train people to reword labels for the linter's benefit.

Leading whitespace is ignored so the same paragraph at two indents is still
caught. Comparison is otherwise exact: a genuine edit to one copy makes them
different blocks and this stops firing, which is correct -- two paragraphs that
differ are no longer a duplicate, they are a contradiction, and that is a
check nothing here can do.

Scope is src/ only: it is the tree that ships, and the one whose comments
a reader is asked to trust.

    0   no file repeats a comment block
    1   at least one does; every occurrence is named with both line numbers
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN = ROOT / "src"

MIN_BLOCK = 3


def blocks(lines: list[str]) -> list[tuple[int, int, tuple[str, ...]]]:
    """Every comment run of at least MIN_BLOCK lines, as (first, last, text)
    with 1-based line numbers."""
    found: list[tuple[int, int, tuple[str, ...]]] = []
    run: list[str] = []
    start = 0
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("//"):
            if not run:
                start = i
            run.append(stripped)
            continue
        if len(run) >= MIN_BLOCK:
            found.append((start, i - 1, tuple(run)))
        run = []
    if len(run) >= MIN_BLOCK:
        found.append((start, len(lines), tuple(run)))
    return found


def main() -> int:
    files = sorted(SCAN.rglob("*.zen"))
    if not files:
        print(f"dup_comments: no .zen files under {SCAN.relative_to(ROOT)} --"
              " this gate is checking nothing", file=sys.stderr)
        return 2

    failures = 0
    wasted = 0
    for path in files:
        lines = path.read_text().splitlines()
        found = blocks(lines)
        for this, nxt in zip(found, found[1:]):
            if this[2] != nxt[2]:
                continue
            # Only blank lines may separate them; anything else means the
            # second copy is documenting a second declaration.
            if any(lines[i].strip() for i in range(this[1], nxt[0] - 1)):
                continue
            failures += 1
            wasted += len(this[2])
            print(f"{path.relative_to(ROOT).as_posix()}:{this[0]}: "
                  f"this {len(this[2])}-line comment block is repeated verbatim "
                  f"at :{nxt[0]} with nothing between them")
            print(f"    | {this[2][0][:96]}")

    if failures:
        print(f"dup_comments: {failures} repeated block(s), "
              f"{wasted} redundant line(s). Keep one copy.")
        return 1
    print(f"dup_comments: {len(files)} files, no repeated comment blocks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
