#!/usr/bin/env python3
"""Classify the observable Zen-to-C pipeline for maintained fixtures.

Each fixture receives exactly one outcome:

    ZEN_REJECTED  Zen rejected the program before producing C.
    CC_REJECTED   Zen accepted it, but the C compiler rejected the output.
    CC_WARNING    C compiled it while reporting a warning.
    RAN_OK        The compiled program exited zero.
    NONZERO_EXIT  The compiled program exited nonzero.

CC_REJECTED is always a gate failure. A manifest may record the other expected
outcomes, but it cannot turn accepted Zen that is invalid C into a passing test.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
FIXTURES = HERE / "fixtures"

ZEN_REJECTED = "ZEN_REJECTED"
CC_REJECTED = "CC_REJECTED"
CC_WARNING = "CC_WARNING"
RAN_OK = "RAN_OK"
NONZERO_EXIT = "NONZERO_EXIT"
CLASSES = {ZEN_REJECTED, CC_REJECTED, CC_WARNING, RAN_OK, NONZERO_EXIT}

# Warnings emitted only because the generated translation unit carries shared
# helpers do not describe the fixture's semantics. All other common warnings
# remain visible and classify the fixture as CC_WARNING.
DEFAULT_CC_FLAGS = (
    "-std=c11 -O0 -g -Wall -Wextra -Wpedantic "
    "-Wno-unused-function -Wno-unused-variable"
)
WARNING = re.compile(r"(^|:)\s*warning:", re.MULTILINE)


class HarnessError(Exception):
    """The harness could not make a semantic observation."""


@dataclass(frozen=True)
class Fixture:
    name: str
    source: Path
    expect: str
    exit_code: int | None
    contains: str | None


@dataclass(frozen=True)
class Outcome:
    kind: str
    detail: str = ""
    exit_code: int | None = None


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="classify maintained Zen programs across the generated-C boundary"
    )
    parser.add_argument("--zen", default=str(REPO_ROOT / "zen"))
    parser.add_argument("--cc", default=os.environ.get("CC", "cc"))
    parser.add_argument("--cc-flags", default=DEFAULT_CC_FLAGS)
    parser.add_argument("--manifest", default=str(HERE / "manifest.json"))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--run-timeout", type=float, default=20.0)
    parser.add_argument("--keep", action="store_true")
    return parser.parse_args(argv)


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def load_manifest(path: Path) -> list[Fixture]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError(f"cannot read manifest {path}: {exc}") from exc

    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise HarnessError(f"{path}: expected manifest version 1")
    rows = raw.get("fixtures")
    if not isinstance(rows, list) or not rows:
        raise HarnessError(f"{path}: zero fixtures is not a differential test")

    fixtures: list[Fixture] = []
    names: set[str] = set()
    sources: set[Path] = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise HarnessError(f"{path}: fixture {index} is not an object")
        name = row.get("name")
        source_name = row.get("source")
        expect = row.get("expect")
        if not isinstance(name, str) or not name:
            raise HarnessError(f"{path}: fixture {index} has no name")
        if name in names:
            raise HarnessError(f"{path}: duplicate fixture name {name!r}")
        if not isinstance(source_name, str):
            raise HarnessError(f"{path}: {name} has no source")
        source = (HERE / source_name).resolve()
        if not _inside(source, FIXTURES.resolve()) or source.suffix != ".zen":
            raise HarnessError(f"{path}: {name} source must be a .zen under fixtures/")
        if not source.is_file():
            raise HarnessError(f"{path}: {name} source does not exist: {source}")
        if source in sources:
            raise HarnessError(f"{path}: source listed twice: {source}")
        if expect not in CLASSES:
            raise HarnessError(f"{path}: {name} has unknown class {expect!r}")

        exit_code = row.get("exit")
        if exit_code is not None and not isinstance(exit_code, int):
            raise HarnessError(f"{path}: {name} exit must be an integer")
        contains = row.get("contains")
        if contains is not None and (not isinstance(contains, str) or not contains):
            raise HarnessError(f"{path}: {name} contains must be a nonempty string")

        names.add(name)
        sources.add(source)
        fixtures.append(Fixture(name, source, expect, exit_code, contains))

    unlisted = set(FIXTURES.glob("*.zen")) - sources
    if unlisted:
        names = ", ".join(sorted(p.name for p in unlisted))
        raise HarnessError(f"{path}: unlisted fixture source(s): {names}")

    # These probes keep both sides of the boundary live. CC_REJECTED is absent
    # by design because the invariant below makes it impossible to bless.
    required = {ZEN_REJECTED, CC_WARNING, RAN_OK, NONZERO_EXIT}
    missing = required - {fixture.expect for fixture in fixtures}
    if missing:
        raise HarnessError(
            f"{path}: non-vacuous manifest needs expected class(es): "
            + ", ".join(sorted(missing))
        )
    return fixtures


def run(argv: list[str], timeout: float, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise HarnessError(f"timed out after {timeout:g}s: {shlex.join(argv)}") from exc
    except (FileNotFoundError, PermissionError) as exc:
        raise HarnessError(f"cannot execute {argv[0]!r}: {exc}") from exc


def diagnostics(proc: subprocess.CompletedProcess[str]) -> str:
    return (proc.stdout + proc.stderr).strip()


def stage(fixture: Fixture, root: Path) -> None:
    shutil.copy2(fixture.source, root / "main.zen")
    std = REPO_ROOT / "src" / "std"
    if not std.is_dir():
        raise HarnessError(f"standard library not found at {std}")
    # Compiler implementation sublayers are not part of a user program's
    # prelude. Excluding them keeps a fixture coupled only to language std.
    shutil.copytree(
        std,
        root / "std",
        ignore=shutil.ignore_patterns("lex", "parse", "ast"),
    )


def classify(
    fixture: Fixture,
    work: Path,
    zen: str,
    cc: str,
    cc_flags: list[str],
    timeout: float,
    run_timeout: float,
) -> Outcome:
    root = work / "src"
    root.mkdir()
    stage(fixture, root)
    out_c = work / "out.c"
    emit = run(
        [zen, "build", str(root), "--entry", "main.zen", "--emit-c", "-o", str(out_c)],
        timeout,
    )
    if emit.returncode < 0:
        raise HarnessError(f"{fixture.name}: Zen died on signal {-emit.returncode}")
    if emit.returncode != 0:
        return Outcome(ZEN_REJECTED, diagnostics(emit), emit.returncode)
    if not out_c.is_file():
        raise HarnessError(f"{fixture.name}: Zen exited zero without producing C")

    binary = work / "program"
    compiled = run([cc, *cc_flags, str(out_c), "-o", str(binary)], timeout)
    c_detail = diagnostics(compiled)
    if compiled.returncode < 0:
        raise HarnessError(f"{fixture.name}: C compiler died on signal {-compiled.returncode}")
    if compiled.returncode != 0:
        return Outcome(CC_REJECTED, c_detail, compiled.returncode)
    if WARNING.search(c_detail):
        return Outcome(CC_WARNING, c_detail, 0)

    program = run([str(binary)], run_timeout, cwd=work)
    if program.returncode == 0:
        return Outcome(RAN_OK, diagnostics(program), 0)
    return Outcome(NONZERO_EXIT, diagnostics(program), program.returncode)


def clip(text: str, limit: int = 1200) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... output clipped ..."


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    try:
        fixtures = load_manifest(Path(args.manifest).resolve())
        zen = str(Path(args.zen).resolve()) if os.sep in args.zen else args.zen
        cc_flags = shlex.split(args.cc_flags)
        if not cc_flags:
            raise HarnessError("--cc-flags must not be empty")

        kept: Path | None = None
        if args.keep:
            kept = Path(tempfile.mkdtemp(prefix="zen-differential."))
            workroot_context = None
            workroot = kept
        else:
            workroot_context = tempfile.TemporaryDirectory(prefix="zen-differential.")
            workroot = Path(workroot_context.name)

        failures: list[str] = []
        outcomes: list[tuple[Fixture, Outcome]] = []
        try:
            for fixture in fixtures:
                work = workroot / fixture.name
                work.mkdir()
                outcome = classify(
                    fixture,
                    work,
                    zen,
                    args.cc,
                    cc_flags,
                    args.timeout,
                    args.run_timeout,
                )
                outcomes.append((fixture, outcome))
                print(f"{outcome.kind:<12} {fixture.name}")
                if outcome.kind != fixture.expect:
                    failures.append(
                        f"{fixture.name}: classified {outcome.kind}, expected {fixture.expect}"
                    )
                if fixture.exit_code is not None and outcome.exit_code != fixture.exit_code:
                    failures.append(
                        f"{fixture.name}: exit {outcome.exit_code}, expected {fixture.exit_code}"
                    )
                if fixture.contains and fixture.contains not in outcome.detail:
                    failures.append(
                        f"{fixture.name}: output does not contain {fixture.contains!r}"
                    )
        finally:
            if workroot_context is not None:
                workroot_context.cleanup()

        rejected_c = [fixture.name for fixture, outcome in outcomes if outcome.kind == CC_REJECTED]
        if rejected_c:
            failures.append(
                "accepted Zen must compile as C; rejected fixture(s): " + ", ".join(rejected_c)
            )

        if failures:
            for failure in failures:
                print(f"FAIL {failure}", file=sys.stderr)
            for fixture, outcome in outcomes:
                if outcome.kind != fixture.expect or outcome.kind == CC_REJECTED:
                    detail = clip(outcome.detail)
                    if detail:
                        print(f"\n[{fixture.name}]\n{detail}", file=sys.stderr)
            if kept:
                print(f"differential: work kept at {kept}", file=sys.stderr)
            return 1

        print(
            f"differential: {len(outcomes)} fixture(s), "
            "accepted-to-C-rejected = 0"
        )
        if kept:
            print(f"differential: work kept at {kept}")
        return 0
    except HarnessError as exc:
        print(f"differential: cannot run: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
