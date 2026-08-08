#!/usr/bin/env python3
"""tests/run.py -- the corpus and must-fail gate.

Compiles every program under tests/corpus/ and tests/must-fail/ and checks it
against its recorded expectations. The format is specified in docs/TESTING.md
("The test file format"); this runner reads only that.

    0   every selected test passed
    1   a test failed -- the compiler is wrong, or the test is
    2   the harness could not run: no compiler, no C compiler, an unreadable
        test, or a selection that matched nothing

2 is NOT a pass. A gate that succeeds when it cannot run reads as coverage and
guards nothing (PLAN.md: "before trusting a new gate, break the thing it
guards on purpose and watch it go red").

Usage:

    tests/run.py                          # everything, via bootstrap/bootstrap.py
    tests/run.py --list                   # names only, no compiler needed
    tests/run.py --filter 'corpus/lex/*'  # a glob over the test id
    tests/run.py --jobs 8
    tests/run.py --toolchain zen --zen ./zen
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent

CORPUS = "corpus"
MUST_FAIL = "must-fail"

# `.expected` at a directory root is the spelling TESTING.md's multi-file
# paragraph reads most naturally, and the one the modules suite used. The two
# alternates are accepted because other suites used them; tests/lint.py names
# them as violations rather than the runner silently blessing them.
DIR_EXPECTED_NAMES = (".expected", "{name}.expected", "main.expected")
DIR_EXIT_NAMES = (".exit", "{name}.exit", "main.exit")
DIR_STDERR_NAMES = (".stderr", "{name}.stderr", "main.stderr")
DIR_COUNT_NAMES = (".count", "{name}.count", "main.count")
DIR_STAGE_NAMES = (".stage", "{name}.stage", "main.stage")
DIR_STDIN_NAMES = (".stdin", "{name}.stdin", "main.stdin")

# What the compiler prints once it is done: `bootstrap: 3 diagnostic(s)`.
# `.count` is the only assertion that needs it, and it is the only one that
# cannot fall back to reading the diagnostics themselves -- two diagnostics
# on one position are two, and the position list cannot tell.
DIAG_TOTAL = re.compile(r"(\d+) diagnostic\(s\)")

# The module named by an import's right-hand side: `Res* = std.core.result`
# and `Kind, Pos = leaf` both name their first component. Module paths are
# lowercase by convention, which is what keeps `= Package(..)` out.
IMPORT_RHS = re.compile(r"=\s*([a-z][A-Za-z0-9_]*)\s*(?:\.|$)")

# A diagnostic position as it appears in compiler output: path:line:col, or a
# bare line:col at the start of a line for a single-file compilation.
POS_WITH_PATH = re.compile(r"(?<![\w./-])([\w./+-]+\.zen):(\d+):(\d+)")
POS_BARE = re.compile(r"(?m)^\s*(\d+):(\d+)(?=:|\s|$)")

# A crash is not a rejection. If the compiler dies this way, a must-fail test
# must not be allowed to read as a pass.
CRASH_MARKERS = (
    "Traceback (most recent call last)",
    "AssertionError",
    "RecursionError",
    "Segmentation fault",
)


class HarnessError(Exception):
    """The harness cannot do its job. Never a test result."""


def _current_stage() -> int:
    """The PLAN.md stage the tree is being graded against, from `STAGE` at the
    repo root. One fact, one place: the Makefile reads the same file, and a
    stage duplicated in two places is one stale stage waiting to happen."""
    path = REPO_ROOT / "STAGE"
    try:
        return int(path.read_text(encoding="utf-8").split("#", 1)[0].strip())
    except (OSError, ValueError) as exc:
        raise HarnessError(
            f"{path}: expected one stage number (see docs/PLAN.md)"
        ) from exc


# --------------------------------------------------------------- test model


@dataclass
class Test:
    tid: str  # "corpus/lex/bom_utf8"
    kind: str  # CORPUS | MUST_FAIL
    suite: str  # "lex"
    source: Path  # what is handed to the compiler: a .zen file or a directory
    entry: Path  # the entry .zen file (main.zen for a directory test)
    expected_path: Path
    expected: bytes
    exit_code: int = 0
    exit_path: Path | None = None
    stderr_lines: tuple[str, ...] = ()
    stderr_path: Path | None = None
    count_max: int | None = None
    count_path: Path | None = None
    stage_at: int | None = None
    stage_path: Path | None = None
    # `.stdin` is fed to the PROGRAM, never to the compiler. A capability is
    # only tested by exercising it, and `std.env.Stdin` cannot be reached by a
    # program the harness hands an empty stream. Absent means /dev/null, which
    # is what every test that does not read stdin still gets.
    stdin_bytes: bytes | None = None
    stdin_path: Path | None = None
    is_dir: bool = False

    @property
    def message(self) -> str:
        """must-fail: line 1 of .expected, a substring of the diagnostic."""
        text = self.expected.decode("utf-8", "replace")
        return text.splitlines()[0].strip() if text.strip() else ""

    @property
    def positions(self) -> tuple[str, ...]:
        """must-fail: every line after line 1, each a position that must appear."""
        text = self.expected.decode("utf-8", "replace")
        return tuple(ln.strip() for ln in text.splitlines()[1:] if ln.strip())


@dataclass
class Result:
    test: Test
    ok: bool
    reasons: list[str] = field(default_factory=list)
    detail: str = ""


@dataclass
class Collection:
    tests: list[Test] = field(default_factory=list)
    uncollected: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


# ----------------------------------------------------------------- discovery


def _first_existing(d: Path, names: Sequence[str], stem: str) -> Path | None:
    for pattern in names:
        candidate = d / pattern.format(name=stem)
        if candidate.is_file():
            return candidate
    return None


def _dir_entry(d: Path) -> Path | None:
    for candidate in (d / "main.zen", d / f"{d.name}.zen"):
        if candidate.is_file():
            return candidate
    return None


def _read_exit(path: Path) -> int:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise HarnessError(f"{path}: unreadable ({exc})") from exc
    if not raw:
        raise HarnessError(f"{path}: empty; an exit file must hold one integer")
    try:
        value = int(raw)
    except ValueError as exc:
        raise HarnessError(f"{path}: {raw!r} is not an integer") from exc
    if not 0 <= value <= 255:
        raise HarnessError(f"{path}: exit code {value} is outside 0..255")
    return value


def _read_stage(path: Path) -> int:
    """`.stage` names the PLAN.md stage a test's feature arrives at. A test
    ahead of the current stage cannot pass yet, and a permanently-red test is
    not free: people learn to read past red, which is the same damage a gate
    that cannot fail does from the other direction.

    It is not a skip. The test still runs -- see `stage_verdict`."""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise HarnessError(f"{path}: unreadable ({exc})") from exc
    try:
        value = int(raw)
    except ValueError as exc:
        raise HarnessError(f"{path}: {raw!r} is not a stage number") from exc
    if value < 0:
        raise HarnessError(f"{path}: stage {value} does not exist")
    return value


def _read_count(path: Path) -> int:
    """`.count` bounds the number of diagnostics; TESTING.md says only write
    one where the count is the property under test. Zero would assert the
    program is accepted, which is what a corpus test is for."""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise HarnessError(f"{path}: unreadable ({exc})") from exc
    if not raw:
        raise HarnessError(f"{path}: empty; a count file must hold one integer")
    try:
        value = int(raw)
    except ValueError as exc:
        raise HarnessError(f"{path}: {raw!r} is not an integer") from exc
    if value < 1:
        raise HarnessError(f"{path}: {value} bounds nothing; a rejection is at least one diagnostic")
    return value


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise HarnessError(f"{path}: unreadable ({exc})") from exc


def _stderr_lines(path: Path) -> tuple[str, ...]:
    text = _read_bytes(path).decode("utf-8", "replace")
    return tuple(ln.strip() for ln in text.splitlines() if ln.strip())


def _make_test(
    tid: str,
    kind: str,
    suite: str,
    source: Path,
    entry: Path,
    expected: Path,
    exit_path: Path | None,
    stderr_path: Path | None,
    count_path: Path | None,
    stage_path: Path | None,
    stdin_path: Path | None,
    is_dir: bool,
) -> Test:
    return Test(
        tid=tid,
        kind=kind,
        suite=suite,
        source=source,
        entry=entry,
        expected_path=expected,
        expected=_read_bytes(expected),
        exit_code=_read_exit(exit_path) if exit_path else 0,
        exit_path=exit_path,
        stderr_lines=_stderr_lines(stderr_path) if stderr_path else (),
        stderr_path=stderr_path,
        count_max=_read_count(count_path) if count_path else None,
        count_path=count_path,
        stage_at=_read_stage(stage_path) if stage_path else None,
        stage_path=stage_path,
        stdin_bytes=_read_bytes(stdin_path) if stdin_path else None,
        stdin_path=stdin_path,
        is_dir=is_dir,
    )


def _suite_of(base: Path, path: Path) -> str:
    rel = path.relative_to(base)
    return rel.parts[0] if len(rel.parts) > 1 else rel.stem


def collect(tests_dir: Path, into: Collection, kind: str) -> None:
    base = tests_dir / kind
    if not base.is_dir():
        into.problems.append(f"{base}: missing suite root")
        return

    def walk(d: Path) -> None:
        try:
            children = sorted(d.iterdir(), key=lambda p: p.name)
        except OSError as exc:
            into.problems.append(f"{d}: unreadable ({exc})")
            return
        for child in children:
            if child.is_dir():
                entry = _dir_entry(child)
                expected = _first_existing(child, DIR_EXPECTED_NAMES, child.name)
                if entry and expected:
                    tid = f"{kind}/{child.relative_to(base).as_posix()}"
                    into.tests.append(
                        _make_test(
                            tid,
                            kind,
                            _suite_of(base, child),
                            child,
                            entry,
                            expected,
                            _first_existing(child, DIR_EXIT_NAMES, child.name),
                            _first_existing(child, DIR_STDERR_NAMES, child.name),
                            _first_existing(child, DIR_COUNT_NAMES, child.name),
                            _first_existing(child, DIR_STAGE_NAMES, child.name),
                            _first_existing(child, DIR_STDIN_NAMES, child.name),
                            is_dir=True,
                        )
                    )
                    continue
                if entry and not expected:
                    # An entry point with nothing to compare against: it can
                    # never go red, so it is never silently skipped.
                    into.uncollected.append(
                        f"{entry.relative_to(tests_dir).as_posix()} "
                        f"(directory test with no .expected at its root)"
                    )
                    continue
                walk(child)
            elif child.suffix == ".zen":
                expected = child.with_suffix(".expected")
                if expected.is_file():
                    rel = child.relative_to(base).with_suffix("").as_posix()
                    exit_path = child.with_suffix(".exit")
                    stderr_path = child.with_suffix(".stderr")
                    count_path = child.with_suffix(".count")
                    stage_path = child.with_suffix(".stage")
                    stdin_path = child.with_suffix(".stdin")
                    into.tests.append(
                        _make_test(
                            f"{kind}/{rel}",
                            kind,
                            _suite_of(base, child),
                            child,
                            child,
                            expected,
                            exit_path if exit_path.is_file() else None,
                            stderr_path if stderr_path.is_file() else None,
                            count_path if count_path.is_file() else None,
                            stage_path if stage_path.is_file() else None,
                            stdin_path if stdin_path.is_file() else None,
                            is_dir=False,
                        )
                    )
                else:
                    into.uncollected.append(
                        f"{child.relative_to(tests_dir).as_posix()} (no sibling .expected)"
                    )

    walk(base)


def discover(tests_dir: Path) -> Collection:
    found = Collection()
    collect(tests_dir, found, CORPUS)
    collect(tests_dir, found, MUST_FAIL)
    found.tests.sort(key=lambda t: t.tid)
    found.uncollected.sort()
    return found


def select(tests: Iterable[Test], patterns: Sequence[str]) -> list[Test]:
    tests = list(tests)
    if not patterns:
        return tests
    chosen: list[Test] = []
    for test in tests:
        for pattern in patterns:
            name = test.tid.rsplit("/", 1)[-1]
            glob = any(ch in pattern for ch in "*?[")
            if (
                fnmatch.fnmatchcase(test.tid, pattern)
                or fnmatch.fnmatchcase(name, pattern)
                or (not glob and pattern in test.tid)
            ):
                chosen.append(test)
                break
    return chosen


# ----------------------------------------------------------------- toolchain


@dataclass
class Toolchain:
    """How to turn Zen source into C. Both back ends honour the CLI contract in
    bootstrap/CONTRACT.md and tests/determinism/README.md: --emit-c -o <path>."""

    name: str
    emit_argv: list[str]  # command prefix; source and -o are appended
    style: str  # "bootstrap" (source first) | "zen" (source last)

    src_root: Path | None = None  # the tree every test is compiled against

    def command(self, source: Path, out_c: Path, root: Path,
                entry: str | None = None) -> list[str]:
        # A test is a program, and a program stands on std: `Res`, `Ok`, `Env`
        # and `println` are prelude names. Compiling a corpus file alone would
        # fail on every one of them and say nothing about the test.
        #
        # `--root` is not optional. The compilation root defaults to the
        # inputs' common ancestor, so a test under /tmp plus a std under
        # /home/... makes the root `/` and the compiler walks the filesystem.
        if self.style == "bootstrap":
            return [*self.emit_argv, str(source), "--root", str(root),
                    "--emit-c", "-o", str(out_c)]
        # The two CLIs disagree about how a build is named, and both spellings
        # are deliberate.
        #
        # The self-hosted CLI takes the root POSITIONALLY -- `zen build <root>
        # --emit-c -o <file>` -- and knows no `--root`, because a build is a
        # root. Passing the bootstrapper's spelling made every differential run
        # fail with `unknown argument --root`, which reads as 33 compiler bugs
        # and is one harness bug.
        #
        # It takes no source argument either; where to START inside the root is
        # `--entry`, and that is the other half of the same disagreement. The
        # bootstrapper is handed the entry as a positional and the root as a
        # flag; the self-hosted compiler is handed the root as a positional and
        # the entry as a flag. Without `--entry` the driver probes `main.zen`,
        # the root's own basename, and `zen.zen` -- which finds every directory
        # test and NO single-file one, because `stage` copies `foo.zen` in
        # under its own name. It cannot be renamed to `main.zen`: every
        # must-fail position assertion names the file it was written in, so
        # renaming reddens hundreds of expectations to paper over a missing
        # flag. That gap scored the whole self-hosted corpus 38/393.
        argv = [*self.emit_argv, "build", str(root)]
        if entry:
            argv += ["--entry", entry]
        return [*argv, "--emit-c", "-o", str(out_c)]


def make_toolchain(args: argparse.Namespace) -> Toolchain:
    if args.toolchain == "bootstrap":
        script = Path(args.bootstrap)
        if not script.is_absolute():
            script = REPO_ROOT / script
        if not script.is_file():
            raise HarnessError(
                f"no bootstrapper at {script}. It is written at stage 0 "
                f"(PLAN.md §0); pass --bootstrap PATH or --toolchain zen."
            )
        # `-m`, never the script path: bootstrap/ast.py shadows the stdlib `ast`
        # that dataclasses imports, and the script form puts bootstrap/ on
        # sys.path[0], so the interpreter dies before the first line of ours.
        return Toolchain(
            "bootstrap",
            [args.python, "-m", "bootstrap.bootstrap"],
            "bootstrap",
            src_root=REPO_ROOT / "src",
        )

    binary = Path(args.zen)
    if not binary.is_absolute():
        binary = REPO_ROOT / binary
    if not (binary.is_file() and os.access(binary, os.X_OK)):
        raise HarnessError(f"no executable zen compiler at {binary}. Build one (`make build`).")
    return Toolchain("zen", [str(binary)], "zen", src_root=REPO_ROOT / "src")


# ------------------------------------------------------------------- running


@dataclass
class Run:
    argv: list[str]
    code: int  # 128+signal when killed by a signal, as a shell reports it
    stdout: bytes
    stderr: bytes
    timed_out: bool
    signalled: bool


def run_process(
    argv: list[str],
    timeout: float,
    cwd: Path | None = None,
    feed: bytes | None = None,
) -> Run:
    """`feed` is the bytes on the process's stdin; None is /dev/null.

    None and b"" are different: an empty pipe is a stream that closes at once,
    which is what a program reading stdin sees at end of input, while
    /dev/null is what everything else gets. A test asserting end-of-input
    behaviour needs the first, so the default cannot be b"".
    """
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            **({"input": feed} if feed is not None else {"stdin": subprocess.DEVNULL}),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise HarnessError(f"cannot execute {argv[0]!r}: {exc}") from exc
    except PermissionError as exc:
        raise HarnessError(f"cannot execute {argv[0]!r}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        return Run(argv, 124, exc.stdout or b"", exc.stderr or b"", True, False)
    code = proc.returncode
    signalled = code < 0
    if signalled:
        code = 128 + (-code)
    return Run(argv, code, proc.stdout, proc.stderr, False, signalled)


def diagnostics(run: Run) -> str:
    return (run.stderr + run.stdout).decode("utf-8", "replace")


def positions_in(text: str) -> set[tuple[str | None, int, int]]:
    found: set[tuple[str | None, int, int]] = set()
    for path, line, col in POS_WITH_PATH.findall(text):
        found.add((path, int(line), int(col)))
    for line, col in POS_BARE.findall(text):
        found.add((None, int(line), int(col)))
    return found


def position_matches(assertion: str, entry_name: str, seen: set) -> bool:
    """`path:line:col`, or `line:col` meaning the test's entry file.

    A diagnostic path is matched by suffix, because the compilation root of a
    test is the test's own directory (tests/corpus/codegen/README.md) while a
    runner may hand over a longer path.
    """
    parts = assertion.split(":")
    if len(parts) == 2:
        want_path, line_s, col_s = None, parts[0], parts[1]
    elif len(parts) == 3:
        want_path, line_s, col_s = parts[0], parts[1], parts[2]
    else:
        return False
    try:
        line, col = int(line_s), int(col_s)
    except ValueError:
        return False

    for got_path, got_line, got_col in seen:
        if (got_line, got_col) != (line, col):
            continue
        if want_path is None:
            # bare line:col -- the position is in the test's entry file
            if got_path is None or Path(got_path).name == entry_name:
                return True
            continue
        if got_path is None:
            continue
        want = [p for p in Path(want_path).parts if p not in (".", "")]
        got = [p for p in Path(got_path).parts if p not in (".", "")]
        if got[-len(want):] == want or want[-len(got):] == got:
            return True
    return False


def byte_diff(expected: bytes, actual: bytes) -> str:
    import difflib

    if expected == actual:
        return ""
    offset = next(
        (i for i in range(min(len(expected), len(actual))) if expected[i] != actual[i]),
        min(len(expected), len(actual)),
    )
    head = [
        f"stdout differs at byte {offset} "
        f"(expected {len(expected)} bytes, got {len(actual)} bytes)"
    ]
    exp_lines = expected.decode("utf-8", "replace").splitlines(keepends=True)
    act_lines = actual.decode("utf-8", "replace").splitlines(keepends=True)
    diff = difflib.unified_diff(
        [repr(ln)[1:-1] + "\n" for ln in exp_lines],
        [repr(ln)[1:-1] + "\n" for ln in act_lines],
        fromfile="expected",
        tofile="actual",
        n=2,
        lineterm="\n",
    )
    head.extend(ln.rstrip("\n") for ln in list(diff)[:60])
    return "\n".join(head)


def display_path(path: Path) -> str:
    """Repo-relative when possible, so failure output is copy-pasteable."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def clip(text: str, lines: int = 30) -> str:
    parts = text.splitlines()
    if len(parts) <= lines:
        return "\n".join(parts)
    return "\n".join(parts[:lines] + [f"... {len(parts) - lines} more line(s)"])


