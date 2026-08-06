#!/usr/bin/env python3
"""tests/lint.py -- the format checker for tests/corpus and tests/must-fail.

docs/TESTING.md § "The test file format" is the specification; this file is its
enforcement. It is deliberately an independent scan rather than a reuse of
tests/run.py's discovery: the runner is permissive so that a malformed test
still runs where it can, and a lint that shares the runner's permissiveness
cannot see what the runner tolerated.

    0   every test conforms
    1   at least one violation
    2   the tree could not be read

Usage:

    tests/lint.py                       # human-readable report
    tests/lint.py --errors-only
    tests/lint.py --markdown > tests/FORMAT-VIOLATIONS.md
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

TESTS_DIR = Path(__file__).resolve().parent

KNOWN_SUFFIXES = {".zen", ".expected", ".exit", ".stderr", ".count", ".stage"}
POSITION = re.compile(r"^(?:(?P<path>[^\s:]+):)?(?P<line>\d+):(?P<col>\d+)$")
MERGED = re.compile(r"^(?P<path>[^\s:]+):(?P<line>\d+):(?P<col>\d+):\s*\S")

ERROR = "ERROR"
WARN = "WARN"
INFO = "INFO"

# rule id -> (severity, one-line statement of the rule)
RULES: dict[str, tuple[str, str]] = {
    "orphan-zen": (ERROR, "a .zen file that belongs to no test: it never runs, so it cannot go red"),
    "orphan-expected": (ERROR, "an .expected with no .zen beside it"),
    "orphan-aux": (ERROR, "an .exit/.stderr with no test beside it"),
    "foreign-file": (ERROR, "a file whose suffix is not one TESTING.md names"),
    "doc-file": (WARN, "prose inside a suite; TESTING.md does not provide for it"),
    "dir-entry-name": (ERROR, "a directory test's entry point must be main.zen"),
    "dir-expected-name": (ERROR, "a directory test's expectation lives at the directory root"),
    "dir-no-expected": (ERROR, "a directory holding an entry point but no expectation"),
    "dir-module-shape": (ERROR, "a submodule folder must contain <folder>.zen"),
    "mf-empty": (ERROR, ".expected is empty: the test asserts nothing"),
    "mf-merged-position": (ERROR, "message and position merged on line 1; the position must be its own line"),
    "mf-no-position": (ERROR, ".expected asserts no position; TESTING.md requires message AND position"),
    "mf-bad-position": (ERROR, "a position line that is not path:line:col or line:col"),
    "mf-zero-position": (ERROR, "a position with a 0 line or column; both are 1-based"),
    "mf-blank-line": (WARN, "a blank line inside .expected"),
    "mf-aux-file": (ERROR, "a must-fail test carries .exit/.stderr, which the format does not define"),
    "mf-bare-position": (ERROR, "bare line:col in a DIRECTORY test, which has no single entry to resolve against"),
    "corpus-exit-zero": (WARN, ".exit holds 0; TESTING.md says omit the file when it is 0"),
    "corpus-exit-bad": (ERROR, ".exit is not a single integer in 0..255"),
    "corpus-expected-crlf": (ERROR, ".expected contains a CR; stdout is compared byte for byte"),
    "corpus-expected-bom": (ERROR, ".expected starts with a UTF-8 BOM"),
    "corpus-no-trailing-newline": (WARN, "non-empty .expected does not end in a newline; println appends one"),
    "corpus-empty-stderr": (ERROR, "an empty .stderr asserts nothing"),
    "corpus-weak": (WARN, "empty stdout, exit 0 and no .stderr: nothing observable is asserted"),
    "name-shape": (WARN, "a test name containing whitespace or an uppercase letter"),
}


# The central fix for a rule that fires across a whole suite. A hundred rows of
# the same violation is one decision, not a hundred.
CENTRAL_FIX: dict[str, str] = {
    "mf-bare-position": (
        "Amend `docs/TESTING.md` to say the path may be omitted for a single-file "
        "test, where it can only mean that file. Four suites independently chose "
        "the bare form, which is the tell that the spec asked for something nobody "
        "wanted to write. `tests/run.py` already resolves a bare `line:col` against "
        "the test's entry file, so blessing it costs nothing; the alternative is "
        "editing 92 files to add a redundant filename."
    ),
    "mf-merged-position": (
        "One suite wrote `path:line:col: message` on a single line. Split each into "
        "two lines. The runner cannot accept the merged form without also accepting "
        "a test that asserts a message and no position, which is exactly the "
        "assertion `TESTING.md` says decays fastest."
    ),
    "corpus-exit-zero": (
        "Delete every `.exit` that holds `0`; an absent `.exit` already means 0. "
        "Keeping them is harmless to the runner and corrosive to the format: the "
        "next author copies the directory and now `.exit` looks required."
    ),
    "doc-file": (
        "Have `TESTING.md` permit one `README.md` per area. Both files here are "
        "worth keeping, and a format that has no room for prose gets prose anyway."
    ),
}


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str  # repo-relative
    suite: str  # "corpus/lex"
    detail: str
    fix: str

    @property
    def severity(self) -> str:
        return RULES[self.rule][0]


class Linter:
    def __init__(self, tests_dir: Path) -> None:
        self.tests_dir = tests_dir
        self.findings: list[Finding] = []
        self.tests = 0
        self.dir_tests = 0

    # ---------------------------------------------------------------- helpers

    def rel(self, path: Path) -> str:
        try:
            return path.relative_to(self.tests_dir.parent).as_posix()
        except ValueError:
            return str(path)

    def flag(self, rule: str, path: Path, suite: str, detail: str, fix: str) -> None:
        self.findings.append(Finding(rule, self.rel(path), suite, detail, fix))

    @staticmethod
    def suite_of(kind: str, path: Path, base: Path) -> str:
        rel = path.relative_to(base)
        return f"{kind}/{rel.parts[0]}" if len(rel.parts) > 1 else kind

    # -------------------------------------------------------------- the scan

    def run(self) -> None:
        for kind in ("corpus", "must-fail"):
            base = self.tests_dir / kind
            if not base.is_dir():
                raise SystemExit(f"lint.py: missing {base}")
            self.scan_group(kind, base, base)

    def scan_group(self, kind: str, base: Path, d: Path) -> None:
        """`d` is a grouping directory: an area, or the suite root."""
        for child in sorted(d.iterdir(), key=lambda p: p.name):
            suite = self.suite_of(kind, child, base)
            if child.is_dir():
                entry = self.dir_entry(child)
                expected = self.dir_expected(child)
                if entry or expected:
                    self.check_dir_test(kind, base, child, entry, expected)
                else:
                    self.scan_group(kind, base, child)
            else:
                self.check_flat_file(kind, base, child, suite)

    @staticmethod
    def dir_entry(d: Path) -> Path | None:
        for candidate in (d / "main.zen", d / f"{d.name}.zen"):
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def dir_expected(d: Path) -> Path | None:
        for name in (".expected", f"{d.name}.expected", "main.expected"):
            if (d / name).is_file():
                return d / name
        return None

    # ------------------------------------------------------------- flat form

    def check_flat_file(self, kind: str, base: Path, f: Path, suite: str) -> None:
        if f.suffix not in KNOWN_SUFFIXES:
            if f.suffix == ".md":
                self.flag("doc-file", f, suite, f"{f.name} is prose, not a test",
                          "keep it and have TESTING.md permit one README per area, "
                          "or move it under docs/")
            else:
                self.flag("foreign-file", f, suite,
                          f"{f.name} is not part of the test format",
                          "the runner ignores it, so whatever it asserts is asserted "
                          "nowhere: move it out, or have TESTING.md name it")
            return

        stem = f.with_suffix("")
        zen, expected = stem.with_suffix(".zen"), stem.with_suffix(".expected")

        if f.suffix == ".zen":
            if not expected.is_file():
                self.flag(
                    "orphan-zen", f, suite,
                    "no sibling .expected, so tests/run.py never collects it",
                    f"add {expected.name} ("
                    + ("message line then one position per line"
                       if kind == "must-fail" else "the exact stdout")
                    + ")",
                )
                return
            self.tests += 1
            self.check_name(f, suite)
            if kind == "must-fail":
                self.check_must_fail(expected, f.name, suite)
                for aux in (".exit", ".stderr"):
                    extra = stem.with_suffix(aux)
                    if extra.is_file():
                        self.flag(
                            "mf-aux-file", extra, suite,
                            f"{extra.name} beside a must-fail test",
                            f"fold it into {expected.name}: the diagnostic is the assertion",
                        )
            else:
                self.check_corpus(expected, stem, suite)
            return

        if not zen.is_file():
            rule = "orphan-expected" if f.suffix == ".expected" else "orphan-aux"
            self.flag(
                rule, f, suite,
                f"no {zen.name} beside it",
                f"add {zen.name}, or delete {f.name}",
            )

    def check_name(self, f: Path, suite: str) -> None:
        name = f.with_suffix("").name
        if any(c.isspace() for c in name) or name != name.lower():
            self.flag("name-shape", f, suite, f"test name {name!r}",
                      "use lower_snake_case with no spaces")

    # -------------------------------------------------------- directory form

    def check_dir_test(
        self, kind: str, base: Path, d: Path, entry: Path | None, expected: Path | None
    ) -> None:
        suite = self.suite_of(kind, d, base)
        if entry is None:
            self.flag(
                "dir-no-expected", d, suite,
                "an expectation file but no main.zen",
                "add main.zen as the entry point",
            )
            return
        if expected is None:
            self.flag(
                "dir-no-expected", d, suite,
                "an entry point but no expectation at the directory root",
                "add .expected at the directory root",
            )
            return

        self.tests += 1
        self.dir_tests += 1

        if entry.name != "main.zen":
            self.flag(
                "dir-entry-name", entry, suite,
                f"entry point is {entry.name}, not main.zen",
                f"rename {entry.name} to main.zen "
                "(TESTING.md: \"the entry point is main.zen\")",
            )
        if expected.name not in ("main.expected", ".expected"):
            self.flag(
                "dir-expected-name", expected, suite,
                f"expectation is {expected.name}",
                "rename to main.expected, matching the main.zen it sits beside",
            )

        for sub in sorted(p for p in d.iterdir() if p.is_dir()):
            if not (sub / f"{sub.name}.zen").is_file():
                self.flag(
                    "dir-module-shape", sub, suite,
                    f"{sub.name}/ has no {sub.name}.zen",
                    "module trees are <folder>/<folder>.zen",
                )

        for aux in d.iterdir():
            if aux.is_file() and aux.suffix not in KNOWN_SUFFIXES and aux.name not in (
                ".expected", ".exit", ".stderr", ".count", ".stage"
            ):
                self.flag("foreign-file", aux, suite, f"{aux.name} at a test root",
                          "remove it or have TESTING.md name it")

        if kind == "must-fail":
            self.check_must_fail(expected, entry.name, suite, is_dir=True)
            for name in (".exit", ".stderr", f"{d.name}.exit", f"{d.name}.stderr"):
                if (d / name).is_file():
                    self.flag("mf-aux-file", d / name, suite,
                              f"{name} beside a must-fail test",
                              "fold it into .expected")
        else:
            self.check_corpus(expected, None, suite, dir_root=d)

    # ---------------------------------------------------------- the contents

    def check_must_fail(self, expected: Path, entry_name: str, suite: str,
                        is_dir: bool = False) -> None:
        text = expected.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if not text.strip():
            self.flag("mf-empty", expected, suite, "empty file",
                      "line 1 is a message substring; each line after it is a position")
            return

        first = lines[0].strip()
        merged = MERGED.match(first)
        if merged:
            pos = f"{merged['path']}:{merged['line']}:{merged['col']}"
            message = first[merged.end("col") + 1:].strip()
            self.flag(
                "mf-merged-position", expected, suite,
                f"line 1 is {first!r}",
                f"split into two lines: {message!r} then {pos!r}",
            )
            return

        positions = [ln for ln in lines[1:]]
        if any(ln.strip() == "" for ln in positions):
            self.flag("mf-blank-line", expected, suite, "a blank line after line 1",
                      "delete it; every line after line 1 is a position")
        positions = [ln.strip() for ln in positions if ln.strip()]

        if not positions:
            self.flag(
                "mf-no-position", expected, suite,
                "only a message line",
                f"add the position the diagnostic must report, e.g. {entry_name}:<line>:<col>",
            )
            return

        bare: list[str] = []
        for raw in positions:
            m = POSITION.match(raw)
            if not m:
                self.flag("mf-bad-position", expected, suite, f"{raw!r}",
                          "write path:line:col (path relative to the test root) or line:col")
                continue
            if int(m["line"]) == 0 or int(m["col"]) == 0:
                self.flag("mf-zero-position", expected, suite, f"{raw!r}",
                          "line and column are both 1-based")
            if m["path"] is None:
                bare.append(raw)
        if bare and is_dir:
            # TESTING.md blesses the bare form for SINGLE-FILE tests, where it
            # resolves against the one entry. A directory has several files and
            # nothing to resolve against, so there the path is not optional.
            # One finding per file: 100+ rows of the same thing is a wall.
            self.flag(
                "mf-bare-position", expected, suite,
                f"{len(bare)} position(s) omit the path: {', '.join(bare)}",
                f"prefix each with the file it belongs to; a directory test has "
                "more than one, so there is nothing for a bare position to mean",
            )

    def check_corpus(
        self, expected: Path, stem: Path | None, suite: str, dir_root: Path | None = None
    ) -> None:
        data = expected.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            self.flag("corpus-expected-bom", expected, suite, "leading UTF-8 BOM",
                      "strip it; stdout is compared byte for byte")
        if b"\r" in data:
            self.flag("corpus-expected-crlf", expected, suite, "contains CR",
                      "convert to LF endings")
        if data and not data.endswith(b"\n"):
            self.flag("corpus-no-trailing-newline", expected, suite, "no final newline",
                      "add one, or confirm the program's last write has none")

        if dir_root is not None:
            exit_path = next((dir_root / n for n in (".exit", f"{dir_root.name}.exit", "main.exit")
                              if (dir_root / n).is_file()), None)
            stderr_path = next((dir_root / n for n in (".stderr", f"{dir_root.name}.stderr",
                                                       "main.stderr")
                                if (dir_root / n).is_file()), None)
        else:
            assert stem is not None
            exit_path = stem.with_suffix(".exit")
            exit_path = exit_path if exit_path.is_file() else None
            stderr_path = stem.with_suffix(".stderr")
            stderr_path = stderr_path if stderr_path.is_file() else None

        code = 0
        if exit_path is not None:
            raw = exit_path.read_text(encoding="utf-8", errors="replace").strip()
            try:
                code = int(raw)
                if not 0 <= code <= 255:
                    raise ValueError
            except ValueError:
                self.flag("corpus-exit-bad", exit_path, suite, f"{raw!r}",
                          "one integer in 0..255, nothing else")
                code = -1
            else:
                if code == 0:
                    self.flag("corpus-exit-zero", exit_path, suite, "holds 0",
                              f"delete {exit_path.name}; an absent .exit means 0")

        if stderr_path is not None and not stderr_path.read_bytes().strip():
            self.flag("corpus-empty-stderr", stderr_path, suite, "empty file",
                      f"delete {stderr_path.name}, or write the substring it should assert")

        if not data and code == 0 and stderr_path is None:
            self.flag("corpus-weak", expected, suite,
                      "empty stdout, exit 0, no .stderr",
                      "assert something observable, or delete the test")


# --------------------------------------------------------------- reporting


def group(findings: Sequence[Finding]) -> dict[str, list[Finding]]:
    out: dict[str, list[Finding]] = {}
    for f in findings:
        out.setdefault(f.suite, []).append(f)
    for items in out.values():
        items.sort(key=lambda f: (f.severity != ERROR, f.path, f.rule))
    return dict(sorted(out.items()))


def report_text(lint: Linter, errors_only: bool) -> str:
    findings = [f for f in lint.findings if not errors_only or f.severity == ERROR]
    lines = []
    for suite, items in group(findings).items():
        lines.append(f"\n{suite}  ({len(items)})")
        for f in items:
            lines.append(f"  {f.severity:5} {f.rule:<24} {f.path}")
            lines.append(f"        {f.detail}")
            lines.append(f"        fix: {f.fix}")
    errors = sum(1 for f in lint.findings if f.severity == ERROR)
    warns = len(lint.findings) - errors
    lines.append(
        f"\nlint.py: {lint.tests} test(s) ({lint.dir_tests} directory form), "
        f"{errors} error(s), {warns} warning(s)"
    )
    return "\n".join(lines)


def report_markdown(lint: Linter) -> str:
    errors = [f for f in lint.findings if f.severity == ERROR]
    warns = [f for f in lint.findings if f.severity == WARN]
    out: list[str] = []
    add = out.append

    add("# Test format violations")
    add("")
    add("Generated by `tests/lint.py --markdown`. `docs/TESTING.md` §\"The test file")
    add("format\" is the specification; every row below is a file that does not match it.")
    add("")
    add("**Nothing here has been edited.** Ten authors wrote these suites in parallel and")
    add("each one is reported, not fixed, so the owning author makes the change.")
    add("")
    add(f"- tests found: **{lint.tests}** ({lint.dir_tests} in directory form)")
    add(f"- errors: **{len(errors)}** — the test does not run, or runs without asserting")
    add(f"- warnings: **{len(warns)}** — it runs, but the format says otherwise")
    add("")

    add("## Count by suite")
    add("")
    add("| suite | errors | warnings |")
    add("|---|---:|---:|")
    grouped = group(lint.findings)
    for suite, items in grouped.items():
        e = sum(1 for f in items if f.severity == ERROR)
        w = len(items) - e
        add(f"| `{suite}` | {e} | {w} |")
    add(f"| **total** | **{len(errors)}** | **{len(warns)}** |")
    add("")

    by_rule: dict[str, list[Finding]] = {}
    for f in lint.findings:
        by_rule.setdefault(f.rule, []).append(f)

    systemic = sorted(
        ((r, items) for r, items in by_rule.items() if len(items) >= 5),
        key=lambda kv: -len(kv[1]),
    )
    if systemic:
        add("## The systemic ones")
        add("")
        add("Rules that fired across a whole suite. Each is one decision, not N edits.")
        for rule, items in systemic:
            suites = sorted({f.suite for f in items})
            add("")
            add(f"### `{rule}` — {len(items)} file(s), {RULES[rule][0]}")
            add("")
            add(f"*{RULES[rule][1]}.* In: {', '.join('`' + s + '`' for s in suites)}.")
            add("")
            add(CENTRAL_FIX.get(rule, items[0].fix))
        add("")

    add("## Rules")
    add("")
    add("| rule | severity | what it means |")
    add("|---|---|---|")
    used = {f.rule for f in lint.findings}
    for rule, (sev, text) in RULES.items():
        if rule in used:
            add(f"| `{rule}` | {sev} | {text} |")
    add("")

    add("## The spec decided these; one migration is outstanding")
    add("")
    add("`docs/TESTING.md` is authoritative. Every question this report used to")
    add("carry has since been answered there, and they are listed so nobody")
    add("re-opens one:")
    add("")
    add("1. **A directory test names its expectation `main.expected`** — it matches")
    add("   the `main.zen` already mandated, and a dotfile is invisible to `ls` and")
    add("   to some `git add` habits. The runner still accepts the literal")
    add("   `.expected` and `<name>.expected`, and **22 tests still use them**. That")
    add("   is a rename, not a question.")
    add("2. **A position may omit its path in a single-file test**, resolving")
    add("   against the entry. A directory test has no single entry, so there it is")
    add("   an error — which is what `mf-bare-position` now means.")
    add("3. **`.count` bounds the diagnostic count**, and `tests/run.py` reads it.")
    add("   It was invented by `must-fail/parse` and read by nothing, which made")
    add("   \"one syntax error must not cascade into fifty\" unenforceable.")
    add("4. **A test\'s compilation root is its own directory**, so every asserted")
    add("   path is relative to it — which is what makes comparing two copies of a")
    add("   tree at different absolute paths a meaningful determinism check.")
    add("")
    add("`.stage` joined the format later: it names the stage a test\'s feature")
    add("arrives at, and a test ahead of `STAGE` is reported deferred rather than")
    add("failed. It is not a skip — a deferred test that PASSES is a failure.")
    add("")

    add("## What is deliberately not a violation")
    add("")
    add("Recorded so nobody 'fixes' one of these:")
    add("")
    add("- **Extra diagnostics beyond those asserted.** A `must-fail` test lists the")
    add("  positions that *must* appear; the compiler may report more. One ownership")
    add("  test legitimately produces two diagnostics.")
    add("- **An empty `.expected`.** The trap corpus prints nothing on stdout and")
    add("  carries its assertion in `.exit` and `.stderr`. That is a real assertion.")
    add("- **A `.stderr` on a corpus test.** It is a substring check, so a trap message")
    add("  can be asserted without pinning the whole stream.")
    add("- **Test names that do not match the source file they exercise.**")
    add("")

    add("## Violations, by suite")
    for suite, items in grouped.items():
        add("")
        add(f"### `{suite}`")
        add("")
        add("| file | rule | detail | fix |")
        add("|---|---|---|---|")
        for f in items:
            detail = f.detail.replace("|", "\\|")
            fix = f.fix.replace("|", "\\|")
            add(f"| `{f.path}` | {f.severity} `{f.rule}` | {detail} | {fix} |")
    add("")
    add("---")
    add("")
    add("Regenerate with `tests/lint.py --markdown > tests/FORMAT-VIOLATIONS.md`.")
    add("`tests/lint.py` exits 1 while any ERROR remains, so this file going stale is")
    add("itself detectable.")
    return "\n".join(out)


def main(argv: Sequence[str]) -> int:
    p = argparse.ArgumentParser(prog="tests/lint.py", description=__doc__.splitlines()[0])
    p.add_argument("--tests", default=str(TESTS_DIR), help="the tests/ directory")
    p.add_argument("--markdown", action="store_true", help="emit the FORMAT-VIOLATIONS report")
    p.add_argument("--errors-only", action="store_true")
    args = p.parse_args(argv)

    tests_dir = Path(args.tests).resolve()
    if not tests_dir.is_dir():
        print(f"lint.py: no such directory: {tests_dir}", file=sys.stderr)
        return 2

    lint = Linter(tests_dir)
    try:
        lint.run()
    except OSError as exc:
        print(f"lint.py: cannot read the tree: {exc}", file=sys.stderr)
        return 2

    if lint.tests == 0:
        print(f"lint.py: no tests found under {tests_dir}", file=sys.stderr)
        return 2

    print(report_markdown(lint) if args.markdown else report_text(lint, args.errors_only))
    return 1 if any(f.severity == ERROR for f in lint.findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
