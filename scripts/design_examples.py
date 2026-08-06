#!/usr/bin/env python3
"""Every complete example in docs/DESIGN.md must parse.

PLAN.md 0.1 asks for this in as many words -- "Every example in DESIGN.md
becomes a parse test. Expect the grammar to surface ambiguities the prose
hides" -- and nothing was checking it. Two real bugs were sitting in the
document when this was first run: the example program was missing a
semicolon on a line whose rule DESIGN.md states 1000 lines earlier, and one
fence mixed a declaration with the statements illustrating its use.

A document nobody executes drifts from the language it defines, and here the
document IS the language, so the drift is the language becoming two things.

FENCE KINDS. A ```groovy fence is a complete compilation unit and must parse.
A ```groovy fragment fence is statements, record fields, or a body with a
literal `..` placeholder -- shown out of context on purpose, so it is read but
not parsed. Marking one costs a word; getting it wrong costs a false green,
which is why `fragment` is the annotation and `groovy` is the default.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "docs" / "DESIGN.md"
GRAMMAR = ROOT / "grammar"

FENCE = re.compile(r"^```groovy( fragment)?$")


def blocks(text: str):
    """(line number, is_fragment, source) for every groovy fence."""
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        end = i + 1
        while end < len(lines) and lines[end] != "```":
            end += 1
        yield i + 1, bool(m.group(1)), "\n".join(lines[i + 1:end])
        i = end + 1


def main() -> int:
    if not (GRAMMAR / "zen.so").exists():
        print("design_examples: run `make grammar` first", file=sys.stderr)
        return 2
    text = DESIGN.read_text(encoding="utf-8")
    checked = skipped = 0
    failures = []
    with tempfile.TemporaryDirectory(prefix="zen-design.") as tmp:
        for line, fragment, source in blocks(text):
            if fragment:
                skipped += 1
                continue
            checked += 1
            path = Path(tmp) / f"design_{line}.zen"
            path.write_text(source, encoding="utf-8")
            run = subprocess.run(
                ["npx", "tree-sitter", "parse", "--quiet", str(path)],
                cwd=GRAMMAR, capture_output=True, text=True,
            )
            if run.returncode != 0:
                where = (run.stdout or run.stderr).strip().splitlines()
                failures.append((line, where[-1] if where else "parse failed"))

    for line, detail in failures:
        print(f"docs/DESIGN.md:{line}: this example does not parse")
        print(f"    {detail}")
        print("    fix the example, or mark the fence ```groovy fragment if it")
        print("    is deliberately shown out of context")
    print(f"design_examples: {checked} example(s) checked, {skipped} fragment(s) "
          f"skipped, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
