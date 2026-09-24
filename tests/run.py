#!/usr/bin/env python3
"""tests/run.py -- the corpus, must-fail and example gate.

Compiles every program under tests/corpus/, tests/must-fail/ and example/ and
checks it against its recorded expectations. The format is specified in
docs/TESTING.md ("The test file format"); this runner reads only that.

example/ is the third suite and the newest: it is the tree's worked example,
it lives at the repo root rather than under tests/, and until 2026-08-25 no
gate ever handed it to the compiler. See EXAMPLE below.

    0   every selected test passed
    1   a test failed -- the compiler is wrong, or the test is
    2   the harness could not run: no compiler, no C compiler, an unreadable
        test, or a selection that matched nothing

2 is NOT a pass. A gate that succeeds when it cannot run reads as coverage and
guards nothing (PLAN.md: "before trusting a new gate, break the thing it
guards on purpose and watch it go red").

Usage:

    tests/run.py                          # everything, via ./zen
    tests/run.py --list                   # names only, no compiler needed
    tests/run.py --filter 'corpus/lex/*'  # a glob over the test id
    tests/run.py --filter 'example/*'     # just the worked example
    tests/run.py --jobs 8
    tests/run.py --filter 'corpus/std/*' --shard 1/2 --timings
    tests/run.py --timings-json build/test-timings.json
    tests/run.py --zen build/zen          # some other build of the compiler
"""

from __future__ import annotations

import argparse
import fnmatch
import fcntl
import hashlib
import json
import os
import platform
import re
import resource
import shlex
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent

CORPUS = "corpus"
MUST_FAIL = "must-fail"

# THE THIRD SUITE, AND IT DOES NOT LIVE UNDER tests/. `example/` is the
# tree's worked example -- DESIGN.md's own program, the one a newcomer reads
# -- and until 2026-08-25 NOTHING COMPILED IT. Every gate that touched it was
# lexical: `parse`, `grammar-test`, `lextile` and `fmt` read the bytes and
# never handed them to the compiler, and there was not one `.expected` file
# anywhere in the directory.
#
# That gap has already cost something real. Compiling example/ is how the
# lambda-body hole was found: the same two statements produce two diagnostics
# at statement level and ZERO inside a `.loop` or `.then` body, which means
# `cc` was the type checker for lambda bodies. Nothing in this repository
# compiled the file that showed it.
#
# It is collected exactly like a corpus test -- same directory shape, same
# `.expected`, `.exit`, `.stage` sidecars, same compile/link/run/compare --
# because a second mechanism for "run a program and check its output" is a
# second mechanism to go stale. The only difference is where the root is.
#
# WHAT `example/src/.expected` IS, EXACTLY, because reading it wrong would
# be worse than not having it: it is a SPECIFICATION written in advance, not
# a recorded measurement. example/src is stage 5 -- it names `std.actor` and
# `pkg.*`, neither of which exists -- so it does not compile today and its
# `.stage` defers it. Everything in that file down to `sent all three` follows
# from main.zen line by line; the lines BELOW it are the actor turns, and
# main.zen's own comments say only that the prints "happen later, on foo's
# turn, in send order", which does not pin their interleaving with main's.
# Whoever lands stage 5 will see the difference as a diff and is the one who
# gets to rule on it -- and cannot delete the `.stage` without doing so,
# because a deferred test that passes is a failure here (`stage_verdict`).
#
# AND TWO OF ITS LINES ARE BLOCKED BY SOMETHING THAT IS NOT STAGE 5.
# `circle: 1` and `rect: 2 3` come from Shape's Display impl, which formats an
# f64 -- and `{}` on an f64 is refused by gen_c ("codegen does not lower this
# yet: `formatting a value of this type`", gen_c_sink.zen:895). So example/src
# owes a codegen fix as well as a runtime, and example/src/main_test.zen's
# `circle_prints_its_radius` cannot run for the same reason. ISSUES.md carries
# it, along with the other thing running these turned up: main_test.zen is not
# imported from main.zen, so nothing type-checks it either.
EXAMPLE = "example"

# A .zen under example/ that is NOT a program, with the reason. Ratchets both
# ways: a name here that no longer exists is an error, so the exemption cannot
# outlive the file it excuses.
#
# `build.zen` declares `build = (b :: Builder) Res<(), BuildError>` and has no
# `main`. It is a build FILE -- there is nothing to link and nothing to run,
# so there is no stdout for an `.expected` to hold. `make parse` and `make
# fmt` are what stand behind it.
EXAMPLE_NOT_PROGRAMS = {"build.zen": "a build file: it declares `build`, not `main`"}

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
DIR_ARGS_NAMES = (".args", "{name}.args", "main.args")
DIR_ENV_NAMES = (".env", "{name}.env", "main.env")

# What the compiler prints once it is done: `zen: 3 diagnostic(s)`.
# Every must-fail test asserts against it -- the bound defaults to the number
# of positions `.expected` asserts, and `.count` overrides it -- and it is
# the one fact that cannot fall back to reading the diagnostics themselves:
# two diagnostics on one position are two, and the position list cannot tell.
DIAG_TOTAL = re.compile(r"(\d+) diagnostic\(s\)")

# The module named by an import's right-hand side: `Res* = std.core.result`
# and `Kind, Pos = leaf` both name their first component. Module paths are
# lowercase by convention, which is what keeps `= Package(..)` out.
IMPORT_RHS = re.compile(r"=\s*([a-z][A-Za-z0-9_]*)\s*(?:\.|$)")

# The compiler's own frontend lives INSIDE std (`std.lex`, `std.parse`,
# `std.ast`), so IMPORT_RHS sees only `std`; the second segment takes its own
# pattern. Used by `stage` to prune the sublayer a test never names.
SUBLAYER = {"lex", "parse", "ast"}
SUBLAYER_RHS = re.compile(r"=\s*std\.(lex|parse|ast)(?:\.|\s|$)")

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

# Link only native floors named by generated C; keep libraries after sources.
NATIVE_FLOORS: tuple[tuple[bytes, tuple[Path, ...], tuple[str, ...]], ...] = (
    (b"SSL_", (), ("-lssl", "-lcrypto")),
    (b"zg_proc_", (REPO_ROOT / "src/std/proc/proc.c",), ()),
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
    # `.args` is the PROGRAM's argv after argv[0], one word per line, and
    # `.env` is KEY=VALUE lines added to its environment: the two inputs
    # `env.args<T>()` reads, and the only way a corpus test can hand a
    # program a command line. Absent means no words and nothing added.
    args_words: tuple[str, ...] = ()
    env_pairs: tuple[tuple[str, str], ...] = ()
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
    seconds: float = 0.0
    cached: bool = False
    cacheable: bool = True
    artifact_cached: bool = False


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
    """`.count` states the diagnostic count where it differs from the number
    of positions `.expected` asserts, which bounds every must-fail test by
    default. Zero would assert the program is accepted, which is what a
    corpus test is for."""
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
    args_path: Path | None = None,
    env_path: Path | None = None,
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
        args_words=_read_lines(args_path) if args_path else (),
        env_pairs=_read_env(env_path) if env_path else (),
        is_dir=is_dir,
    )


def _read_lines(path: Path) -> tuple[str, ...]:
    """One argv word per line; the trailing newline does not add a word."""
    text = path.read_text(encoding="utf-8")
    if "\0" in text:
        raise HarnessError(f"{path}: `.args` cannot contain a NUL byte")
    if text.endswith("\n"):
        text = text[:-1]
    return tuple(text.split("\n")) if text else ()


