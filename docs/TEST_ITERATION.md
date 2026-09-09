# Test iteration

`tests/run.py` prepares the compiler source import graph once per invocation,
then shares it across workers. Every test still receives its own copied source
tree and runs the Zen compiler, links, and executes the program. Test results
are never cached; optional C object caching is described below.

Every compiler invocation explicitly selects `--std` with the staged source
root. This keeps the test's copied library authoritative even when the selected
compiler has another `src/std` beside it or the shell sets `ZEN_STD`. Choosing a
different `--zen` selects the compiler executable; it does not select a different
library for the test.

The runner regression stages a library-only probe module and requires emission
to resolve it. Its negative control removes `--std` and requires the module to
be unresolved through the library beside the compiler. This checks the behavior
behind library selection, not just the presence of a command-line flag.

A focused batch on 2026-09-06 used the existing `./zen`, four workers, and both
`corpus/std/*` and `must-fail/sema/*` (288 tests):

| Runner | Wall time | Result |
| --- | ---: | --- |
| Before shared import discovery | 14.22 s | 288 passed |
| Shared discovery, timings, and source freshness guard | 10.49 s | 288 passed |
| Same selection, shard 1/2 | 4.80 s | 144 passed |

The complete focused batch took about 26% less wall time (1.36× faster). These
are local single-run measurements, not promises across machines or workloads.
An earlier shared-discovery run took 9.82 s. Profiling 20 original staging
operations attributed 49% of staging time to repeated import scans and 34% to
file copies, so discovery was the first useful target. Native process support
is used by only three current process tests; compiling it per test was not the
main bottleneck and remains unchanged.

## Run the relevant tests after a batch of edits

```sh
python3 tests/run.py --zen ./zen --jobs 4 --filter 'corpus/std/*' --timings
python3 tests/run.py --zen ./zen --jobs 4 --filter 'must-fail/sema/*' --timings 20
```

`--timings` reports the ten slowest executed tests; an optional positive integer
changes that count. Each duration includes staging, compilation, and execution
within its worker, excluding time queued behind another test. Durations overlap
when workers run concurrently, so their sum is not the batch's wall time.

Use `--timings-json build/test-timings.json` for all test IDs, durations, and
`passed`/`failed`/`deferred` verdicts. The versioned report also records the
worker count, filters, shard, batch duration, harness errors, and uncollected
files. Parent directories are created automatically. The batch duration starts
after discovery and toolchain preparation and includes test-directory cleanup;
external wall-clock measurements also include startup. The command's exit code
is authoritative; a report write error or source change is a harness failure.

## Cache expensive C compilation

```sh
python3 tests/run.py --jobs 4 --filter 'corpus/gen_zen/*' --cc-cache ccache --timings
```

The heavy compiler-embedding tests generate approximately 8.9 MB of C each.
Phase profiling of a representative test attributed about 8.0 s to C compilation
and linking, 3.3 s to Zen emission, and 0.09 s to source staging under the measured
load. C compilation is the useful cache boundary for these tests.

A comparison on 2026-09-06 ran the same 17 existing `corpus/gen_zen` test IDs,
the same `./zen`, unchanged source files, and four workers:

| Native compilation | Wall time | Result |
| --- | ---: | --- |
| Original uncached compile and link | 32.649 s | 17 passed |
| Warm ccache objects, fresh link and execution | 11.790 s | 17 passed |

That batch was **2.77× faster**, taking about **64% less wall time**. Both warm
runs hit all 17 cached objects; the isolated cache recorded 17 initial misses
and 34 subsequent direct hits. These local measurements do not imply equal
speedups for tiny tests or cold caches. A new test added during this work was
excluded from both measured selections to keep them identical.

`--cc-cache` names one executable, normally `ccache`; empty or omitted retains
the original uncached compile-and-link command. Direct runner calls opt in;
`make test` and `make verify` pass the detected `CACHE` executable and use
`TEST_J` workers (defaulting to `J`). Set `CACHE=` to disable caching. The
aggregate gate always runs the full suite; development filters do not apply. Compilation
is split into `ccache cc ... -c` and a fresh link so ccache receives a cacheable
operation. Every invocation still emits Zen-generated C, links native support,
runs the program, and compares stdout, stderr, and exit status. Failed emission,
compilation, linking, and execution retain their existing failure behavior.
Headers, compiler flags, generated C, and tool identity remain ccache inputs;
no test verdict or final executable is reused.

Each test ID has a locked stable directory under `build/test-native`, configurable
with `--cc-work-dir`. This preserves debug-path cache hits without disabling
ccache's directory checks or changing the working directory that relative
compiler flags use. The freshly generated C is copied there for compilation,
then the object is copied back into the invocation's private test directory.
Concurrent runs of the same test serialize that brief native compilation step;
compiler children retain the lock if their parent dies. Linking and execution
use private paths. A compiler that exits zero without creating an object is a
harness error, so a stranded old object cannot turn a broken compile green.

Generated C using quoted includes, `__FILE__`, or `__BASE_FILE__` follows the
uncached path to preserve its original location semantics. The cache retains
compiler diagnostics, and native C support is relinked from its current sources
on every run. Use ccache's standard `CCACHE_DIR` to choose object storage;
`--cc-work-dir` controls only the stable compilation scratch paths. Keep these
scratch paths stable between runs and remove them only when no runner uses them.

## Split one selection across workers or agents

```sh
python3 tests/run.py --list --filter 'corpus/std/*' --shard 1/2
python3 tests/run.py --zen build/lanes/shared/zen --jobs 2 --filter 'corpus/std/*' --shard 1/2 --timings-json build/results/shard-1.json
python3 tests/run.py --zen build/lanes/shared/zen --jobs 2 --filter 'corpus/std/*' --shard 2/2 --timings-json build/results/shard-2.json
```

The shard index is **one-based**. Matching test IDs are sorted and distributed
round-robin: shard 1/2 takes positions 1, 3, 5, and shard 2/2 takes positions 2,
4, 6. With the same source revision and filter arguments, all shards together
cover the complete selection exactly once. Adding or removing tests can change
assignments; this is deterministic distribution, not a persistent ownership
map or a duration-balancing scheduler.

Each invocation has a distinct temporary work directory. Give concurrent runs
different JSON output paths and budget the total `--jobs` across invocations;
starting two runners at the machine's full CPU count can make both slower.
Use the isolated compiler outputs described in [Build iteration](BUILD_ITERATION.md)
for independent compiler work. Avoid modifying compiler sources during a test
batch: the runner checks the source manifest before and after execution and
returns exit 2 when it changed, so stale dependency information cannot certify
a successful run. Separate checkouts keep concurrent source edits independent.

Sharding happens after complete discovery and format validation. Uncollected
files anywhere still fail an executed shard, the example suite must still be
present, and an empty shard or selection exits 2. `--list` remains an inspection
command: it reports uncollected files but does not execute their failure gate.
A passing shard covers only its selection. Run all shards, or the full
unfiltered verification gate, before treating the complete suite as checked.

## Check the runner itself

```sh
python3 tests/quality/test_runner_parallel.py
python3 tests/run.py --self-check
```

The compiler-free harness regressions cover disjoint shard coverage, invalid
arguments and empty selections, discovery failures beyond a shard, diagnostic
and deferred verdicts, timing report failures, transitive imports, local module
precedence, symlink copy behavior, independent staging directories, and source
changes during a run. When `cc` and `ccache` are installed, four additional
checks exercise real cache reuse, header/flag/source invalidation, native
relinking, diagnostic replay, link failures, missing objects, and path-sensitive
C fallback; those optional checks explicitly skip when either tool is absent.
