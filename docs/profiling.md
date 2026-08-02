# Profiling and benchmarking Zen

Three first-class tools, no external setup beyond a stock profiler:

- `zen profile` — a sampling profile of your *program*, rendered with zen-native names.
- `zen run --time` / `zen build --time` — wall-clock per *compiler pipeline stage*.
- `make bench` — the repeatable benchmark suite: ns/op **and** heap bytes/op per named operation.

The first two are *profiling*: a snapshot of one run, answering "where did this run spend its
time". The third is *benchmarking*: a named operation run many times, producing a number a later
run can be compared against. Reach for `make bench` when the question is "did this change make
things slower, or start leaking".

## `zen profile`

```sh
zen profile prog.zen                  # top-20 table: SELF%  CUM%  FUNCTION
zen profile prog.zen -- arg1 arg2     # everything after -- is the program's argv
zen profile --raw prog.zen            # untouched perf/gprof report, for deep dives
```

What it does:

1. Compiles the program on the dev profile (`-O1 -g`) **plus** `-fno-omit-frame-pointer`, so the
   sampler can walk real frames. It deliberately keeps `-O1` — profiling unoptimized code lies
   about where time goes. The profiling build has its own compile-cache key, so it never replays
   as (or from) a plain dev build.
2. If `perf` is on PATH: `perf record -g --call-graph fp`, then `perf report --no-children`
   parsed into the table. `SELF%` is time in the function itself; `CUM%` is the running sum down
   the table.
3. If perf is missing — or records zero samples (a container with a strict
   `/proc/sys/kernel/perf_event_paranoid` looks exactly like this) — it falls back to `gprof`:
   recompile with `-pg`, run, `gprof -b -p`. Neither installed is an honest error naming both.

The emitted C function names ARE the zen names, so the table needs no mapping — except hoisted
impl methods, which appear in C as `impl_<Trait>_<Ty>_<method>` and are demangled back to
`Ty.method` for display (same scheme as `zen doc`/`tools/sigs.zen`).

Rows from outside your binary keep their origin in brackets (`__strlen_avx2  [libc.so.6]`);
unresolved bare-address rows are dropped.

### Profiling the compiler itself

The compiler is a zen program, so it profiles like one:

```sh
ZEN_ROOT=. ./zen profile driver.zen -- --build-self /tmp/seed.c .
```

profiles a full self-build (frontend + emit of the whole compiler) and prints where the time goes.

## `--time`: compiler stage tables

```sh
ZENC_NO_CACHE=1 zen run --time prog.zen
ZENC_NO_CACHE=1 zen build --time .
```

prints (to stderr, after the verb finishes):

```
zenc --time: pipeline stages
  flatten               0.1 ms      # import resolution + closure flatten
  parse                 0.0 ms
  resolve               0.3 ms      # name/type resolution
  check                 0.0 ms      # type check + validators (incl. desugar/inline)
  mono+emit             0.0 ms      # monomorphize + C emission
  cc                    80.8 ms
  other (io/cache/run)  6.2 ms
  total                 87.6 ms
```

Stage clocks read nothing when the flag is off. A binary-cache hit skips the compile stages
entirely — the table says so; use `ZENC_NO_CACHE=1` when you want a full-compile measurement.

## `make bench`: the benchmark suite

`tests/harness_bench.zen` measures a fixed set of operations repeatedly and reports, per case,
**iterations, total ns, ns/op, and live heap bytes per op**. It is deliberately *not* part of
`make harness` and is not a gate: benchmark numbers are noisy, and a noisy number must never
decide a merge. There is no baseline file of "expected" numbers and nothing compares against one —
it records numbers, humans compare them.

```sh
make -f bootstrap/Makefile bench                    # one line per case
make -f bootstrap/Makefile bench > before.txt       # …change something, rerun → diff the files
ZEN_BENCH_REPS=7 make -f bootstrap/Makefile bench   # this box's noise floor, 7 reps in one process
ZEN_BENCH_SCALE=4 make -f bootstrap/Makefile bench  # longer loops
```

```
case                  iters      total_ns       ns/op   liveB/op             sink
slicelit_sum        1000000      43473370          43         48    1000002000000
string_chain         500000     156234913         312          0          9388890
string_append        500000     124400806         248          0          9388890
println_int          200000     232889292        1164         32           200000
formatln_int         200000     361511804        1807         80          1888890
sort_by_i64             200     170976982      854884          0        300568400
map_put_get          800000     100027920         125          0        799600000
```

Columns are fixed-width with no timestamps or paths, so two runs `diff` cleanly. `sink` is a
deterministic checksum of the work each case did: it must be **identical** between two runs of the
same binary, and it exists so the loops are observable and cannot be folded away.

### The allocation column

`liveB/op` is the point of the suite. It is glibc's own live-bytes accounting
(`mallinfo2().uordblks + .hblkhd`) sampled around the timed loop, divided by iterations. A case
that allocates and frees reads `0`; a case that leaks reads its leak, rounded up to glibc's chunk
granularity. This is what catches the class of bug that motivated the suite — `formatln` of an
integer leaks ~53 bytes per call (two heap-promoted slice literals that are never freed), which
went unnoticed until someone ran valgrind by hand. It now shows up as `liveB/op = 80` on every
run, and will read `0` the day it is fixed.

It is *live bytes*, not an allocation **count**: a case that churns a million malloc/free pairs
also reads 0. For exact counts and leak backtraces, run the same binary under valgrind:

```sh
make -f bootstrap/Makefile bench-valgrind
```

and read `total heap usage: N allocs, M frees` plus the `LEAK SUMMARY`; divide by the `iters`
column for allocs/op. Under valgrind glibc's allocator is replaced, so `liveB/op` reads 0 in every
row — the in-process column and the valgrind numbers are alternatives, never both at once.

For a process-wide allocation count without valgrind's ~30x slowdown, the repo's own LD_PRELOAD
interposer works:

```sh
cc -shared -fPIC -O2 scripts/alloc-fuzz/oom-shim.c -ldl -o /tmp/oom-shim.so
ZALLOC_COUNT=1 LD_PRELOAD=/tmp/oom-shim.so ./zen run tests/harness_bench.zen > /dev/null
```

### Reading a diff honestly

Time columns move; allocation columns do not. Measure the floor on your machine with
`ZEN_BENCH_REPS=9` before believing a regression. On the 16-core dev box at load average ~7, the
min-to-max spread *within one process* over 9 reps was 1.5–2.4% for most cases and 6.4% at worst
(`map_put_get`). *Across* processes it is much wider: one whole-suite run taken while a `cc` was
finishing in the background read `string_chain` at 519 ns/op against a 303–317 baseline — a 1.7x
excursion from contention alone, with every allocation column unchanged.

So never act on a single run. Re-run with `ZEN_BENCH_REPS` and check the reps agree with each
other before comparing them to yesterday's file. A change in `liveB/op`, by contrast, is real
immediately — it does not move with load.

The suite header in `tests/harness_bench.zen` documents what one "op" is for each case, why each
was chosen, and what the emitted C for it looks like.
