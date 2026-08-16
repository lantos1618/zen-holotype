#!/usr/bin/env python3
"""The grammar's contract, both halves -- the gate `tree-sitter test` never was.

`make grammar-test` used to be `cd grammar && npx tree-sitter test`, and it
reported "Total parses: 0; successful parses: 0; failed parses: 0", exit 0:
grammar/ has no test/ or corpus/ directory, so there was nothing to run and
the target passed unconditionally. A gate that passes on an empty set is worse
than no target -- it reads as coverage and guards nothing.

The two halves of the real check already existed as files; nothing executed
them:

  NEGATIVE  tests/parse/errors/*.zen exist IN ORDER NOT TO PARSE
            (docs/LEXER_BOOTSTRAP_FIXES.md:475). Each one is a syntax
            the language rejects. If the grammar accepts one, that is a real
            bug -- the parser now blesses what the language forbids -- and
            this gate fails naming the file. The fix is never to delete the
            fixture or weaken this check; it is to fix the grammar, or to
            move the file out with a sentence in constructs.md saying why
            the syntax is now legal.

            Three fixtures left this directory the day this gate first ran,
            because the grammar accepts them BY DESIGN: grammar.js D13 keeps
            parameter types optional in the grammar (closures infer them) and
            rejects the shapes one stage later, in cst.py and sema. A file
            that parses is not a parse-negative, so they now live where their
            rejection is actually asserted -- bare_self_param and
            match_arm_paren_form as tests/must-fail/ tests with .expected
            diagnostics, and fn_type_unnamed_params deleted as a duplicate of
            the tests/must-fail/parse/ test that already gated the rule.

  POSITIVE  every .zen under tests/corpus/ and example/ must parse. A
            grammar regression that REJECTS valid Zen is caught here, not by
            the negatives. src/ is deliberately NOT in this set: `make parse`
            already gates it, and a grammar check that reddens because a
            half-written compiler module does not parse is reporting the
            wrong thing.

    0   every negative rejected, every positive parsed
    1   at least one file broke its half of the contract
    2   the harness could not run: no grammar/zen.so, or a fixture set came
        up empty -- which would make this the empty-set gate again

2 is NOT a pass. The file counts are printed on green for the same reason:
`23 negative(s) rejected` dropping to a smaller number is how you find out
the fixtures moved and the check quietly stopped reading them.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAMMAR = ROOT / "grammar"

NEGATIVE_DIR = ROOT / "tests" / "parse" / "errors"
POSITIVE_DIRS = (ROOT / "tests" / "corpus", ROOT / "example")

# One batch invocation per positive directory in the common case; a failing
# batch is re-run file by file so the failure names its file.
TIMEOUT = 120


def parse_batch(paths: list[Path]) -> subprocess.CompletedProcess:
    """tree-sitter parse over many files at once. Exit 1 if ANY has an error
    node -- which is exactly what --quiet hides, so the exit code is the whole
    result here."""
    return subprocess.run(
        ["npx", "tree-sitter", "parse", "--quiet", *[str(p) for p in paths]],
        cwd=GRAMMAR, capture_output=True, text=True, timeout=TIMEOUT,
    )


def parse_one(path: Path) -> bool:
    """True if the file parses clean."""
    run = subprocess.run(
        ["npx", "tree-sitter", "parse", "--quiet", str(path)],
        cwd=GRAMMAR, capture_output=True, text=True, timeout=TIMEOUT,
    )
    return run.returncode == 0


def main() -> int:
    if not (GRAMMAR / "zen.so").exists():
        print("grammar_test: run `make grammar` first", file=sys.stderr)
        return 2

    negatives = sorted(NEGATIVE_DIR.glob("*.zen"))
    positives = [p for d in POSITIVE_DIRS for p in sorted(d.rglob("*.zen"))]
    if not negatives:
        print(f"grammar_test: no fixtures in {NEGATIVE_DIR.relative_to(ROOT)} --"
              " the negative half is checking nothing", file=sys.stderr)
        return 2
    if not positives:
        print("grammar_test: no positive fixtures found -- the positive half"
              " is checking nothing", file=sys.stderr)
        return 2

    failures: list[str] = []

    # The negative half: each file must FAIL to parse. Run per file from the
    # start -- the report has to name the file either way, and a batch can
    # only say "something in here parsed".
    for path in negatives:
        rel = path.relative_to(ROOT).as_posix()
        try:
            accepted = parse_one(path)
        except subprocess.TimeoutExpired:
            accepted = False
            failures.append(f"{rel}: the parser hung on a file that exists to"
                            " be rejected; a rejection must terminate")
        if accepted:
            failures.append(
                f"{rel}: PARSES CLEAN, but it exists because the language"
                " rejects this syntax. The grammar now accepts it -- that is"
                " a grammar bug, not a fixture bug. Fix the grammar; do not"
                " delete the file."
            )

    # The positive half: batch first, per-file only to name a failure.
    parsed = 0
    for d in POSITIVE_DIRS:
        paths = [p for p in positives if p.is_relative_to(d)]
        try:
            batch = parse_batch(paths)
        except subprocess.TimeoutExpired:
            batch = subprocess.CompletedProcess([], 1, "", "timed out")
        if batch.returncode == 0:
            parsed += len(paths)
            continue
        for path in paths:
            rel = path.relative_to(ROOT).as_posix()
            try:
                ok = parse_one(path)
            except subprocess.TimeoutExpired:
                ok = False
            if ok:
                parsed += 1
            else:
                failures.append(
                    f"{rel}: no longer parses. Either the grammar regressed"
                    " or the file did -- this file parsed the last time the"
                    " gate ran."
                )

    for line in failures:
        print(line)
    print(f"grammar_test: {len(negatives) - sum('PARSES CLEAN' in f for f in failures)}"
          f"/{len(negatives)} negative(s) rejected, "
          f"{parsed}/{len(positives)} positive(s) parsed, "
          f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