def stage(test: Test, tool: Toolchain, work: Path) -> Path:
    """Build a self-contained source tree for one test, and return its root.

    A test is a program, and a program stands on std — `Res`, `Ok`, `Env` and
    `println` are prelude names. So the prelude is staged beside the test and
    the pair is compiled as one tree.

    Staging rather than passing two paths is not a convenience: the compilation
    root defaults to the inputs' common ancestor, so a test under /tmp plus a
    std under /home/... roots at `/` and the compiler walks the filesystem.
    """
    root = work / "src"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    if test.source.is_dir():
        shutil.copytree(test.source, root, dirs_exist_ok=True)
    else:
        shutil.copy2(test.source, root / test.source.name)

    # `std` always -- it is the prelude, and every program stands on it.
    # Any OTHER top-level module under src/ (`lex`, `ast`, `parse`, ..) only
    # if this test's own sources name it.
    #
    # Staging the whole of src/ was the first attempt, and it is wrong for a
    # reason worth writing down: the compiler compiles the whole staged tree,
    # so ONE half-written module reddens every test in the suite -- not by
    # failing them, but by adding its diagnostics to their counts, which is
    # how a `.count` assertion starts failing because of a file it has never
    # heard of. That couples every test to every module's health and makes
    # working on two modules at once impossible.
    #
    # The name test is deliberately crude and deliberately UNDER-inclusive:
    # a module that is wanted but not matched gives a plain "module not
    # found", which names the problem, while an unwanted module that IS
    # staged gives diagnostics from a file the author never mentioned.
    if tool.src_root and tool.src_root.is_dir():
        # A test OWNS its own namespace. `corpus/modules/folder_root` declares
        # its own `gen/`, and staging src/gen on top of it merged the two
        # trees: the test's three-line gen.zen got a diagnostic reported at
        # line 51, which is a line only src/gen/gen.zen has. Whatever the test
        # defines wins, and the src module of that name is simply not staged.
        mine = {e.name for e in root.iterdir()}
        available = {e.name: e for e in tool.src_root.iterdir()
                     if e.name not in mine}
        wanted = ({"std"} | _modules_named_in(root)) & set(available)
        # TRANSITIVE. `parse` imports `lex`, so a test naming only `parse`
        # needs `lex` staged too or it gets "module lex.lex not found". The
        # first version scanned only the test's own sources and stopped there;
        # that was fine while every stage-1 module stood alone and stopped
        # being fine the moment two of them were wired together.
        frontier = sorted(wanted)
        while frontier:
            name = frontier.pop()
            entry = available[name]
            if not entry.is_dir():
                continue
            for dep in sorted(_modules_named_in(entry) & set(available)):
                if dep not in wanted:
                    wanted.add(dep)
                    frontier.append(dep)
        for name in sorted(wanted):
            entry = available[name]
            if entry.is_dir():
                shutil.copytree(entry, root / entry.name, dirs_exist_ok=True)
            else:
                shutil.copy2(entry, root / entry.name)
    return root