def _read_env(path: Path) -> tuple[tuple[str, str], ...]:
    pairs = []
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise HarnessError(f"{path}: `.env` lines are KEY=VALUE, got {line!r}")
        if not key:
            raise HarnessError(f"{path}: `.env` variable names cannot be empty")
        if "\0" in key or "\0" in value:
            raise HarnessError(f"{path}: `.env` cannot contain a NUL byte")
        if key in names:
            raise HarnessError(f"{path}: duplicate `.env` variable {key!r}")
        names.add(key)
        pairs.append((key, value))
    return tuple(pairs)


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
            # A SYMLINK IS NOT A TEST. `example/std` points at src/std, which
            # is the prelude every test already stands on -- descending it
            # would report all ~200 std files as uncollected and stage the
            # library twice. No suite has ever held a real symlinked test.
            if child.is_symlink():
                continue
            if kind == EXAMPLE and child.name in EXAMPLE_NOT_PROGRAMS:
                continue
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
                            args_path=_first_existing(child, DIR_ARGS_NAMES, child.name),
                            env_path=_first_existing(child, DIR_ENV_NAMES, child.name),
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
                    args_path = child.with_suffix(".args")
                    env_path = child.with_suffix(".env")
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
                            args_path=args_path if args_path.is_file() else None,
                            env_path=env_path if env_path.is_file() else None,
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
    # example/ hangs off the REPO root, not tests/, so it is passed the
    # repository rather than `tests_dir`. Everything downstream of collection
    # treats it as a corpus test.
    collect(REPO_ROOT, found, EXAMPLE)
    for name, reason in sorted(EXAMPLE_NOT_PROGRAMS.items()):
        if not (REPO_ROOT / EXAMPLE / name).is_file():
            found.problems.append(
                f"example/{name} is exempted in EXAMPLE_NOT_PROGRAMS"
                f" ({reason}) and does not exist. Delete the line -- an"
                " exemption that outlives its file is an exemption nobody"
                " re-read."
            )
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


def shard_arg(value: str) -> tuple[int, int]:
    """A shard is a one-based position in a positive number of workers."""
    try:
        index, count = map(int, value.split("/"))
        if 1 <= index <= count:
            return index, count
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("expected INDEX/COUNT with 1 <= INDEX <= COUNT")


def positive_int(value: str) -> int:
    try:
        number = int(value)
        if number > 0:
            return number
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("expected a positive integer")


def shard(tests: Sequence[Test], selection: tuple[int, int] | None) -> list[Test]:
    if selection is None:
        return list(tests)
    index, count = selection
    return sorted(tests, key=lambda test: test.tid)[index - 1::count]


# ----------------------------------------------------------------- toolchain


