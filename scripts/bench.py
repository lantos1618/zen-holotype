#!/usr/bin/env python3
"""scripts/bench.py -- the tests/bench gate.

Compiles each driver under tests/bench/drivers/ through the same toolchain
path tests/run.py uses (run.py is imported, not reimplemented), runs it under
an external wall clock, and reports ns/op against the budgets in
tests/bench/bench_budgets.zen and the rolling baseline in
tests/bench/baseline.json.

WHAT ns_op MEASURES, honestly: whole-process wall time of a driver that runs
the bench body in a loop, minus the same number for drivers/null.zen (same
staging, same spawn, no loop), divided by the loop count. std has no clock,
so the clock lives here; the subtraction is what keeps process startup out of
the op cost.

WHAT allocs_op/bytes_op MEASURE, and where the measurement stands. Every
driver is linked against an interposer (ALLOC_SHIM below) through
`ld --wrap`, so each libc malloc/calloc/realloc the program makes is counted
along with the bytes it asked for. Each driver is then compiled TWICE, at its
declared loop count and at twice it, and the per-op figure is the SLOPE:

    allocs_op = (allocs at 2N - allocs at N) / N

and not a subtraction of drivers/null.zen's floor. A slope cancels every
fixed cost of THAT driver exactly -- its own prelude, its own arena setup,
the argv rows -- where a shared floor only cancels the costs two drivers
happen to share, and leaves a residue that makes `allocs_op: 0` unfalsifiable
the moment a driver grows one setup line the null driver does not have.

THE BOUNDARY IS LIBC, NOT THE ZEN ALLOCATOR, and the difference matters when
you read a number. `env.mem.alloc()` is an arena: it bump-allocates out of
64 KiB pages and calls malloc only when a page runs out, so a million Zen
allocations show up here as a few hundred. A measured figure is therefore a
LOWER BOUND on Zen allocator calls, and the budgets are gated as CEILINGS:
over budget fails, under budget is not a claim that the design's count was
met. The one budget this measures exactly is zero -- an operation that
performs no heap allocation has a slope of exactly 0, on every machine, and
that is the number TESTING.md and the fold driver actually lean on.

    0   every bench ran and nothing regressed past the hard margins
    1   a bench failed to build or run, or regressed past a hard margin
    2   the harness could not run: no compiler, no C compiler, no `ld --wrap`

ns_op budgets have never been measured against real numbers, so they stay
INFORMATIONAL: over budget warns, over BUDGET_HARD x budget fails. The
baseline is a rolling median of the last BASELINE_KEEP samples; over
BASELINE_WARN x the median warns, over BASELINE_HARD x fails.
`--update-baseline` appends the current run to the samples. allocs_op and
bytes_op get no such margin: they are the same integers on every machine, so
over budget is a failure and not a weather report.

Usage:

    scripts/bench.py                        # everything, via ./zen
    scripts/bench.py --allocs-only          # the deterministic half; no clock
    scripts/bench.py --update-baseline      # fold this run into baseline.json
    scripts/bench.py --runs 9 --jobs 8

`--allocs-only` is what `make test` runs. The wall-clock half stays out of
`make test` on purpose (a gate that reddens on a loaded machine teaches
people to read past red); the allocation half has no such excuse, because it
is not a measurement of the machine.
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
BUDGET_RE = re.compile(
    r'Budget\(name:\s*"([^"]+)",\s*ns_op:\s*(\d+),'
    r'\s*allocs_op:\s*(\d+),\s*bytes_op:\s*(\d+)\s*\)'
)

# The interposer every driver is linked against. `ld --wrap=malloc` rewrites
# the program's undefined reference to `malloc` into `__wrap_malloc`, so this
# counts the driver's own allocations and NOT libc's internal ones -- stdio's
# buffer never reaches here. `free` is deliberately not wrapped: the pointers
# handed out are __real_malloc's, so the real free is already the right one,
# and one fewer wrapped symbol is one fewer way to link this wrong.
ALLOC_SHIM = r"""
#include <stdio.h>
#include <stdlib.h>

