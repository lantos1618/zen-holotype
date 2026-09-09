# Repository review and implementation plan

This review targets maintainability, allocation discipline, and trustworthy
verification. A numeric grade is not evidence of completion. The release
milestones in QUALITY_PLAN.md still require native tests, performance budgets,
and release policy work beyond structural cleanup.

## Current evidence

The working-tree baseline contains 233 Zen files, 67,721 lines, 64 functions
with eight or more parameters, and 132 mutual sibling import edges. These are
review signals, not quotas. Previous review snapshots predate the current
NamedCallSite, ActorSend, transport sharing, and semantic recovery work.

## Implementation order

1. Give allocator creation lowering one settled call owner. Keep raw-method
   discovery distinct from emission; preserve one receiver evaluation, one
   allocation call, error carriers, and dynamic/static dispatch.
2. Replace temporary collections used only to find one range implementation
   or method with returned optional values. Use predicate search for pure
   membership. Preserve declaration order and incomplete-impl fallback.
3. Borrow loop arguments from their AST call instead of copying them into a
   vector. Put argument indexing and checked tail access on the borrowed view;
   share it with fold lowering without merging range/control-flow subjects.
4. Simplify LSP and CLI searches where the existing collection already owns
   iteration. Consolidate forwarding-only boundaries only when they do not
   represent an independent invariant.
5. Add the missing full compiler fixpoint to the authoritative verification
   command, prove that it rejects a changed output, regenerate the seed, and
   run the repository gates against the final source.
6. Record measured changes, validation, and remaining work here.

## Area decisions

| Area | Decision |
| --- | --- |
| AST/parser/lexer | Keep syntax and identity boundaries; prefer existing AST owner queries over local scans. |
| Sema | Preserve authoritative/recovery separation; do not move unrelated analyses into the checker merely to reduce files. |
| C generation | Prioritize complete phase owners and temporary-allocation removal; keep type, range, loop control, and ABI responsibilities distinct. |
| Collections/text | Use existing find, then, and result operations where their failure/escape contracts fit. |
| Actors/network | The current actor owns an actual mailbox and lifecycle; HTTP/2 already has actor delivery. Preserve refusal and flow-control semantics. Adding actors to synchronous compiler work has no established benefit. |
| JSON | Preserve borrowed document parsing and owned streaming events; a shared syntax engine requires separate allocation/lifetime proof. |
| LSP | Remove unnecessary search state and serialization buffers; retain workspace overlay positioning. |
| CLI/build | Keep declaration-driven help and parse policy together; simplify searches without changing diagnostic precedence. |
| Formatter | Use the repository formatter and token-faithfulness checks. |
| Tests/CI | Close the missing self-hosting fixpoint oracle; keep one required verification command. |
| Releases/performance | Do not claim completion without executable budgets, native collection parity, and reproducible release checks. |

## Implemented results

- `CreateCall` owns settled allocator-call facts and dynamic/static emission.
- `Struct.has_field`, `Impl.field_value`, and `Impl.bodied_fn` own syntax-only
  searches without scratch allocation. Range resolution returns the first
  eligible implementation instead of allocating a result collection.
- `LoopArgs` borrows the call and receiver, including checked tail indexing;
  loop/fold lowering no longer allocates and fills an argument vector.
- `DefinitionSource` owns one response's buffer/overlay positioning facts.
  Definition lookup uses the AST's expression iterator; CLI command search
  directly searches child commands and returns the first declaration error.
- Continuation use belongs to the live `LoopFrame`. Ordinary and unrolled meta
  loops emit a continuation label only when a `next()` call targets it.
- Three overlapping smoke tests were consolidated with their unique assertions
  retained. `TEST_REVIEW.md` records the coverage mapping and retained cases.
- `make build` now reuses unchanged compiler artifacts, `make bootstrap`
  preserves the C-only path, and `make buildcheck` checks cache invalidation and
  failure publication. Measurements are in `BUILD_ITERATION.md`.
- `make fixpoint` is required by `make verify` and compares every full-compiler
  C unit/header before checking seed freshness. The refreshed seed also brings
  previously unsynchronized source changes into the generated artifact.

| Signal | Before | After |
| --- | ---: | ---: |
| Zen files | 233 | 233 |
| Zen lines | 67,721 | 67,625 |
| Functions with 8+ parameters | 64 | 58 |
| Parameter slots | 17,648 | 17,576 |
| Relay excess above five parameters | 728 | 704 |
| Mutual sibling import edges | 132 | 132 |

Source-health round 06 is this review's starting tree; round 07 is its final
working tree. Earlier rounds describe older source. No external model review
was requested for these two snapshots.

File count and sibling cycles did not decrease. The reviewed short modules
mostly name public surfaces, capability boundaries, or independent syntax
subjects. Merging them to hit a count would not remove coupling. Further
compiler cleanup should model the remaining call/member/inline phases first.

## Remaining work toward the release target

The tree still has generated-C warnings, a deferred later-stage test, native
test/benchmark execution gaps, no enforced compiler/LSP allocation or timing
budgets, and incomplete release policy/matrix coverage. Deep actor sendability
also remains explicitly deferred by the language plan. These are not marked
complete by this refactor or by a green current-stage verification command.

## Validation

The final source passed `make verify`: 1,175 corpus cases passed, one stage-6
case was deferred, and none were uncollected. Parser/lexer/format gates passed;
all six determinism axes and the complete 182-unit compiler fixpoint passed.
The 14-case differential suite reported zero accepted-to-C-rejected programs.
UBSan verified its positive control and a clean instrumented compiler run.
The signature inventory and source-health snapshot pass their freshness checks.

The warning ratchet was lowered, without suppressing warning classes:

| Artifact | Previous budget | New budget |
| --- | ---: | ---: |
| GCC seed | 2,664 | 1,864 |
| Clang seed | 2,692 | 1,893 |
| GCC emitted fixture | 1 | 1 |
| Clang emitted fixture | 8 | 8 |

The small compiler fixture still complements full self-compilation: the former
varies process/path/import order, while the latter proves self-hosting stability
and seed freshness. Neither replaces runtime and diagnostic corpus assertions.

The final build-driver review added header-symlink retarget and symbol-map
publication regressions. All 52 build checks pass after those fixes, and
restoring either bug makes the corresponding check fail. The updated driver
rebuilt the shared compiler successfully; five subsequent unchanged builds had
a median wall time of 0.169 seconds. These final build-only changes were
rechecked independently after the aggregate source verification.