@dataclass
class Toolchain:
    """How to turn Zen source into C, per tests/determinism/README.md's CLI
    contract: --emit-c -o <path>."""

    name: str
    emit_argv: list[str]  # command prefix; the build arguments are appended

    src_root: Path | None = None  # the tree every test is compiled against
    modules: dict[str, Path] = field(default_factory=dict, init=False)
    imports: dict[str, frozenset[str]] = field(default_factory=dict, init=False)
    source_state: dict[Path, tuple[int, ...]] = field(default_factory=dict, init=False)
    c_compiler: CCompiler | None = None
    module_files: dict[str, dict[str, Path]] = field(default_factory=dict, init=False)
    sublayer_imports: dict[Path, frozenset[str]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        # One import manifest per invocation, prepared before worker threads.
        # Staged files remain private copies; only source-tree discovery is shared.
        if self.src_root and self.src_root.is_dir():
            self.source_state = self.current_source_state()
            self.modules = {entry.name: entry for entry in self.src_root.iterdir()}
            self.imports = {
                name: frozenset(_modules_named_in(entry))
                for name, entry in self.modules.items() if entry.is_dir()
            }
            self.module_files = {name: tree_files(entry) for name, entry in self.modules.items()}
            self.sublayer_imports = {path: frozenset(sublayers_named_in(path))
                                    for path, state in self.source_state.items()
                                    if path.suffix == ".zen" and stat.S_ISREG(state[-1])}
            self.check_source_state()

    def current_source_state(self) -> dict[Path, tuple[int, ...]]:
        if self.src_root is None:
            return {}
        try:
            paths = [self.src_root, *tree_files(self.src_root).values()]
            state = {}
            for path in paths:
                info = path.stat()
                state[path] = (info.st_dev, info.st_ino, info.st_size,
                               info.st_mtime_ns, info.st_ctime_ns, info.st_mode)
            return state
        except OSError as exc:
            raise HarnessError(f"cannot inspect compiler source tree: {exc}") from exc

    def check_source_state(self) -> None:
        if self.current_source_state() != self.source_state:
            raise HarnessError("compiler sources changed during this test run; "
                               "rerun after edits finish (the import manifest is per invocation)")

    def command(self, source: Path, out_c: Path, root: Path,
                entry: str | None = None) -> list[str]:
        # A test is a program, and a program stands on std: `Res`, `Ok`, `Env`
        # and `println` are prelude names. Compiling a corpus file alone would
        # fail on every one of them and say nothing about the test -- so what
        # is passed is the staged ROOT, positionally, because a build IS a root.
        #
        # `--entry` is where to START inside it, and it is not optional.
        # Without it the driver probes `main.zen`, the root's own basename and
        # `zen.zen` -- which finds every directory test and NO single-file one,
        # because `stage` copies `foo.zen` in under its own name. It cannot be
        # renamed to `main.zen`: every must-fail position assertion names the
        # file it was written in, so renaming reddens hundreds of expectations
        # to paper over a missing flag. That gap scored the corpus 38/393.
        # Select the staged library even when this binary has a sibling src/std
        # or the invoking shell supplies ZEN_STD for another development lane.
        argv = [*self.emit_argv, "build", str(root), "--std", str(root)]
        if entry:
            argv += ["--entry", entry]
        return [*argv, "--emit-c", "-o", str(out_c)]


def make_toolchain(args: argparse.Namespace) -> Toolchain:
    binary = Path(args.zen)
    if not binary.is_absolute():
        binary = REPO_ROOT / binary
    if not (binary.is_file() and os.access(binary, os.X_OK)):
        raise HarnessError(f"no executable zen compiler at {binary}. Build one (`make build`).")
    return Toolchain("zen", [str(binary)], src_root=REPO_ROOT / "src",
                     c_compiler=CCompiler(args.cc, shlex.split(args.cc_flags),
                                          args.cc_cache, args.cc_work_dir, args.timeout))


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
    env: dict[str, str] | None = None,
    pass_fds: tuple[int, ...] = (),
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
            env=env,
            pass_fds=pass_fds,
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


@dataclass
class CCompiler:
    command: str
    flags: list[str]
    cache: str
    work_dir: Path
    timeout: float

    def build(self, tid: str, source: Path, binary: Path, native: list[str]) -> Run:
        cacheable = bool(self.cache)
        if cacheable:
            generated = source.read_bytes()
            # Moving path-sensitive C would change its meaning. These uncommon
            # programs retain the original compile path and still run normally.
            cacheable = not (b"__FILE__" in generated or b"__BASE_FILE__" in generated
                             or re.search(rb'(?m)^\s*#\s*include\s*"', generated))
        if not cacheable:
            return run_process([self.command, *self.flags, str(source), *native,
                                "-o", str(binary)], self.timeout)

        # Stable C paths allow ccache hits with debug info, while keeping the
        # caller's working directory and relative compiler flags unchanged.
        directory = self.work_dir.resolve() / hashlib.sha256(tid.encode()).hexdigest()
        directory.mkdir(parents=True, exist_ok=True)
        object_file = binary.with_suffix(".o")
        with (directory / "compile.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            staged_c = directory / "out.c"
            staged_object = directory / "out.o"
            shutil.copyfile(source, staged_c)
            # A compiler that returns zero without producing output must never
            # reuse an object left by a previous invocation.
            staged_object.unlink(missing_ok=True)
            compiled = run_process([self.cache, self.command, *self.flags,
                                    "-c", str(staged_c), "-o", str(staged_object)],
                                   self.timeout, pass_fds=(lock.fileno(),))
            if compiled.timed_out or compiled.code != 0:
                return compiled
            if not staged_object.is_file():
                raise HarnessError("C compiler succeeded without producing an object")
            shutil.copyfile(staged_object, object_file)
        # Link and execute on every invocation; only C compilation is cached.
        linked = run_process([self.command, *self.flags, str(object_file), *native,
                              "-o", str(binary)], self.timeout)
        linked.stdout = compiled.stdout + linked.stdout
        linked.stderr = compiled.stderr + linked.stderr
        return linked


class ResultCache:
    """Reuse passed verdicts only with the same observable compiler inputs.

    Environment values enter only a digest. Native search trees use inode,
    size, nanosecond change-time and modification-time snapshots, so replacing
    a header/library or restoring its mtime still invalidates the cache.
    Unsupported native configurations run fresh rather than guessing their
    dependency closure. Verification can always disable this cache entirely.
    """
    VERSION = 1
    REWRITTEN = {"corpus/env/clock_reads_are_two_authorities",
                 "corpus/net/tcp_connect", "corpus/net/tls_connect"}

    def __init__(self, directory: Path, tool: Toolchain, args: argparse.Namespace):
        self.directory, self.tool, self.args = directory, tool, args
        self.hashes: dict[tuple, str] = {}
        self.lock = threading.Lock()
        self.pending: list[tuple[str, str]] = []
        self.checked: list[tuple[Test, str]] = []
        self.keys: dict[str, str] = {}
        self.artifacts: list[tuple[str, Path]] = []
        self.identity = self.context()
        # Source rows are shared across tests, and the complete source snapshot
        # is validated again before publishing or accepting a warm run.
        self.source_rows = {
            path: (stat.S_IMODE(state[-1]), "directory" if stat.S_ISDIR(state[-1])
                   else self.file_digest(path))
            for path, state in tool.source_state.items()
        } if self.identity is not None else {}
        tool.check_source_state()

    @staticmethod
    def digest(value) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()

    @staticmethod
    def state(path: Path) -> tuple:
        info = path.stat()
        return (str(path.resolve()), info.st_dev, info.st_ino, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns, info.st_mode)

    def file_digest(self, path: Path) -> str:
        before = self.state(path)
        with self.lock:
            known = self.hashes.get(before)
        if known is not None:
            return known
        value = hashlib.sha256(path.read_bytes()).hexdigest()
        if self.state(path) != before:
            raise HarnessError(f"cache input changed while reading: {path}")
        with self.lock:
            self.hashes[before] = value
        return value

    def context(self) -> str | None:
        if platform.system() != "Linux" or len(self.tool.emit_argv) != 1:
            return None
        # Arbitrary wrappers, response files and compiler plugins can read
        # inputs outside the declared search trees. Keep their verdicts fresh.
        flags = shlex.split(self.args.cc_flags)
        if any(not re.fullmatch(r"-(?:std=[\w+]+|O[0-3sgz]|g\d*|W[\w=+-]+|pipe)", flag)
               for flag in flags):
            return None
        if any(os.environ.get(name) for name in
               ("LD_PRELOAD", "LD_LIBRARY_PATH", "GCC_EXEC_PREFIX", "COMPILER_PATH",
                "CCACHE_PREFIX", "CPATH", "C_INCLUDE_PATH", "LIBRARY_PATH")):
            return None
        try:
            cc = shutil.which(self.args.cc)
            if cc is None:
                return None
            executables = [Path(self.tool.emit_argv[0]), Path(cc)]
            if self.args.cc_cache:
                cache = shutil.which(self.args.cc_cache)
                if cache is None:
                    return None
                executables.append(Path(cache))
            for executable in executables:
                with executable.open("rb") as stream:
                    if stream.read(4) != b"\x7fELF":
                        return None
            def probe(*options: str) -> str:
                output = subprocess.run([cc, *options], input=b"", capture_output=True,
                                        timeout=self.args.timeout,
                                        env={**os.environ, "LC_ALL": "C"})
                if output.returncode:
                    raise ValueError("native toolchain probe failed")
                return (output.stdout + output.stderr).decode(errors="replace")
            for program in ("cc1", "as", "ld"):
                found = shutil.which(probe("-print-prog-name=" + program).strip())
                if found:
                    executables.append(Path(found))
            roots = {Path("/usr/include"), Path("/usr/lib"), Path("/lib")}
            search = probe("-print-search-dirs")
            for line in search.splitlines():
                if line.startswith(("programs: =", "libraries: =")):
                    roots.update(Path(value) for value in line.split("=", 1)[1].split(os.pathsep)
                                 if value)
            include = probe(*flags, "-E", "-x", "c", "-v", "-o", os.devnull, "-")
            collecting = False
            for line in include.splitlines():
                if line.startswith("#include") and line.endswith("search starts here:"):
                    collecting = True
                elif line.strip() == "End of search list.":
                    collecting = False
                elif collecting:
                    roots.add(Path(line.strip()))
            roots = {root.resolve() for root in roots if root.is_dir()}
            roots = {root for root in roots if not any(parent in roots for parent in root.parents)}
            native = []
            seen = set()
            for root in sorted(roots):
                pending = [str(root)]
                while pending:
                    directory = pending.pop()
                    info = os.stat(directory)
                    identity = (info.st_dev, info.st_ino)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    try:
                        with os.scandir(directory) as scan:
                            entries = sorted(scan, key=lambda entry: entry.name)
                    except PermissionError:
                        native.append((directory, info.st_mode, info.st_ctime_ns, "unreadable"))
                        continue
                    for entry in entries:
                        try:
                            info = entry.stat()
                            native.append((entry.path, info.st_dev, info.st_ino, info.st_size,
                                           info.st_mtime_ns, info.st_ctime_ns, info.st_mode,
                                           os.readlink(entry.path) if entry.is_symlink() else None))
                            if entry.is_dir():
                                pending.append(entry.path)
                        except FileNotFoundError:
                            native.append((entry.path, "missing"))
            native_files = [path for _, paths, _ in NATIVE_FLOORS for path in paths]
            return self.digest({
                "version": self.VERSION,
                "compiler": [(str(path), self.file_digest(path)) for path in executables],
                "harness": self.file_digest(Path(__file__)),
                "native": native,
                "native_floors": [(str(path), self.file_digest(path)) for path in native_files],
                "environment": self.digest(dict(os.environ)),
                "platform": platform.uname(), "cwd": str(Path.cwd()),
                "user": [os.getuid(), os.getgid(), os.getgroups()],
                "umask": next((line for line in Path("/proc/self/status").read_text().splitlines()
                               if line.startswith("Umask:")), None),
                "limits": {name: resource.getrlimit(getattr(resource, name))
                           for name in dir(resource) if name.startswith("RLIMIT_")},
                "loader": [(str(path), self.file_digest(path) if path.is_file() else None)
                           for path in (Path("/etc/ld.so.cache"), Path("/etc/ld.so.preload"))],
                "arguments": [flags, self.args.cc_cache, str(self.args.cc_work_dir),
                              self.args.stage, self.args.timeout, self.args.run_timeout],
            })
        except (OSError, ValueError, subprocess.SubprocessError):
            return None

    def key(self, test: Test) -> str | None:
        if self.identity is None or test.stage_at is not None:
            return None
        files = staged_files(test, self.tool)
        fixture = tree_files(test.source) if test.is_dir else {
            path.name: path for path in test.source.parent.glob(test.source.stem + ".*")}
        def snapshot(entries, shared=False):
            rows = []
            for name, path in sorted(entries.items()):
                row = self.source_rows.get(path) if shared else None
                if row is None:
                    mode = path.stat().st_mode
                    row = (stat.S_IMODE(mode), "directory" if stat.S_ISDIR(mode)
                           else self.file_digest(path))
                rows.append((name, *row))
            return rows
        # Parsed expectations are also included: collection happens before keys
        # are computed, and a simultaneous sidecar edit must not bless old data.
        expectation = [test.expected.hex(), test.exit_code, test.stderr_lines,
                       test.count_max, test.stdin_bytes.hex() if test.stdin_bytes is not None else None,
                       test.args_words, test.env_pairs]
        return self.digest([self.identity, test.tid, test.kind, staged_entry(test),
                            stat.S_IMODE(test.source.stat().st_mode),
                            snapshot(files, shared=True), snapshot(fixture), expectation])

    def lookup(self, test: Test, key: str | None) -> Result | None:
        if key is None:
            return None
        with self.lock:
            self.checked.append((test, key))
            self.keys[test.tid] = key
        if self.args.refresh_result_cache:
            return None
        try:
            record = json.loads((self.directory / (key + ".json")).read_text())
            if record.get("version") == self.VERSION and record.get("key") == key \
                    and record.get("passed") is True and isinstance(record.get("detail"), str):
                return Result(test, True, detail=record["detail"], cached=True)
        except (OSError, ValueError, AttributeError):
            pass
        return None

    def remember(self, result: Result, key: str | None) -> None:
        if key is not None and result.ok and result.cacheable and not result.cached \
                and result.test.stage_at is None and self.key(result.test) == key:
            with self.lock:
                self.pending.append((key, result.detail))

    def restore_binary(self, test: Test, work: Path) -> bool:
        key = self.keys.get(test.tid)
        if key is None or self.args.refresh_result_cache or test.tid in self.REWRITTEN:
            return False
        directory = self.directory / (key + ".artifact")
        try:
            if not directory.is_dir():
                return False
            with (self.directory / (key + ".lock")).open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_SH)
                record = json.loads((directory / "manifest.json").read_text())
                if record.get("key") != key or record.get("version") != self.VERSION:
                    return False
                if not os.access(directory / "prog", os.X_OK):
                    return False
                for name in ("out.c", "prog"):
                    if self.file_digest(directory / name) != record["files"][name]:
                        return False
                for name in ("out.c", "prog"):
                    shutil.copy2(directory / name, work / name)
                return True
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def remember_binary(self, test: Test, work: Path) -> None:
        key = self.keys.get(test.tid)
        if key is None or test.tid in self.REWRITTEN:
            return
        generated = (work / "out.c").read_bytes()
        if any(marker in generated for marker in
               (b"__FILE__", b"__BASE_FILE__", b"__DATE__", b"__TIME__", os.fsencode(work))):
            return
        if re.search(rb'(?m)^\s*#\s*include\s*"', generated):
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix=".pending-artifact-", dir=self.directory))
        try:
            files = {}
            for name in ("out.c", "prog"):
                shutil.copy2(work / name, directory / name)
                files[name] = self.file_digest(directory / name)
            (directory / "manifest.json").write_text(json.dumps({
                "version": self.VERSION, "key": key, "files": files}))
            with self.lock:
                self.artifacts.append((key, directory))
        except BaseException:
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def discard_pending(self) -> None:
        for _, directory in self.artifacts:
            shutil.rmtree(directory, ignore_errors=True)

    def publish(self) -> None:
        # No entries survive a source/toolchain/environment edit during a run.
        if self.identity is None:
            return
        self.tool.check_source_state()
        if self.context() != self.identity or any(self.key(test) != key for test, key in self.checked):
            raise HarnessError("test cache inputs changed during this run; rerun after edits finish")
        if not self.pending and not self.artifacts:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        for key, detail in self.pending:
            fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=self.directory)
            try:
                with os.fdopen(fd, "w") as stream:
                    json.dump({"version": self.VERSION, "key": key,
                               "passed": True, "detail": detail}, stream)
                os.replace(temporary, self.directory / (key + ".json"))
            finally:
                Path(temporary).unlink(missing_ok=True)
        for key, directory in self.artifacts:
            destination = self.directory / (key + ".artifact")
            # Readers hold the same lock. Replace even an existing entry so a
            # fresh successful run repairs corruption instead of missing forever.
            with (self.directory / (key + ".lock")).open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                shutil.rmtree(destination, ignore_errors=True)
                os.rename(directory, destination)


