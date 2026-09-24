# Build and iteration

Use `make build` for ordinary compiler work. It bootstraps from `seed/zen.c`,
emits the current Zen sources, and compiles independent C modules with `J`
workers. It needs Python 3 and GCC or Clang. `ccache` remains optional.

The driver keeps successful state in `build/bootstrap.json`. An unchanged
invocation checks content hashes and returns without recompiling the seed,
emitting C, or linking. Source edits trigger emission, while unchanged C
modules and their dependencies keep their objects. A shared generated header
change can still require every module to compile.

Repairing a missing native object or executable can reuse the previously
emitted C when the source inputs, toolchain settings, newly linked bootstrap
bytes, requested outputs, and every generated artifact still match. Native
compilation and linking retain their existing dependency checks. Changed Zen
source still requires fresh emission.

Invalidation covers:

- Zen, C, and header files under the selected source root, including symlinked
  import folders and a `ZEN_STD` override; the committed seed and native process implementation;
- C compiler command, executable, version, compiler/linker subprograms, flags,
  and environment variables that affect header/toolchain lookup;
- compiler-reported dependencies, including system headers and retargeted header
  symlinks, plus potential include candidates in the compiler's search paths;
- generated C/header files, object contents, output executable contents and
  execute permission, and a requested symbol map.

Header lookup also depends on files that did not exist during the previous
compile: a new header in an earlier `-I`, `-iquote`, `CPATH`, or `C_INCLUDE_PATH`
directory can replace the old selection. The driver records literal include
candidates (including quoted local paths, forced includes, and `__has_include`)
using compiler-reported search roots, including roots that do not yet exist.
Unchanged builds check candidate existence without walking the system include
tree. If lookup changes, both the whole-build shortcut and object reuse are
invalidated. Every submitted C compilation bypasses ccache direct mode so its
old header manifests cannot hide new candidates, including when source changes
back to a historical version. The driver's own content cache still skips
unchanged objects; ccache can reuse objects after preprocessing current inputs.

Computed includes, response files, framework lookup, and opaque preprocessor
options conservatively use fresh emission and object compilation. Ccache can
still reuse an object after preprocessing current inputs. This keeps those
configurations supported without assuming their dependency search is literal.

Compilation failures leave the last successful `./zen` in place and return a
failure status. The next build retries; a failed attempt never becomes cached
success. Symbol-map destinations cannot alias source files, the compiler, or internal
build artifacts. Symbol-map and cache metadata writes are prepared before the
compiler is published. Failure to rename the optional cache after publication
is reported without failing the successful build; old state is revalidated on
the next invocation. A source change during a build also fails the build. Builds sharing
one `--build-dir` serialize with a file lock. Compiler children retain the lock
if the Python driver is killed, preventing the next build from racing surviving
writes. Avoid simultaneously publishing
to the same output from different build directories.

`make bootstrap` runs the complete seed/source bootstrap with a C compiler and
shell tools only. It bypasses incremental state and uses `build/bootstrap/`.
`make clean build` discards all local build state before rebuilding. These
remain useful when changing the host toolchain installation or investigating
bootstrap failures.

Batch related edits before rebuilding. `make` or `make check` combines an
incremental build with cached development test results. Use `make verify` for
the complete repository checks. When regenerating the seed, run
`make -j1 seed verify` in one invocation so both targets share their build
prerequisite. The build driver does not cache correctness gates or replace the full
successive-compiler and seed-freshness checks.

For an isolated build, run from the repository root:

```sh
python3 scripts/build.py --build-dir /tmp/zen-build --output /tmp/zen-next \
  --cc cc --cache ccache --cflags='-O2 -std=c99' --jobs 16
```

`make buildcheck` runs small real-C integration checks in temporary directories.
They exercise input and dependency changes, flag changes, missing/corrupt
artifacts, symlinked imports, clean builds, and failed-build publication. The
checks deliberately compile invalid seed and generated C programs to verify
that failures preserve the published executable. The gate was also checked
against a mutation that disabled object dependency validation; it failed on
the first source change.

## Measurements

Measured on September 6, 2026, on this Linux development machine with 16 C
workers, `cc -O2 -std=c99`, and ccache, using an isolated copy of the compiler
sources. Timings include process startup and are observations, not CI budgets.

| Operation | Wall time |
| --- | ---: |
| Previous recipe, unchanged, warm ccache (median of 3) | 2.209 s |
| Final incremental driver, unchanged (median of 5) | 0.169 s |
| Initial incremental build in an empty build directory | 34.82 s |
| Help-text source edit, one C module submitted | 2.71 s |
| Revert that source edit, one C module submitted | 2.69 s |

The unchanged build was about 13 times faster. The empty-directory measurement
used the machine's existing ccache, so it is not a cold-toolchain benchmark.
A changed source still requires whole-program C emission; seed changes and
shared-header changes remain the expensive cases.

## Parallel work and full validation

[Parallel work](PARALLEL_WORK.md) documents `dev-build`, `dev-check`, and
`dev-run`, which give each worker a separate compiler and build directory.
[Test iteration](TEST_ITERATION.md) covers disjoint shards, timing reports,
and the source import manifest shared within a runner invocation.

The full compiler fixpoint now uses a locked, stable scratch path under
`build/fixpoint`. Outputs are generated into fresh directories and removed
afterward. Stable paths allow ordinary ccache hits without saving successful
gate results or bypassing either compiler emission or the seed comparison.
`tests/determinism/fixpoint.py --work-dir PATH` selects a separate lane.

On the same machine, three alternating runs per implementation with eight C
workers measured the complete fixpoint gate:

| Full compiler validation | Median wall time |
| --- | ---: |
| Previous random temporary paths | 18.701 s |
| Stable scratch paths, warm ccache | 12.193 s |

That is about 35% less wall time (1.53× faster). Every measured run compared all
182 C units, the shared header, and the regenerated seed. The first stable-path
run took 19.063 s before its cache was warm. These measurements use the existing
ccache and are local observations, not cold-build or CI timing guarantees.
The complete corpus with the faster runner also passed: 1,175 passed, one
stage-6 deferred, zero failed or uncollected, with eight workers in 91.27 s.
The corpus timing is a final validation observation, not a before/after claim.

After adding inherited build locks, five final unchanged `make build` calls
had a 0.177 s median (0.171–0.185 s). Rebuilding with the final driver produced
the exact compiler bytes used by the successful full corpus run. All 54 build
invalidation/publication/lock checks, 10 parallel-runner checks, five fixpoint
harness tests, and the full Make fixpoint gate passed.
