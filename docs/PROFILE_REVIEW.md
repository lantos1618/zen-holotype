# Profile-guided iteration and ownership review

This round measured compilation and test costs before changing implementation.
Results are local measurements from September 6, 2026, not CI timing budgets.

| Measured workload | Before | After | Change |
| --- | ---: | ---: | ---: |
| Same 17 compiler-embedding tests, four workers | 32.649 s | 11.790 s with warm native cache | 64% less wall time |
| Full-source C emission, median of three alternating runs | 3.983 s | 3.474 s with indexed lookups | 12.8% less wall time |

The test comparison used exactly the same test IDs and compiler against a
frozen source tree. Zen emission, native linking, execution, and assertions
ran every time. Ccache recorded 17 misses followed by 34 direct hits in its
isolated benchmark cache. These gains describe warm iteration; the first
compilation still has to populate the cache.

The emission comparison used two uninstrumented compiler binaries and one
frozen input snapshot. Both emitted identical bytes for all 182 C units and
the shared header. The lookup change retains ordered vectors and adds maps
for membership/index queries; it never emits by map iteration. Immutable
String byte buffers back the borrowed map keys.

## Profiling evidence

The full fixpoint phase profile took 12.29 seconds: 7.85 seconds for the two
modular emissions, 4.03 seconds for seed emission, and 0.076 seconds linking.
The 183 cached C compilations totalled 1.03 worker-seconds, overlapping across
four workers. Compiler emission was the useful optimization target.

A representative heavy CLI case spent 3.19 seconds in Zen emission and
8.19 seconds in C compilation/linking; staging took 0.087 seconds. The matching
codegen case showed the same distribution. Absolute phase measurements may
include contention from other profiling work.

Kernel policy denied perf events. An isolated `-O2 -pg` compiler supplied gprof
samples and call counts instead. The estimated caller flame views are explicitly
labelled: they are not sampled call stacks. Their before/after `str.eq` call
counts were 87,782,509 and 33,416,275. Production timing, rather than the
instrumented runtime, establishes the reported emission improvement.

A separate py-spy capture sampled 100 heavy staging operations at 250 Hz,
producing 1,481 samples and one sampling error. That is an actual sampled
Python flame graph. Repeated sublayer scans and copying dominate staging,
but staging is under 1% of the heavy tests, so it was not the first target.

Local artifacts under `build/profiles/`:

- `staging-flame.svg`, `staging-speedscope.json`, `staging.folded`: sampled Python stacks.
- `full-dir.gprof.svg`, `map-full-dir.gprof.svg`: labelled estimated caller views.
- `full-dir.gprof.txt`, `map-full-dir.gprof.txt`: raw gprof reports.
- `lookup-benchmark.json`: alternating production timings and byte comparisons.
- `fixpoint-phases.json`, `staging-phases.json`: subprocess phase timings.
- `README.md`: collection details and interpretation limits.

`make clean` removes these local artifacts. The measurements and reasoning
remain recorded here.

## Source changes

- `Emit` uses bulk String appends for indentation; redundant forwarding methods
  are gone. `KeyOrder` owns the stable merge operation and its shared keys.
- `TextEdit` owns edit serialization. Formatter acceptance is checked by the
  shared formatter instead of repeated through a forwarding chain.
- `ShapeNote` owns hover visibility, delimiters, overload deduplication, and a
  reusable signature buffer. Member descriptions stream into the final output.
- LSP Colour variants carry their protocol spelling and use `variant_name()`.
  Completion kinds use a represented enum with explicit numeric values.
- Position models are named `Position` and `TextRange`; conversions name their
  source or LSP coordinate system. LineRun owns bounded column conversion.
  The generic newline lookup lives on str. Oversized columns clamp before
  offset addition, avoiding integer overflow.
- Capabilities use typed values and std.json object/array operations. Response
  envelopes and error handling share RequestTurn methods.
- URI scheme classification is an enum; Uri owns path conversion and overlay
  lookup. Protocol prefix bytes remain constants at the parsing boundary.