void *__real_malloc(size_t);
void *__real_calloc(size_t, size_t);
void *__real_realloc(void *, size_t);

static unsigned long long zb_allocs, zb_bytes;

void *__wrap_malloc(size_t n) {
    zb_allocs++; zb_bytes += n; return __real_malloc(n);
}
void *__wrap_calloc(size_t a, size_t b) {
    zb_allocs++; zb_bytes += a * b; return __real_calloc(a, b);
}
void *__wrap_realloc(void *p, size_t n) {
    zb_allocs++; zb_bytes += n; return __real_realloc(p, n);
}

static void zb_dump(void) {
    const char *path = getenv("ZEN_ALLOC_OUT");
    FILE *f = path ? fopen(path, "w") : NULL;
    if (!f) return;
    fprintf(f, "%llu %llu\n", zb_allocs, zb_bytes);
    fclose(f);
}

__attribute__((constructor)) static void zb_arm(void) { atexit(zb_dump); }
"""

WRAP_FLAGS = ["-Wl,--wrap=malloc", "-Wl,--wrap=calloc", "-Wl,--wrap=realloc"]

# The second compile of each driver, whose allocation count minus the first
# one's is the slope. Two, and not ten: the quantity is a straight line
# through the origin plus a constant, so two points determine it exactly.
SLOPE_FACTOR = 2


class HarnessError(Exception):
    """The harness cannot do its job. Never a bench result."""


@dataclass
class Budget:
    ns_op: int
    allocs_op: int
    bytes_op: int


@dataclass
class Bench:
    name: str
    driver: Path
    iters: int
    budget: Budget | None
    binary: Path | None = None
    binary_2x: Path | None = None
    ns_op: float | None = None
    allocs_op: float | None = None
    bytes_op: float | None = None
    wall_ns: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def budget_ns(self) -> int | None:
        return self.budget.ns_op if self.budget else None


def _read_iters(driver: Path) -> int:
    return _iters_of(_read(driver), driver)


def _read(driver: Path) -> str:
    try:
        return driver.read_text(encoding="utf-8")
    except OSError as exc:
        raise HarnessError(f"{driver}: unreadable ({exc})") from exc


def _iters_of(text: str, driver: Path) -> int:
    found = ITERS_RE.findall(text)
    if len(found) != 1:
        raise HarnessError(
            f"{driver}: expected exactly one `Range(0, N)` loop count, found {len(found)}"
        )
    return int(found[0])


def _with_iters(text: str, driver: Path, iters: int) -> str:
    """The driver with its one loop count replaced -- the second point of the
    slope. The same regex that reads the number writes it, so a driver whose
    loop stops matching fails in `_iters_of` before it can silently produce a
    second binary identical to the first."""
    out, n = ITERS_RE.subn(f"Range(0, {iters})", text)
    if n != 1:
        raise HarnessError(f"{driver}: rewrote {n} loop counts, expected 1")
    return out


def _read_budgets(path: Path) -> dict[str, Budget]:
    text = _read(path)
    found = {name: Budget(int(ns), int(allocs), int(byts))
             for name, ns, allocs, byts in BUDGET_RE.findall(text)}
    # A budget file that stopped matching yields {}, every budget reads as
    # None, and every verdict comes out "ok" -- the gate would pass because it
    # found nothing to check. Missing names are a harness error, not a pass.
    missing = [name for name in BENCHES if name not in found]
    if missing:
        raise HarnessError(
            f"{path}: no budget row parsed for {', '.join(missing)}."
            " The file changed shape and this gate just stopped checking --"
            " fix the parse, do not drop the bench."
        )
    return found


def make_toolchain(args: argparse.Namespace) -> runner.Toolchain:
    binary = Path(args.zen)
    if not binary.is_absolute():
        binary = REPO_ROOT / binary
    if not (binary.is_file() and binary.stat().st_mode & 0o111):
        raise HarnessError(f"no executable zen compiler at {binary}. Build one (`make build`).")
    return runner.Toolchain("zen", [str(binary)], src_root=REPO_ROOT / "src")


def stage_driver(driver: Path, work: Path, source: str) -> Path:
    """Same shape as run.py's stage: a self-contained root holding std (the
    prelude) and the program as main.zen, so the compilation root is the
    staging directory and never the filesystem."""
    root = work / "src"
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO_ROOT / "src" / "std", root / "std", dirs_exist_ok=True)
    (root / "main.zen").write_text(source, encoding="utf-8")
    return root


def compile_driver(bench: Bench, source: str, tool: runner.Toolchain, work: Path,
                   shim: Path, args: argparse.Namespace) -> Path | None:
    """One driver text to one binary; problems land on the bench, not stderr."""
    root = stage_driver(bench.driver, work, source)
    out_c = work / "out.c"
    entry = "main.zen"
    emit = runner.run_process(tool.command(root / entry, out_c, root, entry), args.timeout)
    if emit.timed_out or emit.code != 0 or not out_c.is_file():
        bench.problems.append(
            f"the compiler rejected the driver (exit {emit.code})\n"
            + runner.clip(runner.diagnostics(emit))
        )
        return None
    binary = work / "prog"
    cc = runner.run_process(
        [args.cc, *shlex.split(args.cc_flags), str(out_c), str(shim),
         "-o", str(binary), *WRAP_FLAGS],
        args.timeout,
    )
    if cc.timed_out or cc.code != 0:
        bench.problems.append(
            f"the C compiler rejected the generated C (exit {cc.code})\n"
            + runner.clip(runner.diagnostics(cc))
        )
        return None
    return binary


def build_bench(bench: Bench, tool: runner.Toolchain, work: Path, shim: Path,
                args: argparse.Namespace) -> None:
    """Both points of the slope: the driver at its own loop count, and at
    SLOPE_FACTOR times it. null.zen has no loop, so it gets one build."""
    text = _read(bench.driver)
    bench.binary = compile_driver(bench, text, tool, work / "1x", shim, args)
    if bench.name == "null" or bench.binary is None:
        return
    bench.binary_2x = compile_driver(
        bench, _with_iters(text, bench.driver, bench.iters * SLOPE_FACTOR),
        tool, work / f"{SLOPE_FACTOR}x", shim, args)


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


def count_allocs(binary: Path, timeout: float) -> tuple[int, int]:
    """(allocations, bytes) for one whole run of `binary`.

    Zero is a legitimate answer here -- at -O2 three of the four drivers
    allocate nothing at all -- which is exactly why a linker that ignored
    `--wrap` could not be caught at this level: silence and success read the
    same. `verify_wrap` below settles that question separately, before any
    driver is measured.
    """
    # Removed first and required after: a leftover file from the previous
    # binary would otherwise be read as this one's answer.
    report = binary.parent / "allocs.txt"
    report.unlink(missing_ok=True)
    os.environ["ZEN_ALLOC_OUT"] = str(report)
    try:
        ran = runner.run_process([str(binary)], timeout)
    finally:
        os.environ.pop("ZEN_ALLOC_OUT", None)
    if ran.timed_out or ran.code != 0:
        raise HarnessError(
            f"{binary} exited {ran.code} while its allocations were counted\n"
            + runner.clip(runner.diagnostics(ran))
        )
    text = report.read_text(encoding="utf-8").split() if report.is_file() else []
    if len(text) != 2:
        raise HarnessError(
            f"{binary}: the allocation interposer wrote nothing readable."
            " It is linked with `ld --wrap`; a toolchain without it cannot"
            " run this gate."
        )
    return int(text[0]), int(text[1])


PROBE = r"""
#include <stdlib.h>
int main(void) {
    void *p = malloc(PROBE_BYTES);
    if (!p) return 1;
    free(p);
    return 0;
}
"""


def verify_wrap(shim: Path, work: Path, args: argparse.Namespace) -> None:
    """A known allocation must be seen, before any driver is believed.

    Every measurement below is a count that can legitimately be zero, so an
    unwrapped link reports a tree of perfectly allocation-free benches and
    the gate passes on nothing at all. This program allocates PROBE_BYTES
    exactly once; if the interposer does not say so, the toolchain cannot run
    this gate and that is a harness error, never a verdict.
    """
    want = 4099  # nothing else would ask for this, so the number identifies it
    work.mkdir(parents=True, exist_ok=True)
    probe_c = work / "probe.c"
    probe_c.write_text(PROBE, encoding="utf-8")
    binary = work / "probe"
    built = runner.run_process(
        [args.cc, *shlex.split(args.cc_flags), f"-DPROBE_BYTES={want}",
         str(probe_c), str(shim), "-o", str(binary), *WRAP_FLAGS],
        args.timeout,
    )
    if built.timed_out or built.code != 0:
        raise HarnessError(
            "the C toolchain will not link `ld --wrap=malloc`, which is how"
            " allocations are counted here\n" + runner.clip(runner.diagnostics(built))
        )
    allocs, byts = count_allocs(binary, args.timeout)
    if (allocs, byts) != (1, want):
        raise HarnessError(
            f"the allocation interposer saw {allocs} allocation(s) of {byts}"
            f" byte(s) where the probe makes exactly 1 of {want}. `--wrap`"
            " linked but did not take effect, and every bench below would"
            " read as allocation-free."
        )


def measure_allocs(bench: Bench, timeout: float) -> None:
    """The slope between the two builds: every fixed cost of this driver
    appears in both runs and subtracts out exactly."""
    assert bench.binary is not None and bench.binary_2x is not None
    allocs_1x, bytes_1x = count_allocs(bench.binary, timeout)
    allocs_2x, bytes_2x = count_allocs(bench.binary_2x, timeout)
    span = bench.iters * (SLOPE_FACTOR - 1)
    bench.allocs_op = (allocs_2x - allocs_1x) / span
    bench.bytes_op = (bytes_2x - bytes_1x) / span


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
    p.add_argument("--zen", default="zen", help="path to the zen binary")
    p.add_argument("--cc", default=os.environ.get("CC", "cc"), help="C compiler")
    p.add_argument("--cc-flags", default=os.environ.get("CFLAGS", "-std=c11 -O2"),
                   help="flags for the C compiler (optimized: benches measure -O2, "
                        "not run.py's -O0 debug build)")
    p.add_argument("--runs", type=int, default=7, help="timed runs per bench (min is kept)")
    p.add_argument("--jobs", "-j", type=int, default=os.cpu_count() or 1,
                   help="parallelism for COMPILES only; timing runs are always "
                        "sequential, because two clocks on one machine measure each other")
    p.add_argument("--timeout", type=float, default=120.0, help="seconds for one compile or run")
    p.add_argument("--allocs-only", action="store_true",
                   help="the deterministic half: allocs_op and bytes_op against "
                        "their budgets, no wall clock. what `make test` runs")
    p.add_argument("--update-baseline", action="store_true",
                   help="fold this run into tests/bench/baseline.json")
    p.add_argument("--keep", action="store_true", help="keep the work directory")
    return p.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)

    benches: list[Bench] = []
    try:
        budgets = _read_budgets(BUDGETS_PATH)
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
        half = "allocations only" if args.allocs_only else "allocations and wall clock"
        print(f"bench.py: {len(BENCHES)} bench(es) via {tool.name} "
              f"[{shlex.join(tool.emit_argv)}], {half}")
        shim = workroot / "alloc_shim.c"
        shim.write_text(ALLOC_SHIM, encoding="utf-8")
        verify_wrap(shim, workroot / "probe", args)
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            list(pool.map(
                lambda b: build_bench(b, tool, workroot / b.name, shim, args), benches))
    except HarnessError as exc:
        print(f"bench.py: {exc}", file=sys.stderr)
        if not args.keep:
            shutil.rmtree(workroot, ignore_errors=True)
        return 2

    null = next(b for b in benches if b.name == "null")
    timed = [b for b in benches if b.name != "null"]

    failed = False
    try:
        # Allocations first: they are integers, so nothing about the order or
        # the load on the machine can change them.
        for bench in timed:
            if bench.binary is not None and bench.binary_2x is not None:
                measure_allocs(bench, args.timeout)
        # Sequential from here on: a wall clock measures everything on the
        # machine, so the machine must be doing one thing at a time.
        if null.binary is not None and not args.allocs_only:
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

    # The deterministic table. Over budget is a failure here and not a
    # warning: these are the same integers on every machine, which is the
    # whole reason bench_budgets.zen says exceeding them fails the build.
    print(f"\n{'bench':<22} {'allocs/op':>12} {'budget':>8} "
          f"{'bytes/op':>12} {'budget':>8}  verdict")
    for bench in timed:
        if bench.allocs_op is None or bench.bytes_op is None or bench.budget is None:
            failed = True
            print(f"{bench.name:<22} {'--':>12} {'--':>8} {'--':>12} {'--':>8}  "
                  f"FAIL (did not run)")
            for problem in bench.problems:
                print(f"    {problem}")
            continue
        over = []
        if bench.allocs_op > bench.budget.allocs_op:
            over.append(f"allocs_op {bench.allocs_op:g} > {bench.budget.allocs_op}")
        if bench.bytes_op > bench.budget.bytes_op:
            over.append(f"bytes_op {bench.bytes_op:g} > {bench.budget.bytes_op}")
        # A BUDGET IS A CEILING, AND A CEILING PASSES A MEASUREMENT OF
        # NOTHING. Every check above is `measured > budget`, so a driver
        # whose work stopped reaching the allocator at all -- the loop
        # elided, the binary not actually re-linked at 2N, `--wrap=malloc`
        # silently not applied -- reads as 0 and prints `ok`. The three
        # benches budgeted at zero are saved from that by an accident in
        # the drivers rather than by anything here: their bodies return
        # `Ok(1)` when the accumulator is zero, so an elided loop exits
        # non-zero and `count_allocs` raises. `vec_add` has no such escape
        # -- it returns `Ok(0)` unconditionally -- and it is the one bench
        # whose whole subject IS that a Vec reaches malloc.
        #
        # So a NON-ZERO budget carries a floor with it: it is this file
        # asserting the operation allocates, and measuring that it does not
        # is a broken harness, not a fast one. No new number to maintain --
        # the floor is read off the budget already in bench_budgets.zen.
        if bench.budget.allocs_op > 0 and bench.allocs_op == 0:
            over.append(
                f"allocs_op 0, and the budget says this operation allocates"
                f" ({bench.budget.allocs_op}). A ceiling passes a measurement"
                f" of nothing: the loop was elided, the driver was not rebuilt"
                f" at 2N, or --wrap=malloc did not apply"
            )
        if over:
            failed = True
        print(f"{bench.name:<22} {bench.allocs_op:>12.6g} "
              f"{bench.budget.allocs_op:>8} {bench.bytes_op:>12.6g} "
              f"{bench.budget.bytes_op:>8}  "
              f"{'FAIL (' + '; '.join(over) + ')' if over else 'ok'}")
    print("  measured at the libc boundary as a slope between the driver at N"
          " and at 2N\n  iterations, so it is a LOWER BOUND on Zen allocator"
          " calls (an arena serves\n  many out of one page) and is checked as a"
          " ceiling. Exact only at zero.")

    if args.allocs_only:
        if failed:
            return 1
        return 0

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
