# Profiling Zen programs

Two first-class tools, no external setup beyond a stock profiler:

- `zen profile` — a sampling profile of your *program*, rendered with zen-native names.
- `zen run --time` / `zen build --time` — wall-clock per *compiler pipeline stage*.

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
