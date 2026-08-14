#!/usr/bin/env python3
"""scripts/bench.py -- the tests/bench gate.

Compiles each driver under tests/bench/drivers/ through the same toolchain
path tests/run.py uses (run.py is imported, not reimplemented), runs it under
an external wall clock, and reports ns/op against the budgets in
tests/bench/bench_budgets.zen and the rolling baseline in
tests/bench/baseline.json.

WHAT IT MEASURES, honestly: whole-process wall time of a driver that runs the
bench body in a loop, minus the same number for drivers/null.zen (same
staging, same spawn, no loop), divided by the loop count. std has no clock,
so the clock lives here; the subtraction is what keeps process startup out of
the op cost. allocs_op/bytes_op are NOT measured -- that needs compiler
instrumentation that does not exist yet (deferred, deliberately), so they are
reported as unmeasured rather than guessed.

    0   every bench ran and nothing regressed past the hard margins
    1   a bench failed to build or run, or regressed past a hard margin
    2   the harness could not run: no compiler, no C compiler

Budgets have never been measured against real numbers, so they are
INFORMATIONAL on this first pass: over budget warns, over BUDGET_HARD x
budget fails. The baseline is a rolling median of the last BASELINE_KEEP
samples; over BASELINE_WARN x the median warns, over BASELINE_HARD x fails.
`--update-baseline` appends the current run to the samples.

Usage:

    scripts/bench.py                        # everything, via the bootstrapper
    scripts/bench.py --toolchain zen        # against the built ./zen
    scripts/bench.py --update-baseline      # fold this run into baseline.json
    scripts/bench.py --runs 9 --jobs 8
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
TESTS_DIR = REPO_ROOT / "tests"
BENCH_DIR = TESTS_DIR / "bench"
DRIVERS_DIR = BENCH_DIR / "drivers"
BASELINE_PATH = BENCH_DIR / "baseline.json"
BUDGETS_PATH = BENCH_DIR / "bench_budgets.zen"

sys.path.insert(0, str(TESTS_DIR))
import run as runner  # tests/run.py -- staging and toolchain, reused  # noqa: E402

# One row per bench. The name is the budget's name in bench_budgets.zen; the
# driver holds the loop count, parsed out of its `Range(0, N)` below so the
# number lives in one place -- the file that runs it.
BENCHES = ("vec_add", "stored_field_read", "computed_field_read", "fold_stack_array")

# The budgets were written from the design, not from a measurement, so the
# first real numbers get room: past the budget is a warning, past
# BUDGET_HARD times it is a failure -- that is no longer noise, it is a
# different program.
BUDGET_HARD = 10.0
BASELINE_WARN = 1.5
BASELINE_HARD = 4.0
BASELINE_KEEP = 20

ITERS_RE = re.compile(r"Range\(0,\s*(\d+)\)")
BUDGET_RE = re.compile(r'Budget\(name:\s*"([^"]+)",\s*ns_op:\s*(\d+)')


class HarnessError(Exception):
    """The harness cannot do its job. Never a bench result."""


@dataclass
class Bench:
    name: str
    driver: Path
    iters: int
    budget_ns: int | None
    binary: Path | None = None
    ns_op: float | None = None
    wall_ns: int = 0
    problems: list[str] = field(default_factory=list)


def _read_iters(driver: Path) -> int:
    try:
        text = driver.read_text(encoding="utf-8")
    except OSError as exc:
        raise HarnessError(f"{driver}: unreadable ({exc})") from exc
    found = ITERS_RE.findall(text)
    if len(found) != 1:
        raise HarnessError(
            f"{driver}: expected exactly one `Range(0, N)` loop count, found {len(found)}"
        )
    return int(found[0])


def _read_budgets(path: Path) -> dict[str, int]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HarnessError(f"{path}: unreadable ({exc})") from exc
    return {name: int(ns) for name, ns in BUDGET_RE.findall(text)}


def make_toolchain(args: argparse.Namespace) -> runner.Toolchain:
    if args.toolchain == "bootstrap":
        return runner.Toolchain(
            "bootstrap",
            [args.python, "-m", "bootstrap.bootstrap"],
            "bootstrap",
            src_root=REPO_ROOT / "src",
        )
    binary = Path(args.zen)
    if not binary.is_absolute():
        binary = REPO_ROOT / binary
    if not (binary.is_file() and binary.stat().st_mode & 0o111):
        raise HarnessError(f"no executable zen compiler at {binary}. Build one (`make build`).")
    return runner.Toolchain("zen", [str(binary)], "zen", src_root=REPO_ROOT / "src")


def stage_driver(driver: Path, work: Path) -> Path:
    """Same shape as run.py's stage: a self-contained root holding std (the
    prelude) and the program as main.zen, so the compilation root is the
    staging directory and never the filesystem."""
    root = work / "src"
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO_ROOT / "src" / "std", root / "std", dirs_exist_ok=True)
    shutil.copy2(driver, root / "main.zen")
    return root


def build_bench(bench: Bench, tool: runner.Toolchain, work: Path,
                args: argparse.Namespace) -> None:
    """Compile one driver to a binary; problems land on the bench, not stderr."""
    root = stage_driver(bench.driver, work)
    out_c = work / "out.c"
    entry = "main.zen"
    source = root / entry
    emit = runner.run_process(tool.command(source, out_c, root, entry), args.timeout)
    if emit.timed_out or emit.code != 0 or not out_c.is_file():
        bench.problems.append(
            f"the compiler rejected the driver (exit {emit.code})\n"
            + runner.clip(runner.diagnostics(emit))
        )
        return
    binary = work / "prog"
    cc = runner.run_process(
        [args.cc, *shlex.split(args.cc_flags), str(out_c), "-o", str(binary)],
        args.timeout,
    )
    if cc.timed_out or cc.code != 0:
        bench.problems.append(
            f"the C compiler rejected the generated C (exit {cc.code})\n"
            + runner.clip(runner.diagnostics(cc))
        )
        return
    bench.binary = binary


def time_process(argv: list[str], timeout: float) -> int:
    """One wall-clock measurement of a whole process, in nanoseconds."""
    start = time.perf_counter_ns()
    ran = runner.run_process(argv, timeout)
    elapsed = time.perf_counter_ns() - start
    if ran.timed_out or ran.code != 0:
        raise HarnessError(
            f"{argv[0]} exited {ran.code} mid-bench\n"
            + runner.clip(runner.diagnostics(ran))
        )
    return elapsed


def measure(bench: Bench, null_floor: int, runs: int, timeout: float) -> None:
    """min over `runs` process walls, minus the null driver's floor.

    min, not median: the fastest run is the one with the least scheduler and
    neighbour noise in it, which is the number a budget wants. The loop body
    itself is identical on every run -- only the noise varies."""
    assert bench.binary is not None
    time_process([str(bench.binary)], timeout)  # warmup: page cache, not a sample
    best = min(time_process([str(bench.binary)], timeout) for _ in range(runs))
    bench.wall_ns = best
    bench.ns_op = max(best - null_floor, 0) / bench.iters


def load_baseline() -> dict:
    if not BASELINE_PATH.is_file():
        return {}
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HarnessError(f"{BASELINE_PATH}: unreadable ({exc})") from exc


def baseline_median(baseline: dict, name: str) -> float | None:
    samples = baseline.get("benches", {}).get(name, {}).get("samples_ns_op", [])
    if not samples:
        return None
    return statistics.median(samples)


def update_baseline(baseline: dict, benches: list[Bench]) -> None:
    """Rolling: each --update-baseline run appends one sample per bench and
    trims to the last BASELINE_KEEP, so the median follows deliberate drift
    and a slow machine never poisons it permanently -- it ages out."""
    entry = baseline.setdefault("benches", {})
    for bench in benches:
        if bench.ns_op is None:
            continue
        slot = entry.setdefault(bench.name, {"samples_ns_op": []})
        slot["samples_ns_op"] = (slot["samples_ns_op"] + [bench.ns_op])[-BASELINE_KEEP:]
    baseline["version"] = 1
    BASELINE_PATH.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")


def measure_fmt(args: argparse.Namespace) -> float | None:
    """One wall-clock run of the `make fmt` recipe: `zen fmt --check` over the
    tree. None when there is no ./zen -- the row is reported as skipped, not
    failed, because fmt is not what this gate exists to gate."""
    zen = REPO_ROOT / "zen"
    if not (zen.is_file() and zen.stat().st_mode & 0o111):
        return None
    found = subprocess.run(
        ["find", "src", "example", "tests/corpus", "-name", "*.zen",
         "-not", "-path", "tests/corpus/lex/*", "-print0"],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, check=True,
    ).stdout
    files = [f.decode() for f in found.split(b"\0") if f]
    start = time.perf_counter_ns()
    for i in range(0, len(files), 200):  # xargs would batch; so do we
        ran = runner.run_process([str(zen), "fmt", "--check", *files[i:i + 200]],
                                 args.timeout, cwd=REPO_ROOT)
        if ran.code != 0:
            raise HarnessError(
                f"zen fmt --check exited {ran.code} during the fmt bench\n"
                + runner.clip(runner.diagnostics(ran))
            )
    return time.perf_counter_ns() - start


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="scripts/bench.py",
        description="run the tests/bench drivers against budgets and baseline",
    )
    p.add_argument("--toolchain", choices=("bootstrap", "zen"), default="bootstrap",
                   help="which implementation compiles the drivers (default: bootstrap)")
    p.add_argument("--python", default=sys.executable, help="interpreter for the bootstrapper")
    p.add_argument("--zen", default="zen", help="path to the zen binary (--toolchain zen)")
    p.add_argument("--cc", default=os.environ.get("CC", "cc"), help="C compiler")
    p.add_argument("--cc-flags", default=os.environ.get("CFLAGS", "-std=c11 -O2"),
                   help="flags for the C compiler (optimized: benches measure -O2, "
                        "not run.py's -O0 debug build)")
    p.add_argument("--runs", type=int, default=7, help="timed runs per bench (min is kept)")
    p.add_argument("--jobs", "-j", type=int, default=os.cpu_count() or 1,
                   help="parallelism for COMPILES only; timing runs are always "
                        "sequential, because two clocks on one machine measure each other")
    p.add_argument("--timeout", type=float, default=120.0, help="seconds for one compile or run")
    p.add_argument("--update-baseline", action="store_true",
                   help="fold this run into tests/bench/baseline.json")
    p.add_argument("--keep", action="store_true", help="keep the work directory")
    return p.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)

    budgets = _read_budgets(BUDGETS_PATH)
    benches: list[Bench] = []
    try:
        for name in (*BENCHES, "null"):
            driver = DRIVERS_DIR / f"{name}.zen"
            if not driver.is_file():
                raise HarnessError(f"{driver}: missing driver")
            # null has no loop to count; its wall time is the floor, undivided
            iters = 1 if name == "null" else _read_iters(driver)
            benches.append(Bench(name, driver, iters, budgets.get(name)))
        tool = make_toolchain(args)
        if shutil.which(args.cc) is None:
            raise HarnessError(f"no C compiler on PATH: {args.cc!r} (pass --cc)")
        baseline = load_baseline()
    except HarnessError as exc:
        print(f"bench.py: {exc}", file=sys.stderr)
        return 2

    workroot = Path(tempfile.mkdtemp(prefix="zen-bench."))
    try:
        print(f"bench.py: {len(BENCHES)} bench(es) via {tool.name} "
              f"[{shlex.join(tool.emit_argv)}]")
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            list(pool.map(
                lambda b: build_bench(b, tool, workroot / b.name, args), benches))
    except HarnessError as exc:
        print(f"bench.py: {exc}", file=sys.stderr)
        if not args.keep:
            shutil.rmtree(workroot, ignore_errors=True)
        return 2

    null = next(b for b in benches if b.name == "null")
    timed = [b for b in benches if b.name != "null"]

    failed = False
    try:
        # Sequential from here on: a wall clock measures everything on the
        # machine, so the machine must be doing one thing at a time.
        if null.binary is not None:
            time_process([str(null.binary)], args.timeout)
            null_floor = min(time_process([str(null.binary)], args.timeout)
                             for _ in range(args.runs))
            null.wall_ns = null_floor
            for bench in timed:
                if bench.binary is not None:
                    measure(bench, null_floor, args.runs, args.timeout)
    except HarnessError as exc:
        print(f"bench.py: {exc}", file=sys.stderr)
        if not args.keep:
            shutil.rmtree(workroot, ignore_errors=True)
        return 2
    finally:
        if args.keep:
            print(f"bench.py: work directory kept at {workroot}")
        else:
            shutil.rmtree(workroot, ignore_errors=True)

    print(f"\n{'bench':<22} {'ns/op':>10} {'budget':>8} {'x budget':>9} "
          f"{'baseline':>9} {'x base':>7}  verdict")
    for bench in benches:
        if bench.name == "null":
            print(f"{'null (process floor)':<22} {'--':>10} {'--':>8} {'--':>9} "
                  f"{'--':>9} {'--':>7}  {null.wall_ns / 1e6:.1f} ms wall")
            continue
        if bench.ns_op is None:
            failed = True
            print(f"{bench.name:<22} {'--':>10} {'--':>8} {'--':>9} "
                  f"{'--':>9} {'--':>7}  FAIL (did not run)")
            for problem in bench.problems:
                print(f"    {problem}")
            continue

        verdict = "ok"
        x_budget = bench.ns_op / bench.budget_ns if bench.budget_ns else None
        if x_budget is not None:
            if x_budget > BUDGET_HARD:
                verdict = f"FAIL (>{BUDGET_HARD:g}x budget)"
                failed = True
            elif x_budget > 1.0:
                # budgets were written from the design and have never met a
                # measurement; over is expected, absurd over is not
                verdict = "warn (over budget, informational)"
        median = baseline_median(baseline, bench.name)
        x_base = bench.ns_op / median if median else None
        if x_base is not None and verdict == "ok":
            if x_base > BASELINE_HARD:
                verdict = f"FAIL (>{BASELINE_HARD:g}x baseline median)"
                failed = True
            elif x_base > BASELINE_WARN:
                verdict = f"warn (>{BASELINE_WARN:g}x baseline median)"

        print(f"{bench.name:<22} {bench.ns_op:>10.1f} "
              f"{bench.budget_ns if bench.budget_ns is not None else '--':>8} "
              f"{f'{x_budget:.1f}x' if x_budget is not None else '--':>9} "
              f"{f'{median:.1f}' if median is not None else '--':>9} "
              f"{f'{x_base:.2f}x' if x_base is not None else '--':>7}  {verdict}")
        print(f"    allocs_op/bytes_op: unmeasured (needs compiler "
              f"instrumentation, deferred)")

    # the fmt row: one run of the `make fmt` recipe, reported beside the rest
    try:
        fmt_ns = measure_fmt(args)
    except HarnessError as exc:
        print(f"bench.py: {exc}", file=sys.stderr)
        return 2
    if fmt_ns is None:
        print(f"\n{'fmt_tree':<22} skipped (no ./zen; `make build` first)")
    else:
        print(f"\n{'fmt_tree':<22} {fmt_ns / 1e6:>10.1f} ms wall, one run "
              f"of the `make fmt` recipe (informational; not baselined)")

    if args.update_baseline:
        update_baseline(baseline, timed)
        print(f"bench.py: baseline updated at {BASELINE_PATH} "
              f"(rolling median of last {BASELINE_KEEP})")
    elif not baseline:
        print(f"bench.py: no baseline at {BASELINE_PATH} yet; "
              f"--update-baseline writes one")

    if failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