def deterministic_binary(binary: Path, timeout: float) -> bool:
    """Unknown foreign/runtime dependencies must execute on every invocation."""
    allowed = {
        "__libc_start_main", "__cxa_finalize", "__stack_chk_fail", "abort", "exit",
        "malloc", "calloc", "realloc", "free", "aligned_alloc", "posix_memalign",
        "memcpy", "memmove", "memset", "memcmp", "memchr", "strlen", "strcmp",
        "strncmp", "strchr", "strrchr", "strstr", "strtol", "strtoul", "strtoll",
        "strtoull", "strtod", "printf", "fprintf", "sprintf", "snprintf", "puts",
        "putchar", "fputs", "fputc", "fwrite", "fflush", "stdout", "stderr",
        "__errno_location", "sqrt", "sqrtf", "floor", "floorf", "ceil", "ceilf",
        "fmod", "fmodf", "pow", "powf", "sin", "cos", "tan", "fabs", "fabsf",
        "_ITM_deregisterTMCloneTable", "_ITM_registerTMCloneTable", "__gmon_start__",
    }
    try:
        symbols = subprocess.run(["nm", "-D", "--undefined-only", str(binary)],
                                 capture_output=True, text=True, timeout=timeout)
        if symbols.returncode:
            return False
        names = {line.split()[-1].split("@", 1)[0]
                 for line in symbols.stdout.splitlines() if line.split()}
        # Static binaries have no dynamic dependency list to prove their closure.
        return bool(names) and names <= allowed
    except (OSError, subprocess.SubprocessError):
        return False


