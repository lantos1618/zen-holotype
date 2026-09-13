# Compiler and language metrics

Measure properties a user can observe and failures we can reproduce. Keep
correctness, safety, speed, and ergonomics separate: a faster build cannot
compensate for a miscompile, and a larger test count cannot establish ownership
soundness. Every observation records the source revision or hashes, compiler,
workload, environment, and relevant denominator.

## Source-review dimensions

Review the language and its implementation separately from timing and test
counts. Agents select representative and high-risk files within disjoint
subsystems, then cite actual functions and cross-file interactions. Every
finding distinguishes a reproduced defect, an algorithmic property, and a
hypothesis needing measurement. Preserve strengths as well as identifying
changes.

| Dimension | Questions for the code review |
| --- | --- |
| Design consistency | Do features obey shared rules? Which exceptions depend on spelling or implementation accidents? |
| Style consistency | Are naming, receiver operations, allocation, error propagation and declaration forms consistent? |
| Elegance and simplicity | How many concepts and mechanisms express one behavior? Where is logic duplicated? |
| Readability | Can a reader follow state changes, control flow and invariants locally? |
| API ergonomics | Are operations discoverable and composable? Which ordinary tasks require workarounds? |
| Debuggability | Are failures positioned and explained? Can generated behavior be traced to checked source? |
| Correctness | Do typing, evaluation order, code generation and backend results agree? |
| Memory safety | Are lifetimes, aliases, initialization, bounds and cleanup respected across control flow? |
| Failure handling | Do OOM, malformed input and I/O failures preserve their causes and valid prior state? |
| Compile-time performance | What do phases, lookup, generic expansion and rebuilds cost as inputs grow? |
| Runtime performance | What allocation, copying, traversal and generated-code overhead does a program incur? |
| Memory efficiency | What are peak and retained bytes, temporary storage and per-node/container costs? |
| Architecture and changeability | Do dependencies point toward their owners? Are authoritative facts distinct from recovery? |
| Test and benchmark quality | Which scenarios have independent oracles and failing controls? Which important interactions are absent? |

When a review requests `/10` assessments, label them subjective judgments over
the inspected scope. Supply evidence, confidence, strengths and improvements
for each dimension; mark unassessed dimensions explicitly. Do not average them
into a language score or raise them automatically when tests pass. Retain the
pre-change assessment and explain any reassessment through the changed source
contracts and remaining limits.

Collate findings before assigning fixes. Prioritize reproducible safety and
correctness failures, then measured scaling problems and concrete API friction.
Give each fix disjoint ownership, a before/after probe and integration checks.
Keep generated reviews and measurements under `build/source_health/`.

## What we measure

| Property | Measure | Source and test owners | Acceptance |
| --- | --- | --- | --- |
| Program correctness | Accepted programs rejected by C; wrong results against independent oracles; unexpected crashes; distinct minimized failure classes | `src/sema`, `src/gen`, `tests/differential`, corpus | Zero known miscompilations or accepted-to-C rejections in the maintained workloads; every discovered class gets a regression |
| Diagnostic accuracy | False errors on valid source; missed primary errors; incorrect spans; secondary errors per single introduced fault | parser, sema diagnostics, LSP diagnostics | CLI and LSP agree on the same source graph and overlays; valid snapshots stay clean |
| Editor state | Stale diagnostics/navigation after edit, correction, dependency change, close, restart | `src/lsp`, `src/zen/zen_path.zen`, VS Code lifecycle tests | Zero stale answers in the maintained protocol traces; one source has one semantic identity |
| Coordinates | Byte/UTF-16 disagreement with an independent encoding oracle | `lsp_pos`, lexer spans, semantic-token and navigation consumers | Zero mismatches within the stated valid-input and recovery policy |
| Responsiveness | Edit-to-corresponding-diagnostics p50/p95; cold/warm query latency; checks per edit batch | LSP serve/built/query, build/check driver | Establish measured baselines before imposing timing budgets; report the document version represented by each result |
| Memory | Allocated/retained bytes and peak bytes for a fixed working set over repeated requests | document/build arenas, allocator, ownership and runtime | Bounded steady-state retention; distinguish allocator retention from leaked reachable state; RSS is supporting evidence |
| Ownership | Unsafe escapes accepted, safe transfers rejected, missing/double cleanup, by scenario class | scope/own/drop/actor checking and emitted cleanup | Explicit coverage of aliases, assignments, branches, aggregates, callbacks and actor payloads; deferred cases remain visible |
| Build predictability | Cold, unchanged, leaf-edit and interface-edit time; invalidated objects; output determinism | build driver, incremental checks, determinism/fixpoint | Preserve correct dependency invalidation and identical output; measure native-tool time separately from compiler phases |
| Runtime cost | Byte visits, allocations, retained storage and scaling with input size | text/collections, formatter, realistic task programs | Costs follow the operation's contract; test a deliberately quadratic or allocating control |
| Practical ergonomics | Workarounds needed, changes required for a realistic feature, diagnostic repair effort, explainability of allocation/failure/ownership | task summarizer, CLI, binary decoder, actor service, formatter | Comparable tasks and reviewed evidence; no aggregate style score or line-count target |
| Verification coverage | Required checks reachable from the aggregate, collected/deferred tests, failing controls detected | Makefile, CI, test runners | No empty successful runs or silently omitted required checks; distinguish implemented gates from planned ones |