def staged_entry(test: Test) -> str:
    """Where the staged tree starts, relative to its root.

    `stage` copies a single-file test in under its OWN name and a directory
    test in as itself, so the entry's path inside the staged root is the entry
    relative to whichever of those `stage` copied. Nothing can guess that name:
    a compilation root is a directory and `std.env.Fs` has no listing.

    Passed for both shapes rather than only the one that needs it. The probe
    would find `main.zen` for most directory tests, but not one whose entry is
    `<name>.zen` -- the folder-root spelling, which the probe applies to the
    STAGED root's basename (`src`) and not to the test's -- and a harness that
    is right about the entry for one shape and lucky about it for the other is
    one directory test away from a mystery.
    """
    base = test.source if test.source.is_dir() else test.source.parent
    return test.entry.relative_to(base).as_posix()


def _modules_named_in(root: Path) -> set[str]:
    """Every bare word in the staged test's own sources.

    An import names its module (`lex.lex`, or `lex` for a folder root), so a
    module this test could possibly reach appears here as a word. Over-
    matching costs a directory copy; under-matching costs a clear diagnostic.
    """
    names: set[str] = set()
    for path in root.rglob("*.zen"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            # comments name modules constantly ("see src/parse"), and matching
            # those stages a module the test never imports -- which is the
            # exact coupling this function exists to remove
            code = line.split("//", 1)[0]
            names |= set(IMPORT_RHS.findall(code))
    return names


def run_corpus(test: Test, tool: Toolchain, work: Path, args: argparse.Namespace) -> Result:
    reasons: list[str] = []
    detail: list[str] = []

    out_c = work / "out.c"
    root = stage(test, tool, work)
    emit = run_process(tool.command(root, out_c, root, staged_entry(test)), args.timeout)
    if emit.timed_out:
        return Result(test, False, [f"the compiler timed out after {args.timeout}s"])
    if emit.code != 0 or not out_c.is_file():
        return Result(
            test,
            False,
            [f"the compiler rejected a corpus program (exit {emit.code})"],
            clip(diagnostics(emit)),
        )

    binary = work / "prog"
    cc = run_process([args.cc, *shlex.split(args.cc_flags), str(out_c), "-o", str(binary)],
                     args.timeout)
    if cc.timed_out or cc.code != 0:
        # A rejected translation unit is a codegen bug, not harness noise.
        note = clip(diagnostics(cc))
        if args.keep:
            note += f"\ngenerated C kept at: {out_c}"
        return Result(test, False, [f"the C compiler rejected the generated C (exit {cc.code})"], note)

    # Run in the work directory: a program that writes a file must not write it
    # into the test tree.
    prog = run_process([str(binary)], args.run_timeout, cwd=work, feed=test.stdin_bytes)
    if prog.timed_out:
        return Result(test, False, [f"the program timed out after {args.run_timeout}s"])

    if prog.stdout != test.expected:
        reasons.append("stdout does not match .expected")
        detail.append(byte_diff(test.expected, prog.stdout))

    if prog.code != test.exit_code:
        where = test.exit_path.name if test.exit_path else "no .exit file, so 0"
        note = " (killed by a signal)" if prog.signalled else ""
        reasons.append(f"exit code {prog.code}{note}, expected {test.exit_code} [{where}]")

    for want in test.stderr_lines:
        if want not in prog.stderr.decode("utf-8", "replace"):
            reasons.append(f".stderr substring not found: {want!r}")
    if test.stderr_lines and reasons:
        detail.append("actual stderr:\n" + clip(prog.stderr.decode("utf-8", "replace")))

    return Result(test, not reasons, reasons, "\n".join(d for d in detail if d))


def run_must_fail(test: Test, tool: Toolchain, work: Path, args: argparse.Namespace) -> Result:
    out_c = work / "out.c"
    root = stage(test, tool, work)
    emit = run_process(tool.command(root, out_c, root, staged_entry(test)), args.timeout)
    text = diagnostics(emit)

    if emit.timed_out:
        return Result(
            test, False,
            [f"the compiler hung for {args.timeout}s; a rejection must terminate"],
            clip(text),
        )
    if emit.signalled:
        return Result(
            test, False,
            [f"the compiler died on a signal (exit {emit.code}); a crash is not a rejection"],
            clip(text),
        )
    if emit.code == 0:
        return Result(
            test, False,
            ["the program compiled; it must be rejected"],
            clip(text),
        )
    for marker in CRASH_MARKERS:
        if marker in text:
            return Result(
                test, False,
                [f"the compiler crashed ({marker}); a crash is not a diagnostic"],
                clip(text),
            )

    reasons: list[str] = []
    message = test.message
    if not message:
        return Result(test, False, [f"{test.expected_path} has no message line; it asserts nothing"])
    if message not in text:
        reasons.append(f"message substring not found: {message!r}")

    seen = positions_in(text)
    entry_name = test.entry.name
    for want in test.positions:
        if not position_matches(want, entry_name, seen):
            reasons.append(f"position not reported: {want}")
    if not test.positions:
        reasons.append(
            f"{test.expected_path.name} asserts no position; "
            "TESTING.md requires the diagnostic's position, exact"
        )

    if test.count_max is not None:
        total = DIAG_TOTAL.search(text)
        if total is None:
            # The bound cannot be checked, so the test does not pass. A count
            # gate that silently gives up when it cannot count is the exact
            # thing this assertion exists to prevent.
            reasons.append(
                f"{test.count_path.name} bounds the diagnostic count at "
                f"{test.count_max}, but the compiler printed no "
                f"`N diagnostic(s)` total to compare against"
            )
        elif int(total.group(1)) > test.count_max:
            reasons.append(
                f"{total.group(1)} diagnostics, at most {test.count_max} allowed "
                f"[{test.count_path.name}]: one mistake must not cascade"
            )

    return Result(test, not reasons, reasons, clip(text) if reasons else "")


def stage_verdict(result: Result, current: int) -> tuple[Result, bool]:
    """Apply a test's `.stage` to the result it already earned.

    A deferred test is RUN, never skipped. Skipping would make the sidecar a
    second gate that cannot fail: the day the feature lands, nothing would
    notice, and the file would sit there asserting a stage the project left
    behind. So the two outcomes are both useful --

        it failed  -> deferred, not a failure. The reason is on record.
        it PASSED  -> a failure, and the fix is to delete the .stage file.
    """
    stage_at = result.test.stage_at
    if stage_at is None or stage_at <= current:
        return result, False
    if result.ok:
        name = result.test.stage_path.name
        return Result(
            result.test, False,
            [f"deferred to stage {stage_at}, but it passes at stage {current}: "
             f"delete {name} -- the stage arrived"],
        ), False
    return result, True


def run_one(test: Test, tool: Toolchain, workroot: Path, args: argparse.Namespace) -> Result:
    work = workroot / re.sub(r"[^A-Za-z0-9_.-]", "_", test.tid)
    work.mkdir(parents=True, exist_ok=True)
    if test.kind == CORPUS:
        return run_corpus(test, tool, work, args)
    return run_must_fail(test, tool, work, args)


# ---------------------------------------------------------------------- main


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="tests/run.py",
        description="run the tests/corpus and tests/must-fail gates",
    )
    p.add_argument("--toolchain", choices=("bootstrap", "zen"), default="bootstrap",
                   help="which implementation compiles the tests (default: bootstrap)")
    p.add_argument("--bootstrap", default="bootstrap/bootstrap.py",
                   help="path to the Python bootstrapper")
    p.add_argument("--python", default=sys.executable, help="interpreter for the bootstrapper")
    p.add_argument("--zen", default="zen", help="path to the zen binary (--toolchain zen)")
    p.add_argument("--cc", default=os.environ.get("CC", "cc"), help="C compiler")
    p.add_argument("--cc-flags", default=os.environ.get("CFLAGS", "-std=c11 -O0 -g"),
                   help="flags passed to the C compiler")
    p.add_argument("--tests", default=str(TESTS_DIR), help="the tests/ directory")
    p.add_argument("--filter", action="append", default=[], metavar="GLOB",
                   help="select tests whose id matches (repeatable)")
    p.add_argument("--list", action="store_true", help="print selected test ids and exit")
    p.add_argument("--jobs", "-j", type=int, default=os.cpu_count() or 1)
    p.add_argument("--stage", type=int, default=_current_stage(),
                   help="PLAN.md stage to grade against; a test whose .stage is "
                        "ahead of it is deferred rather than failed")
    p.add_argument("--timeout", type=float, default=120.0, help="seconds for one compile")
    p.add_argument("--run-timeout", type=float, default=20.0, help="seconds for one program")
    p.add_argument("--keep", action="store_true", help="keep the work directory")
    p.add_argument("--verbose", "-v", action="store_true", help="print a line per passing test")
    p.add_argument("--allow-uncollected", action="store_true",
                   help="do not fail when a .zen file belongs to no test")
    return p.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    tests_dir = Path(args.tests).resolve()

    try:
        found = discover(tests_dir)
    except HarnessError as exc:
        print(f"run.py: {exc}", file=sys.stderr)
        return 2

    for problem in found.problems:
        print(f"run.py: {problem}", file=sys.stderr)
    if found.problems:
        return 2

    selected = select(found.tests, args.filter)

    if args.list:
        for test in selected:
            print(test.tid)
        for name in found.uncollected:
            print(f"run.py: uncollected: {name}", file=sys.stderr)
        if not selected:
            print("run.py: no test matched the selection", file=sys.stderr)
            return 2
        return 0

    if not found.tests:
        print(f"run.py: no tests found under {tests_dir}", file=sys.stderr)
        return 2
    if not selected:
        print(f"run.py: no test matched {args.filter}", file=sys.stderr)
        for name in found.uncollected:
            if any(pat.strip("*?[]") in name for pat in args.filter):
                print(f"run.py: but this file is uncollected: {name}", file=sys.stderr)
        return 2

    try:
        tool = make_toolchain(args)
        if any(t.kind == CORPUS for t in selected) and shutil.which(args.cc) is None:
            raise HarnessError(f"no C compiler on PATH: {args.cc!r} (pass --cc)")
    except HarnessError as exc:
        print(f"run.py: {exc}", file=sys.stderr)
        return 2

    workroot = Path(tempfile.mkdtemp(prefix="zen-tests."))
    results: list[Result] = []
    deferred: list[Result] = []
    harness_errors: list[str] = []

    def task(test: Test) -> Result:
        try:
            return run_one(test, tool, workroot, args)
        except HarnessError as exc:
            harness_errors.append(f"{test.tid}: {exc}")
            return Result(test, False, [f"harness error: {exc}"])
        except Exception as exc:  # a runner that tracebacks reports nothing
            harness_errors.append(f"{test.tid}: {type(exc).__name__}: {exc}")
            return Result(test, False, [f"harness error: {type(exc).__name__}: {exc}"])

    try:
        print(
            f"run.py: {len(selected)} test(s) via {tool.name} "
            f"[{shlex.join(tool.emit_argv)}], {args.jobs} job(s)"
        )
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            for raw in pool.map(task, selected):
                result, is_deferred = stage_verdict(raw, args.stage)
                results.append(result)
                if is_deferred:
                    deferred.append(result)
                    if args.verbose:
                        print(f"defer {result.test.tid} "
                              f"(stage {result.test.stage_at})")
                elif result.ok:
                    if args.verbose:
                        print(f"ok   {result.test.tid}")
                else:
                    print(f"FAIL {result.test.tid}: {result.reasons[0]}")
    finally:
        if args.keep:
            print(f"run.py: work directory kept at {workroot}")
        else:
            shutil.rmtree(workroot, ignore_errors=True)

    failures = [r for r in results if not r.ok and r not in deferred]
    if failures:
        print("\n" + "=" * 72)
        print(f"{len(failures)} failure(s)")
        print("=" * 72)
        for result in failures:
            print(f"\n--- {result.test.tid}  ({display_path(result.test.source)})")
            for reason in result.reasons:
                print(f"    {reason}")
            if result.detail:
                for line in result.detail.splitlines():
                    print(f"    | {line}")

    if found.uncollected:
        print("\nuncollected (a .zen file that belongs to no test, so it never runs):")
        for name in found.uncollected:
            print(f"    {name}")

    if deferred:
        print(f"\ndeferred -- ahead of stage {args.stage}, so red is expected "
              "and is not counted:")
        for result in deferred:
            print(f"    stage {result.test.stage_at}  {result.test.tid}")

    passed = len(results) - len(failures) - len(deferred)
    print(f"\nrun.py: {passed} passed, {len(failures)} failed, "
          f"{len(deferred)} deferred, "
          f"{len(found.uncollected)} uncollected, {len(found.tests) - len(selected)} deselected")

    if harness_errors:
        for line in harness_errors:
            print(f"run.py: harness error: {line}", file=sys.stderr)
        return 2
    if failures:
        return 1
    if found.uncollected and not args.allow_uncollected:
        print("run.py: uncollected files are a failure; a test that cannot run "
              "cannot go red (--allow-uncollected to override)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