class LoopbackPeer:
    """One deterministic IPv4 peer for the TCP corpus test."""

    def __init__(self) -> None:
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.problem = ""
        self.thread: threading.Thread | None = None

    @staticmethod
    def _read(conn: socket.socket, count: int) -> bytes:
        out = bytearray()
        while len(out) < count:
            chunk = conn.recv(count - len(out))
            if not chunk:
                break
            out.extend(chunk)
        return bytes(out)

    def _serve(self, timeout: float) -> None:
        try:
            self.listener.settimeout(timeout)
            conn, _ = self.listener.accept()
            with conn:
                conn.settimeout(timeout)
                first = self._read(conn, 4)
                if first != b"ping":
                    raise RuntimeError(f"peer received {first!r}, wanted b'ping'")
                conn.sendall(b"p")
                second = self._read(conn, 3)
                if second != b"ack":
                    raise RuntimeError(f"peer received {second!r}, wanted b'ack'")
                conn.sendall(b"ong")
        except (OSError, RuntimeError) as exc:
            self.problem = str(exc)

    def start(self, timeout: float) -> None:
        self.thread = threading.Thread(
            target=self._serve, args=(timeout,), daemon=True
        )
        self.thread.start()

    def finish(self, timeout: float) -> str:
        self.listener.close()
        if self.thread is not None:
            self.thread.join(min(timeout, 2.0))
            if self.thread.is_alive() and not self.problem:
                self.problem = "loopback peer did not finish"
        return self.problem

    def close(self) -> None:
        self.listener.close()


class TlsLoopbackPeer(LoopbackPeer):
    """Two TLS handshakes: one trusted hostname and one rejected mismatch."""

    def __init__(self, work: Path, timeout: float) -> None:
        super().__init__()
        self.listener.listen(2)
        self.cert = work / "loopback-cert.pem"
        key = work / "loopback-key.pem"
        openssl = shutil.which("openssl")
        if openssl is None:
            self.close()
            raise HarnessError("TLS corpus needs the OpenSSL command")
        made = run_process([
            openssl, "req", "-x509", "-newkey", "ec",
            "-pkeyopt", "ec_paramgen_curve:P-256", "-sha256", "-nodes",
            "-keyout", str(key), "-out", str(self.cert), "-days", "1",
            "-subj", "/CN=localhost",
            "-addext", "subjectAltName=DNS:localhost",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,digitalSignature,keyCertSign",
            "-addext", "extendedKeyUsage=serverAuth",
        ], timeout)
        if made.timed_out or made.code != 0:
            self.close()
            raise HarnessError(
                "could not mint the loopback TLS certificate: "
                + clip(diagnostics(made))
            )
        try:
            self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self.context.load_cert_chain(self.cert, key)
        except (OSError, ssl.SSLError):
            self.close()
            raise

    def _serve(self, timeout: float) -> None:
        try:
            self.listener.settimeout(timeout)
            for attempt in range(2):
                conn, _ = self.listener.accept()
                with conn:
                    conn.settimeout(timeout)
                    try:
                        tls = self.context.wrap_socket(conn, server_side=True)
                    except ssl.SSLError:
                        if attempt == 0:
                            raise
                        continue
                    with tls:
                        if attempt == 1:
                            raise RuntimeError("the mismatched hostname was accepted")
                        tls.sendall(b"x")
                        if tls.recv(1) != b"":
                            raise RuntimeError("the verified TLS stream did not close")
        except (OSError, RuntimeError, ssl.SSLError) as exc:
            self.problem = str(exc)


def native_link_args(out_c: Path) -> list[str]:
    """Native sources and libraries referenced by one generated C program."""
    try:
        generated = out_c.read_bytes()
    except OSError as exc:
        raise HarnessError(f"cannot inspect generated C {out_c}: {exc}") from exc

    sources: list[str] = []
    libraries: list[str] = []
    for symbol, needed_sources, needed_libraries in NATIVE_FLOORS:
        if symbol not in generated:
            continue
        for source in needed_sources:
            if not source.is_file():
                raise HarnessError(
                    f"generated C references {symbol.decode()} but its native "
                    f"floor does not exist: {source}"
                )
            spelling = str(source)
            if spelling not in sources:
                sources.append(spelling)
        for library in needed_libraries:
            if library not in libraries:
                libraries.append(library)
    return [*sources, *libraries]


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


def tree_files(root: Path) -> dict[str, Path]:
    """Files and empty directories copied by staging; follow source symlinks."""
    if not root.is_dir():
        return {root.name: root}
    files = {}
    def visit(directory: Path, ancestors: frozenset[Path]) -> None:
        real = directory.resolve()
        if real in ancestors:
            raise HarnessError(f"cyclic source directory: {directory}")
        for path in sorted(directory.iterdir()):
            files[path.relative_to(root).as_posix()] = path
            if path.is_dir():
                visit(path, ancestors | {real})
    visit(root, frozenset())
    return files


def sublayers_named_in(path: Path) -> set[str]:
    named = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        named.update(SUBLAYER_RHS.findall(line.split("//", 1)[0]))
    return named


def staged_files(test: Test, tool: Toolchain) -> dict[str, Path]:
    """The same manifest drives cache keys and private staging copies."""
    files = tree_files(test.source)
    if not tool.src_root or not tool.src_root.is_dir():
        return files
    mine = {name.split("/", 1)[0] for name in files}
    available = set(tool.modules) - mine
    wanted = ({"std"} | _modules_named_in(test.source)) & available
    frontier = sorted(wanted)
    while frontier:
        name = frontier.pop()
        for dep in sorted(tool.imports.get(name, frozenset()) & available):
            if dep not in wanted:
                wanted.add(dep)
                frontier.append(dep)
    for name in sorted(wanted):
        module = tool.modules[name]
        if module.is_dir():
            files[name] = module
            files.update({name + "/" + relative: path
                          for relative, path in tool.module_files[name].items()})
        else:
            files[name] = module

    # Plain std cannot vote to retain compiler frontend sublayers. Only the
    # test, other modules, and already retained sublayers supply those imports.
    def votes(paths: Iterable[Path]) -> set[str]:
        named = set()
        for path in paths:
            if path.suffix != ".zen":
                continue
            cached = tool.sublayer_imports.get(path)
            if cached is not None:
                named.update(cached)
            elif path.is_file():
                named.update(sublayers_named_in(path))
        return named
    kept = votes(path for name, path in files.items() if not name.startswith("std/"))
    frontier = sorted(kept)
    while frontier:
        name = frontier.pop()
        for dep in sorted(votes(path for relative, path in files.items()
                                if relative.startswith("std/" + name + "/")) - kept):
            kept.add(dep)
            frontier.append(dep)
    removed = {"std/" + name for name in SUBLAYER - kept}
    return {name: path for name, path in files.items()
            if not any(name == prefix or name.startswith(prefix + "/") for prefix in removed)}