- PayloadWalk owns actor payload cycle detection and recursive methods while
  mutating the caller's checker. It preserves direct-string handling and type
  variable cleanup, and stops when it finds an unsafe field.
- VariantCall selects eligible inferred calls without allocating a case vector,
  then owns type settling and memo publication. Constructor surplus checking
  uses a short-circuit predicate and stops after the first diagnostic.

These changes preserve language syntax. A mutable str binding can be reassigned
to another borrowed pointer-and-length view; it does not grow the initial
literal. The server's workspace view borrows from its session allocator.
Actors remain appropriate for asynchronous ownership boundaries; local string
assembly uses synchronous String operations.

## Iteration commands

`make dev-check` and `make dev-run` now enable native C caching when `CACHE`
resolves to ccache. `CACHE=` disables it. Direct runner invocations opt in with
`--cc-cache ccache`. The canonical full verification corpus also enables native
C caching when `CACHE` is available; emission, linking, execution, and verdicts
still run each time. `CACHE=` disables native caching for either workflow.
See [Test iteration](TEST_ITERATION.md) for cache invalidation, path-sensitive
fallback, and the test commands; [Parallel work](PARALLEL_WORK.md) covers lanes.

## Verification

The integrated corpus exercised 1,179 cases: one remains deferred to stage 6.
The first full run passed 1,177 and exposed one expected hover-text change:
`newline_in` now appears among str's public methods. Updating that single
expectation and rerunning its case passed, giving coverage of all 1,178 active
cases without repeating the unchanged corpus. The complete compiler fixpoint,
all determinism axes, and all 14 differential cases passed. Final gate logs are
under `build/profiles/`.

Explicit usize sort indices removed the final signedness regression; both
focused emitter cases passed after that adjustment. The final source also
passed formatting, determinism, the compiler fixpoint, and differential checks.
UBSan instrumentation and its positive control passed, along with 54 build
cache checks and 14 runner checks.

The warning gate passed with stricter seed baselines: GCC 1,857 and Clang
1,887 warnings; representative emitted C remains at 1 and 8 respectively.

## Loop syntax index: September 9, 2026

A fresh profile of the then-current compiler found 74 containment scans making
10,304,722 AST expression lookups. Loop-result collection made another
1,949,542 lookups across 14 scans. The backend now lazily builds one LoopSyntax
index containing break-call IDs and lambda spans. It preserves expression
order, the existing containment rule, and checking every eligible break in its
current semantic context. The parsed tree remains immutable during lowering;
the cache is installed only after allocation succeeds.

Three alternating, uninstrumented runs on one frozen input measured median
full-source C emission at 3.735 seconds before and 3.296 seconds after: 11.8%
less wall time. All 182 C files and the shared header were byte-identical.
Separate gprof runs reduced total expr_at calls from 15,005,316 to 2,895,235.
These are local measurements, not CI budgets or a claim about cold bootstrapping.

Independent review and 18 existing loop-break/nested-loop fixtures found no
regression; three invalid-break diagnostics matched the baseline byte-for-byte.
Profiles, the frozen input, production timings, and comparison results remain
ignored under build/profiles/consolidation-20260909/. The earlier profile's
owned_elsewhere follow-up is therefore implemented by this index.

After the combined source batch passed `make verify J=8 TEST_J=8`, final
uninstrumented measurements on this checkout gave a 0.174-second median
unchanged `make build J=8` across five runs and a 3.239-second median compiler
source-to-C emission across three runs. The latter excludes native compilation
and linking; it is not a fresh bootstrap time. These current-tree observations
are separate from the controlled before/after comparison above.

Aggregate verification took 176.30 seconds: 1,203 corpus cases passed, with one
existing ownership case deferred. The full compiler/seed fixpoint and all
required gates passed. Seed warning baselines are now GCC 936 and Clang 966.
Raw timings and verification logs remain in ignored
build/consolidation-20260909/.