Counts must identify the population. Report 800 coordinate checks as coordinate
evidence, not 800 independently tested language features. Count unique failure
classes as well as input failures so one root-cause cascade does not distort
priority. A diagnostic flood and its underlying defect are different counts.

## Randomized review

Use reproducible seeded sampling with an independent oracle. Start with small
feature families whose meaning is unambiguous, then combine features. Preserve
failing inputs and minimize them into maintained tests. Record seeds, number of
samples, rejection/timeout rules, compiler identity, and limitations. A known
bad control must demonstrate that the harness detects its target failure.

Useful next families are full-document LSP edit/correct/close traces, import
root and overlay spellings, checked numeric boundaries, evaluation order, and
ownership escape combinations. Sampling the file tree should be stratified by
subsystem and risk; a uniform random file list can miss small critical modules.
Keep generated probes, reports, context packs, and review results under ignored
`build/source_health/`. Durable decisions and executable regressions belong in
maintained documentation and tests.

## Review and fix order

1. Reproduce editor false positives with identical disk bytes, overlays, source
   roots and compiler identity. Fix shared loader/path identity rather than
   suppressing correct ownership diagnostics. Preserve the client's URI when
   reporting results.
2. Keep extension startup, restart and shutdown on one lifecycle queue. Exercise
   overlapping configuration changes, launch failure and deactivation.
3. Extend state-machine tests to dependency edits, syntax recovery and corrected
   diagnostics. Measure correspondence to document versions before optimizing
   throughput.
4. Establish responsiveness and allocation baselines on fixed project sizes.
   Timing budgets need repeated samples and tolerances; allocation budgets need
   counting probes. Do not infer either from whole-suite duration.
5. Audit ownership failures and remaining implicit compiler operations by
   concrete responsibility and coverage. Cross-file fixes should move facts to
   their owner and make backend consumers use checked facts.

`make verify` is the aggregate compatibility gate. ASan/leak probes and runtime
performance budgets must not be described as covered merely because another
sanitizer or correctness test passes. Record which optional checks were run.

## Ergonomic proposal: positional boolean matches

Proposed, not implemented: `(condition).match({ when_true, when_false })` as a
boolean-only shorthand. The first expression is the true arm and the second is
the false arm. Exactly one arm evaluates. This is a grammar rule rather than an
ordinary overloaded call because existing braces contain explicit match arms.

Acceptance requires parser and formatter agreement, exactly two arms, a boolean
receiver, compatible result types, and the same lexical `.try()`, cleanup and
non-local control behavior as explicit `true =>` / `false =>` arms. Test side
effects in both branches, nesting, malformed arity, and diagnostics before
adopting the shorthand. Compare real call-site readability, especially when the
arms are long; preserve explicit arms as the general match form.