def stage(test: Test, tool: Toolchain, work: Path) -> Path:
    """Copy exactly the test's resolved staging manifest into a private tree."""
    root = work / "src"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    manifest = staged_files(test, tool)
    for name, path in manifest.items():
        target = root / name
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    for name, path in reversed(list(manifest.items())):
        if path.is_dir():
            shutil.copystat(path, root / name)
    if test.source.is_dir():
        shutil.copystat(test.source, root)
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
    for path in ([root] if root.is_file() else root.rglob("*.zen")):
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
    entry = staged_entry(test)
    loopback: LoopbackPeer | None = None

    # A CLOCK TEST'S CONSTANT IS REWRITTEN HERE AND ONLY HERE, before the
    # compiler runs. A wall-clock expectation depends on when the run
    # happens, which `.expected` bytes cannot hold; the test's
    # HARNESS_EPOCH is rewritten to the second this run starts, so "near"
    # has a number to be near. The regex names one line and rewrites one
    # number, and a file that no longer carries that line fails loudly --
    # a silent no-op would leave a test asserting against epoch zero, red
    # forever while reading as coverage.
    if test.tid == "corpus/env/clock_reads_are_two_authorities":
        try:
            path = root / entry
            text = path.read_text(encoding="utf-8")
            patched, n = re.subn(
                r"HARNESS_EPOCH\* : u64 = \d+",
                f"HARNESS_EPOCH* : u64 = {int(time.time())}",
                text,
            )
            if n != 1:
                raise AssertionError(f"HARNESS_EPOCH lines rewritten: {n}, want 1")
            path.write_text(patched, encoding="utf-8")
        except (OSError, AssertionError) as e:
            return Result(test, False, [f"the harness could not stage the clock epoch: {e}"])

    if test.tid == "corpus/net/tcp_connect":
        try:
            loopback = LoopbackPeer()
            path = root / entry
            text = path.read_text(encoding="utf-8")
            patched, n = re.subn(
                r"HARNESS_PORT\* : u16 = \d+",
                f"HARNESS_PORT* : u16 = {loopback.port}",
                text,
            )
            if n != 1:
                raise AssertionError(f"HARNESS_PORT lines rewritten: {n}, want 1")
            path.write_text(patched, encoding="utf-8")
        except (OSError, AssertionError) as e:
            if loopback is not None:
                loopback.close()
            return Result(test, False, [f"the harness could not stage loopback TCP: {e}"])

    if test.tid == "corpus/net/tls_connect":
        try:
            loopback = TlsLoopbackPeer(work, args.timeout)
            path = root / entry
            text = path.read_text(encoding="utf-8")
            patched, n = re.subn(
                r"HARNESS_PORT\* : u16 = \d+",
                f"HARNESS_PORT* : u16 = {loopback.port}",
                text,
            )
            if n != 1:
                raise AssertionError(f"HARNESS_PORT lines rewritten: {n}, want 1")
            path.write_text(patched, encoding="utf-8")
        except (HarnessError, OSError, AssertionError, ssl.SSLError) as e:
            if loopback is not None:
                loopback.close()
            return Result(test, False, [f"the harness could not stage loopback TLS: {e}"])

    binary = work / "prog"
    cache = getattr(args, "verdict_cache", None)
    restored = cache.restore_binary(test, work) if cache else False
    if not restored:
        emit = run_process(tool.command(root, out_c, root, entry), args.timeout)
        if emit.timed_out:
            if loopback is not None:
                loopback.close()
            return Result(test, False, [f"the compiler timed out after {args.timeout}s"])
        if emit.code != 0 or not out_c.is_file():
            if loopback is not None:
                loopback.close()
            return Result(
                test,
                False,
                [f"the compiler rejected a corpus program (exit {emit.code})"],
                clip(diagnostics(emit)),
            )

        try:
            native = native_link_args(out_c)
        except HarnessError:
            if loopback is not None:
                loopback.close()
            raise
        cc = tool.c_compiler.build(test.tid, out_c, binary, native)
        if cc.timed_out or cc.code != 0:
            if loopback is not None:
                loopback.close()
            # A rejected translation unit is a codegen bug, not harness noise.
            note = clip(diagnostics(cc))
            if args.keep:
                note += f"\ngenerated C kept at: {out_c}"
            return Result(test, False, [f"the C compiler rejected the generated C (exit {cc.code})"], note)

    # Run in the work directory: a program that writes a file must not write it
    # into the test tree.
    # A LONG-NAME ENV TEST NEEDS NAMES .expected CANNOT HOLD AND NO SHELL
    # EXPORTS (#814). `env_var_resolves_a_name_of_any_length` asks about a
    # 5039-byte name and one at exactly 4096 -- past, and at, the cap the
    # backend used to impose before answering "not set". The names are
    # generated HERE and exported for THIS program alone; without them its
    # premise ("the variable IS set") is false and the test would pass for
    # the wrong reason. Keyed by tid like the clock rewrite above: any other
    # test's environment is untouched.
    # None is "inherit this process's environment", which is what every other
    # test wants and what `run_process` passes straight to subprocess.
    prog_env = None
    if test.tid == "corpus/env/env_var_resolves_a_name_of_any_length":
        prog_env = dict(os.environ)
        prog_env["V" * 5039] = "hello"
        prog_env["B" * 4096] = "hello"
    if isinstance(loopback, TlsLoopbackPeer):
        prog_env = dict(os.environ)
        prog_env["SSL_CERT_FILE"] = str(loopback.cert)
    if test.env_pairs:
        prog_env = dict(prog_env if prog_env is not None else os.environ)
        prog_env.update(test.env_pairs)

    if test.tid == "corpus/file-io/symlink_loop_is_failed":
        try:
            (work / "loop").symlink_to("loop")
        except OSError as e:
            return Result(test, False, [f"the harness could not stage the symlink loop: {e}"])

    if loopback is not None:
        loopback.start(args.run_timeout)
    prog = run_process([str(binary), *test.args_words], args.run_timeout, cwd=work,
                       feed=test.stdin_bytes, env=prog_env)
    peer_problem = loopback.finish(args.run_timeout) if loopback is not None else ""
    if prog.timed_out:
        return Result(test, False, [f"the program timed out after {args.run_timeout}s"])

    if peer_problem:
        reasons.append(f"loopback peer failed: {peer_problem}")

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

    result = Result(test, not reasons, reasons, "\n".join(d for d in detail if d),
                    cacheable=(not cache or deterministic_binary(binary, args.timeout)),
                    artifact_cached=restored)
    if cache and result.ok and not result.cacheable and not restored:
        cache.remember_binary(test, work)
    return result



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

    # THE BOUND. A rejection asserts a NUMBER of diagnostics: the complaints
    # its `.expected` names positions for, and nothing more -- one mistake,
    # one diagnostic, the property `parse/one_error_no_cascade` exists to
    # police. `.count` states the number where it genuinely differs; absent
    # one, the positions ARE the number, which is the natural reading of a
    # file whose author wrote one complaint down. Before issue #746 the
    # default was no bound at all, and a test asserting one diagnostic passed
    # identically against one-plus-nine -- the surplus invisible, because the
    # captured text below was discarded on a pass.
    if test.count_max is not None:
        bound, bound_src = test.count_max, test.count_path.name
    else:
        bound = len(test.positions)
        bound_src = f"{len(test.positions)} asserted position(s)"
    total = DIAG_TOTAL.search(text)
    if total is None:
        # The bound cannot be checked, so the test does not pass. A count
        # gate that silently gives up when it cannot count is the exact
        # thing this assertion exists to prevent.
        reasons.append(
            f"{bound_src} bounds the diagnostic count at {bound}, but the "
            f"compiler printed no `N diagnostic(s)` total to compare against"
        )
    elif int(total.group(1)) > bound:
        reasons.append(
            f"{total.group(1)} diagnostics, at most {bound} allowed "
            f"[{bound_src}]: one mistake must not cascade"
        )

    # A pass keeps what the compiler said, too. Before issue #746 this was
    # `clip(text) if reasons else ""`: a green test remembered nothing, which
    # is how #741's surplus diagnostic hid inside a passing gate for weeks --
    # nobody could ask later what a pass had cost. What is graded does not
    # change; what is REMEMBERED does.
    return Result(test, not reasons, reasons, clip(text))


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
            seconds=result.seconds,
        ), False
    return result, True


