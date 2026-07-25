# Allocator fuzzer

Two complementary campaigns against Zen's explicit-allocator memory model (`src/std/mem/*`, C floor in
`bootstrap/zenrt.c`). The compiler and every program allocate through libc `malloc`/`realloc`/`free`
(`heap_acquire` in `alloc.zen` is `malloc`), so both angles reach the real allocation path.

## Angle 1 — OOM / allocation-failure injection (`oom-shim.c` + `oom-sweep.sh`)

Zen's design claim is **OOM-as-value**: every allocation returns a `Result` the caller must handle.
`oom-shim.c` is an `LD_PRELOAD` interposer that makes the **Nth** `malloc`/`calloc`/`realloc` return
`NULL` (`FAIL_AT=N`); `oom-sweep.sh` sweeps N over a target and classifies each outcome:

| class | meaning |
|-------|---------|
| `OK` | rc == baseline — the failed allocation was absorbed / off the critical path |
| `HANDLED` | clean nonzero exit or an explicit checked panic (`.expect(...)`, `zenc: … allocation failed`) — OOM-as-value working |
| `BUG:NULL` | `null pointer dereference` — an unchecked allocation result was dereferenced |
| `BUG:HEAP` | glibc `double free` / `corruption` / `malloc():` — a corrupted heap on the error path |
| `BUG:SIG` | died by signal with no clean panic line |

```sh
scripts/alloc-fuzz/oom-sweep.sh --check examples/hello.zen   # sweep the COMPILER checking a program
scripts/alloc-fuzz/oom-sweep.sh --build examples/hello.zen   # ... building
scripts/alloc-fuzz/oom-sweep.sh --run   ./some_compiled.bin  # sweep a compiled program's own allocations
# knobs: LOW=<dense band> STEP=<sample stride> CAP=<max N>   ; runs under MALLOC_CHECK_=3 (libc heap checks)
```

Findings (BUG:*) are deduped by signature into `fuzz-out/oom/findings.txt`.

**ASan note.** This runs the ordinary (glibc) build, **not** `zen-asan`: AddressSanitizer owns
`malloc`/`calloc`/`realloc` and does not chain to a preloaded interposer (a preloaded `malloc` is simply
never called under ASan — verified). `MALLOC_CHECK_=3` gives glibc double-free / corruption detection on
the error paths instead. A Zen-level `Allocator` fault hook would be ASan-compatible but needs a compiler
source change (out of scope here).

## Angle 2 — allocator API stress under ASan (`alloc-stress.zen` + `run-stress.sh`)

`alloc-stress.zen` dogfoods `std.mem` under the seeded xoshiro256** RNG: each seed drives a
randomized-but-**valid** op sequence over the process heap (acquire/resize/release), the bump `Arena`
(bump/reset/free), and `Rc`/`Arc` (clone/drop, balanced to zero). Valid by construction, so any
sanitizer hit is an allocator bug (UAF / double-free / overflow / leak / refcount error).

`run-stress.sh` `zen emit`s the program, replicates the driver's HEAD→`zenrt.h` swap, and compiles it
with `-fsanitize=address,undefined` + LeakSanitizer against `zenrt.c` (native `zen build` can't add
sanitizer flags — `ZENC_TARGET_CC` is cross-target only).

```sh
scripts/alloc-fuzz/run-stress.sh                 # build + run the stress harness under ASan
SRC=path/to/prog.zen scripts/alloc-fuzz/run-stress.sh   # ASan-run any Zen program (also a handy leak probe)
```

## Artifacts

`oom-shim.so` and everything under `fuzz-out/` are build/run artifacts (git-ignored). Rebuilt on demand.
