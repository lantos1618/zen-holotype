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
EXCEPTIONS: dict[str, str] = {}


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
