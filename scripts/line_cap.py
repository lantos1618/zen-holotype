#!/usr/bin/env python3
"""STYLE.md's line caps, enforced.

    over 500 lines: justify or split   -- a prompt, printed, never a failure
    over 800 lines: fails the build    -- unless listed below with a reason

The rule said "fails the build" and nothing failed. A file crossed 800 during
an ordinary change and the only reason anyone noticed was that its author
happened to read the rule and split by hand. That is the gate-that-guards-
nothing pattern: the sentence in STYLE.md read as coverage while asserting
nothing at all.

WHY THE EXCEPTIONS LIVE HERE and not in a `build.zen`. STYLE.md named
`build.zen`, and there is no project-level one -- `src/std/build/build.zen` is
the Builder API a project's own build file is handed, not this repo's. An
exception you have to type a sentence for is an exception someone will read,
and that property is what matters; a dict with a mandatory reason has it. When
this repo grows a real build.zen, move them and update STYLE.md.

The caps are about a file having two subjects. The line count is only how you
find out, so an exception is a claim that a long file is genuinely ONE subject
-- not a claim that splitting is inconvenient.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SOFT, HARD = 500, 800

# Not read, so not capped: generated output and the test corpus.
EXEMPT_DIRS = ("seed", "tests", "grammar/src", ".fixpoint", ".fixloop")

# path -> the sentence. No entry without one.
EXCEPTIONS: dict[str, str] = {
    "src/gen/gen_c/gen_c_member.zen":
        "member access codegen, one lowering per base shape — the vertical "
        "formatter stretched it past the cap; the subject is one.",
    "src/gen/gen_c/gen_c_state.zen":
        "the emitter's state and its constructors — one subject; the "
        "formatter's vertical breaking, not a second subject, crossed 800.",
    "src/sema/sema_call.zen":
        "call checking, one question from candidate to memo — over the cap "
        "only since the formatter broke long call sites one per line.",
    "src/sema/sema_check.zen":
        "the Checker and its memos — one subject; the reformat added the "
        "lines, and splitting by size would name two files after nothing.",
    "src/sema/sema_def.zen":
        "visibility: defs_of and the walk behind it — one subject, pushed "
        "over 800 by vertical breaking, a candidate for a subject split "
        "only if a second query family ever lands here.",
    # ELEVEN AT ONCE, and they share one cause: `fmt_break.zen` learned
    # parameter lists, so every signature past 80 columns went from a
    # hand-wrapped two lines to one parameter per line. None of these
    # files gained a subject; each gained 90-280 lines of the same one.
    # That the cap now needs eleven excuses is the honest reading: a
    # formatter that only ever grows a file makes a LINE COUNT a weaker
    # proxy for "two subjects" than it was, and the next person to touch
    # this list should ask whether the proxy still earns its place rather
    # than write a twelfth sentence.
    "src/gen/gen_c/gen_c_call.zen":
        "lowering a call, from callee through arguments to the emitted "
        "expression — one subject, and the longest signatures in the "
        "backend are here, which is why the reformat cost it the most.",
    "src/gen/gen_c/gen_c_decl.zen":
        "emitting a declaration, one form per arm — one subject; the "
        "reformat added the lines.",
    "src/gen/gen_c/gen_c_expr.zen":
        "the expression dispatch and its leaves — one subject; the "
        "reformat added the lines.",
    "src/gen/gen_c/gen_c_fat.zen":
        "fat pointers: their layout, construction and every read through "
        "one — one subject; the reformat added the lines.",
    "src/gen/gen_c/gen_c_layout.zen":
        "C layout of a Zen type, one question answered per shape — one "
        "subject; the reformat added the lines.",
    "src/gen/gen_c/gen_c_loop.zen":
        "lowering the loop forms — one subject; the reformat added the "
        "lines.",
    "src/gen/gen_c/gen_c_op.zen":
        "operators: one lowering per operator and operand shape — one "
        "subject; the reformat added the lines.",
    "src/gen/gen_c/gen_c_runtime.zen":
        "the runtime surface the backend emits calls into — one subject; "
        "the reformat added the lines.",
    "src/gen/gen_c/gen_c_sink.zen":
        "where a value lands: the sink protocol and its cases — one "
        "subject; the reformat added the lines.",
    "src/gen/gen_c/gen_c_try.zen":
        "lowering `try` and the error paths it opens — one subject; the "
        "reformat added the lines.",
    "src/sema/sema_match.zen":
        "checking a match: patterns, arms, exhaustiveness — one subject "
        "with three questions about it; the reformat added the lines.",
    # A TWELFTH, and the paragraph above asked for it to be argued rather
    # than written. The argument: this file's subject is WHAT SHAPE A
    # LIST TAKES, and joining and breaking are the two directions of that
    # one decision — a rule that only broke could ratify whatever a human
    # typed, which is why the join is here and not elsewhere. Splitting
    # them leaves two files neither of which can answer the question.
    "src/fmt/fmt_break.zen":
        "what shape a list takes: packed to one line, or broken one item "
        "per line — one decision in two directions, and the second half "
        "is what makes the first a rule rather than a ratification.",
}


def zen_files():
    for path in sorted(ROOT.glob("src/**/*.zen")):
        rel = path.relative_to(ROOT).as_posix()
        if any(rel.startswith(d + "/") for d in EXEMPT_DIRS):
            continue
        yield rel, path


def main() -> int:
    over_hard, over_soft = [], []
    for rel, path in zen_files():
        n = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        if n > HARD and rel not in EXCEPTIONS:
            over_hard.append((rel, n))
        elif n > SOFT:
            over_soft.append((rel, n, rel in EXCEPTIONS))

    for rel, n, excused in over_soft:
        note = f"  (excused past {HARD}: {EXCEPTIONS[rel]})" if excused else ""
        print(f"note: {rel}: {n} lines, over {SOFT} — name its subjects out loud{note}")

    for rel, n in over_hard:
        print(f"{rel}: {n} lines, over the {HARD}-line cap")
        print("    split it by SUBJECT — never by size, because two halves of one")
        print("    subject leave two names that mean nothing. If it is genuinely one")
        print(f"    subject, add it to EXCEPTIONS in {Path(__file__).name} with the")
        print("    sentence saying why.")

    print(f"line_cap: {len(over_soft)} over {SOFT}, {len(over_hard)} over {HARD}")
    return 1 if over_hard else 0


if __name__ == "__main__":
    sys.exit(main())