def run_one(test: Test, tool: Toolchain, workroot: Path, args: argparse.Namespace) -> Result:
    work = workroot / re.sub(r"[^A-Za-z0-9_.-]", "_", test.tid)
    work.mkdir(parents=True, exist_ok=True)
    if test.kind in (CORPUS, EXAMPLE):
        return run_corpus(test, tool, work, args)
    return run_must_fail(test, tool, work, args)


# ------------------------------------------------------------- self-check


SELF_CHECK_CASES: list[tuple[str, str, str, int | None, bool, str]] = [
    # (name, `.expected`, what the compiler prints, `.count` or None,
    #  verdict wanted, a substring some reason must carry when red)
    #
    # The harness auditing ITSELF, without a compiler. Issue #746 sat
    # unnoticed for the suite's whole life because nothing here could fail
    # in the dimension it existed for: these are the assertions that make
    # the bound falsifiable. Break one on purpose before trusting it again.
    (
        "surplus-diagnostic-goes-red",
        "f was consumed\n24:12\n",
        "prog.zen:24:12: use after move: f was consumed\n"
        "prog.zen:27:5: a partial move reaches the drop\n"
        "zen: 2 diagnostic(s)\n",
        None, False, "at most 1 allowed",
    ),
    (
        "exactly-the-asserted-diagnostic-stays-green",
        "f was consumed\n24:12\n",
        "prog.zen:24:12: use after move: f was consumed\n"
        "zen: 1 diagnostic(s)\n",
        None, True, "",
    ),
    (
        "two-asserted-positions-bound-two",
        "an impl collision\n3:1\n7:2\n",
        "prog.zen:3:1: an impl collision\nprog.zen:7:2: a duplicate signature\n"
        "zen: 2 diagnostic(s)\n",
        None, True, "",
    ),
    (
        "count-file-overrides-the-default",
        "f was consumed\n24:12\n",
        "prog.zen:24:12: use after move: f was consumed\n"
        "prog.zen:27:5: a partial move reaches the drop\n"
        "zen: 2 diagnostic(s)\n",
        2, True, "",
    ),
    (
        "a-missing-total-fails-rather-than-passes",
        "f was consumed\n24:12\n",
        "prog.zen:24:12: use after move: f was consumed\n",
        None, False, "printed no",
    ),
]


NATIVE_LINK_CASES: list[tuple[str, bytes, tuple[str, ...]]] = [
    (
        "hello-world-has-no-native-or-openssl-dependency",
        b"int main(void) { return 0; }\n",
        (),
    ),
    (
        "libc-network-reference-needs-no-extra-link-argument",
        b"extern int getaddrinfo(void); void f(void) { getaddrinfo(); }\n",
        (),
    ),
    (
        "any-openssl-reference-selects-only-system-libraries",
        b"extern void SSL_read_ex(void); void f(void) { SSL_read_ex(); }\n",
        ("-lssl", "-lcrypto"),
    ),
    (
        "proc-reference-selects-only-proc",
        b"extern void zg_proc_run(void); void f(void) { zg_proc_run(); }\n",
        (str(REPO_ROOT / "src/std/proc/proc.c"),),
    ),
]


def _self_check_toolchain(work: Path) -> Toolchain:
    """A stub compiler: prints a scripted diagnostic and exits 1.

    Real enough for `run_must_fail`, which asks three things of a process --
    non-zero exit, no crash markers, printable diagnostics -- and nothing
    about Zen. `src_root` stays None: `stage` then copies the lone source
    and stages no std, which no assertion below reads.
    """
    stub = work / "stub-zen"
    stub.write_text("#!/bin/sh\ncat \"$STUB_DIAG\"\nexit 1\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return Toolchain("stub-zen", [str(stub)], src_root=None)


def self_check(args: argparse.Namespace) -> int:
    """Assert the must-fail gate goes red exactly when TESTING.md says it must."""
    failures: list[str] = []
    os.environ.pop("STUB_DIAG", None)
    try:
        workroot = Path(tempfile.mkdtemp(prefix="zen-selfcheck."))
        tool = _self_check_toolchain(workroot)
        source = workroot / "prog.zen"
        source.write_text("main = (env: Env) Res<i32, AllocError> { Ok(0) }\n",
                          encoding="utf-8")
        for name, expected_text, output, count_max, want_ok, want_reason \
                in SELF_CHECK_CASES:
            diag = workroot / "diag.txt"
            diag.write_text(output, encoding="utf-8")
            os.environ["STUB_DIAG"] = str(diag)
            test = Test(
                tid="self-check/probe",
                kind=MUST_FAIL,
                suite="self-check",
                source=source,
                entry=source,
                expected_path=workroot / "prog.expected",
                expected=expected_text.encode("utf-8"),
                count_max=count_max,
                count_path=workroot / ".count" if count_max is not None else None,
            )
            result = run_must_fail(test, tool, workroot / "case", args)
            if result.ok != want_ok:
                failures.append(
                    f"{name}: {'passed' if result.ok else 'failed'}, "
                    f"wanted {'pass' if want_ok else 'fail'} -- {result.reasons}"
                )
            elif not result.ok and want_reason and \
                    want_reason not in " ".join(result.reasons):
                failures.append(f"{name}: no reason names {want_reason!r}: "
                                f"{result.reasons}")
            if result.ok and output.strip() and \
                    output.strip().splitlines()[0] not in result.detail:
                failures.append(
                    f"{name}: a pass discarded what the compiler said "
                    f"(kept {result.detail!r}); the surplus behind #741 hid "
                    f"in exactly that throw"
                )
        for name, generated, expected in NATIVE_LINK_CASES:
            out_c = workroot / f"{name}.c"
            out_c.write_bytes(generated)
            got = tuple(native_link_args(out_c))
            if got != expected:
                failures.append(
                    f"{name}: native link args {got!r}, wanted {expected!r}"
                )
        shutil.rmtree(workroot, ignore_errors=True)
    finally:
        os.environ.pop("STUB_DIAG", None)
    if failures:
        for line in failures:
            print(f"self-check FAIL {line}", file=sys.stderr)
        return 1
    checks = len(SELF_CHECK_CASES) + len(NATIVE_LINK_CASES)
    print(f"self-check: {checks} assertion(s) about the "
          "harness itself hold")
    return 0


# ---------------------------------------------------------------------- main


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="tests/run.py",
        description="run the tests/corpus and tests/must-fail gates",
    )
    p.add_argument("--zen", default="zen", help="path to the zen binary")
    p.add_argument("--cc", default=os.environ.get("CC", "cc"), help="C compiler")
    p.add_argument("--cc-flags",
                   default=os.environ.get("CFLAGS", "-std=c11 -O0 -g -Werror=return-type"),
                   help="flags passed to the C compiler")
    p.add_argument("--cc-cache", default="", metavar="COMMAND",
                   help="optional ccache executable; caches C objects, never test verdicts")
    p.add_argument("--cc-work-dir", type=Path, default=REPO_ROOT / "build/test-native",
                   help="locked stable C paths used with --cc-cache")
    p.add_argument("--result-cache", type=Path, metavar="DIR",
                   help="reuse passed test verdicts with unchanged inputs (development only)")
    p.add_argument("--refresh-result-cache", action="store_true",
                   help="execute and compile fresh, then update successful cache entries")
    p.add_argument("--no-result-cache", action="store_true",
                   help="execute every selected test; do not read or write verdicts")
    p.add_argument("--tests", default=str(TESTS_DIR), help="the tests/ directory")
    p.add_argument("--filter", action="append", default=[], metavar="GLOB",
                   help="select tests whose id matches (repeatable)")
    p.add_argument("--list", action="store_true", help="print selected test ids and exit")
    p.add_argument("--jobs", "-j", type=positive_int, default=os.cpu_count() or 1)
    p.add_argument("--shard", type=shard_arg, metavar="INDEX/COUNT",
                   help="run a disjoint one-based shard of the sorted filtered tests")
    p.add_argument("--timings", nargs="?", type=positive_int, const=10, metavar="N",
                   help="report the N slowest tests (default: 10)")
    p.add_argument("--timings-json", type=Path, metavar="PATH",
                   help="write all test durations and verdicts as JSON")
    p.add_argument("--stage", type=int, default=_current_stage(),
                   help="PLAN.md stage to grade against; a test whose .stage is "
                        "ahead of it is deferred rather than failed")
    p.add_argument("--timeout", type=float, default=120.0, help="seconds for one compile")
    p.add_argument("--run-timeout", type=float, default=20.0, help="seconds for one program")
    p.add_argument("--keep", action="store_true", help="keep the work directory")
    p.add_argument("--self-check", action="store_true",
                   help="assert the must-fail gate itself goes red exactly "
                        "when it must; needs no compiler")
    p.add_argument("--verbose", "-v", action="store_true", help="print a line per passing test")
    p.add_argument("--allow-uncollected", action="store_true",
                   help="do not fail when a .zen file belongs to no test")
    return p.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)

    if args.self_check:
        return self_check(args)

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

    # THE FLOOR UNDER THE EXAMPLE SUITE. A gate that finds zero inputs and
    # exits 0 has told you nothing, and that is the failure this tree keeps
    # rediscovering -- `grammar-test` parsing a directory that did not exist
    # and reporting "Total parses: 0, exit 0" is the same shape. example/ is
    # ONE directory and one rename away from collecting nothing, and the rest
    # of this runner would go green on the corpus and never mention it. So
    # the suite asserts it is non-empty, and an empty one is exit 2 -- the
    # harness could not run -- rather than a pass.
    if not any(test.kind == EXAMPLE for test in found.tests):
        print(
            f"run.py: the {EXAMPLE}/ suite collected no programs. Either the"
            " directory moved or its `.expected` sidecars did, and this gate"
            " just stopped compiling the tree's worked example -- which is"
            " the state it was written to end.",
            file=sys.stderr,
        )
        return 2

    matched = select(found.tests, args.filter)
    selected = shard(matched, args.shard)

    if matched and not selected:
        index, count = args.shard
        print(f"run.py: shard {index}/{count} selected no tests from "
              f"{len(matched)} matching test(s)", file=sys.stderr)
        return 2

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
        if any(t.kind in (CORPUS, EXAMPLE) for t in selected) \
                and shutil.which(args.cc) is None:
            raise HarnessError(f"no C compiler on PATH: {args.cc!r} (pass --cc)")
        if args.cc_cache and shutil.which(args.cc_cache) is None:
            raise HarnessError(f"no C compiler cache on PATH: {args.cc_cache!r}")
    except HarnessError as exc:
        print(f"run.py: {exc}", file=sys.stderr)
        return 2

    verdict_cache = (ResultCache(args.result_cache, tool, args)
                     if args.result_cache and not args.no_result_cache else None)
    args.verdict_cache = verdict_cache
    if verdict_cache and verdict_cache.identity is None:
        print("run.py: result cache disabled: unsupported native toolchain/platform configuration")
    workroot = Path(tempfile.mkdtemp(prefix="zen-tests."))
    results: list[Result] = []
    deferred: list[Result] = []
    harness_errors: list[str] = []
    started = time.perf_counter()

    def task(test: Test) -> Result:
        test_started = time.perf_counter()
        try:
            key = verdict_cache.key(test) if verdict_cache else None
            result = verdict_cache.lookup(test, key) if verdict_cache else None
            if result is None:
                result = run_one(test, tool, workroot, args)
                if verdict_cache:
                    verdict_cache.remember(result, key)
        except HarnessError as exc:
            harness_errors.append(f"{test.tid}: {exc}")
            result = Result(test, False, [f"harness error: {exc}"])
        except Exception as exc:  # a runner that tracebacks reports nothing
            harness_errors.append(f"{test.tid}: {type(exc).__name__}: {exc}")
            result = Result(test, False, [f"harness error: {type(exc).__name__}: {exc}"])
        result.seconds = time.perf_counter() - test_started
        return result

    try:
        print(
            f"run.py: {len(selected)} test(s) via {tool.name} "
            f"[{shlex.join(tool.emit_argv)}], {args.jobs} job(s)"
        )
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
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
                        print(f"{'cached' if result.cached else 'ok  '} {result.test.tid}")
                        # What the compiler said beside the pass: the same
                        # bytes a failure would carry, so a green tick is
                        # never the whole story (#746).
                        for line in result.detail.splitlines():
                            print(f"     | {line}")
                else:
                    print(f"FAIL {result.test.tid}: {result.reasons[0]}")
    finally:
        if args.keep:
            print(f"run.py: work directory kept at {workroot}")
        else:
            shutil.rmtree(workroot, ignore_errors=True)

    try:
        tool.check_source_state()
        if verdict_cache and not harness_errors:
            verdict_cache.publish()
    except (HarnessError, OSError) as exc:
        harness_errors.append(str(exc))
    finally:
        if verdict_cache:
            verdict_cache.discard_pending()

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

    cached = sum(result.cached for result in results)
    artifact_cached = sum(result.artifact_cached for result in results)
    passed = len(results) - len(failures) - len(deferred)
    print(f"\nrun.py: {passed} passed, {len(failures)} failed, "
          f"{len(deferred)} deferred, "
          f"{len(found.uncollected)} uncollected, {len(found.tests) - len(selected)} deselected"
          + (f", {cached} cached, {artifact_cached} executable(s) reused" if verdict_cache else ""))

    elapsed = time.perf_counter() - started
    deferred_ids = {result.test.tid for result in deferred}
    if args.timings:
        print(f"\nslowest tests (wall seconds per test; {elapsed:.3f}s batch):")
        for result in sorted(results, key=lambda r: (-r.seconds, r.test.tid))[:args.timings]:
            print(f"    {result.seconds:8.3f}s  {result.test.tid}")
    if args.timings_json:
        report = {
            "version": 1,
            "elapsed_seconds": elapsed,
            "jobs": args.jobs,
            "cc_cache": args.cc_cache or None,
            "result_cache": str(args.result_cache) if verdict_cache else None,
            "cached": cached,
            "artifact_cached": artifact_cached,
            "filter": args.filter,
            "harness_errors": list(harness_errors),
            "uncollected": found.uncollected,
            "shard": ({"index": args.shard[0], "count": args.shard[1]}
                      if args.shard else None),
            "tests": [
                {"id": result.test.tid, "seconds": result.seconds, "cached": result.cached,
                 "artifact_cached": result.artifact_cached,
                 "status": ("deferred" if result.test.tid in deferred_ids
                            else "passed" if result.ok else "failed")}
                for result in results
            ],
        }
        try:
            args.timings_json.parent.mkdir(parents=True, exist_ok=True)
            args.timings_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            harness_errors.append(f"cannot write timing report {args.timings_json}: {exc}")

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
