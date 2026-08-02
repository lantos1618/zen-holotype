# Zen compiler architecture

Zen is self-hosted: the CLI, loader, parser, semantic passes, formatter, and backends are Zen source.
A committed generated C file plus a small hand-written runtime floor bootstraps the next compiler.

## Shipping pipeline

```text
source files
    │
    ▼
module discovery / import graph / compatibility flattening
    │                         src/compiler/resolve.zen
    ▼
lexer → recursive-descent parser → shared AST
    │     lex.zen + parse*.zen     ast/ast_types.zen
    ▼
resolution / inference / inlining / monomorphization / closure lowering
    │              check*.zen + passes/*.zen + mono.zen
    ▼
type, diagnostic, ownership, escape, send, and boundary validation
    │                    validate/*.zen + diagnostic.zen
    ├──────────────► faithful source formatter       pretty.zen
    ├──────────────► C emitter → cc → executable     backend/c/c_emit.zen
    └──────────────► JavaScript emitter              backend/js/js.zen
```

The backends walk the same resolved/monomorphized AST. C is the complete bootstrap path. JavaScript
is a second emitter with a smaller runtime floor and a target-limited subset; it does not define a
separate frontend or type system.

**Partial.** Sharing the frontend is a structural fact, not a semantic-equivalence guarantee: the JS
emitter is where the two backends diverge, and [STATUS.md](STATUS.md) records an open P0 for it (field
names rewritten, intrinsic/DOM dispatch by bare function name, DOM values returned in representations
Zen expects as `Opt`/`StringView`). Read "same AST" as "same input", not "same meaning".

## Source and AST ownership

`compiler.ast.ast_types` defines the shared declaration, statement, expression, and type data;
parser, checker, C emitter, JS emitter, formatter, and AST-building APIs all use it. `compiler.genc`
(name historical) keeps the value constructors and shared base helpers over those types.

`compiler.ast.expr_children` sits beside it and holds `expr_fold_children` — the single exhaustive
statement of which sub-expressions and statement bodies hang below each `Expr` variant. Broad
recursive walkers delegate their `_` arm to it instead of hand-listing every composite shape, so a
new `Expr` variant fails to compile at that one match rather than being silently skipped by whichever
walkers forgot it. Narrow shape probes (`is_lvalue`, `expr_pos`, …) keep their own `_`: there it
means "not the shape I am asking about", which stays correct.

## Layering: `src/std` sits below `src/compiler`

The prefixes are documentary. The resolver treats `std.` and `compiler.` as the same kind of trusted
repo-tree module id, so nothing in the language enforces the split — `tests/harness_boundaries.zen`
SUITE 10 does: no module under `src/std` may import `compiler.*`, with exactly two exemptions,
`std.internal.ast` and `std.io.c`.

Those two are the metaprogramming surface: build an AST with `std.internal.ast`, emit it with
`compiler.genc`'s `genModule`. Handing out AST values requires naming the AST's types, so the edge is
intrinsic. It is also bounded — both reach only `ast_types`, `genc`, `astops`, and `mangle` (~3k LOC),
never the checker, parser, or driver. Boundedness is the whole point: Zen pulls whole modules, so an
import drags that module's entire transitive closure into the consumer with no tree-shaking.

The rule exists because it drifted once. The module resolver began as a 40-line import-line
classifier that genuinely belonged in `std`, grew into the compiler's real resolver, and stayed at
`std.internal.resolve` until its closure was the entire compiler — 58 modules, ~32k LOC, identical to
`compiler.check`'s. It now lives in `src/compiler/resolve*.zen`.

`std.internal.ast` and `compiler.ast.ast_types` are neither duplicates nor a facade pair. `ast_types`
owns the type definitions, `genc` owns the stack-returning constructors, and `std.internal.ast` owns
the allocator-explicit builders that copy pointer and slice children onto the heap so a returned AST
does not dangle. A re-export facade is impossible under the flat namespace regardless: a same-named
wrapper is a C redefinition of the symbol it wraps.

The parser is split by concern across eleven `parse*.zen` files (`ls src/compiler/parse*.zen`) plus
the lexer — the result of breaking up the original `parse.zen`/`parse_expr.zen` god files:

| Source | Responsibility |
|---|---|
| `lex.zen` | Tokens, literals, comments, and source positions. |
| `parse.zen` | Public parser entry, top-level declaration dispatch, and module assembly. |
| `parse_type.zen` | Type *expressions*, typed parameter lists, brace-skip helpers, and the shared punctuation predicates. |
| `parse_type_decl.zen` | Type *declarations*: struct/enum bodies, fields, variants, and the `<A, B: Trait>` type-parameter list. |
| `parse_impl.zen` | `Type.impl(Trait, {…})` blocks, inherent methods, and trait-default decl synthesis. |
| `parse_implicit.zen` | Post-parse pass: implicit ALL-CAPS type parameters and `name: Trait` params desugared to bounded generics. |
| `parse_expr.zen` | Expression entry and operator-precedence climbing (term/add/shift/bitwise/compare/and/or). |
| `parse_atom.zen` | Atoms and literals: int/float/char/string, leading-dot constructors, lexeme buffers. |
| `parse_primary.zen` | Identifier-led primaries: idents, turbofish, struct literals, parens, prefix ops, slice literals, lambdas. |
| `parse_postfix.zen` | Postfix chains: call/member/index/method/loop suffixes and struct-literal disambiguation. |
| `parse_match.zen` | `match`/`then` forms: arm parsing, boolean/literal/variant matches, pattern binds and destructuring. |
| `parse_stmt.zen` | Blocks, bindings, assignment, return, and internal lowered statements. |

Match parsing lives in `parse_match.zen`, not `parse_expr.zen`, and there are no match guards to parse:
guards were removed from the language in 2026-07 along with `if`.

`pretty.zen` renders that parsed structure while retaining source comments. `zenc fmt --check` and the
in-place formatter compare/render the same canonical result, and fixtures enforce idempotence —
but **Partial**: idempotence is not fidelity. [STATUS.md](STATUS.md) rates the formatter "Partial:
known semantic round-trip failures" and lists the open ones (generic parameters dropped from bodyless
signatures, multi-payload enum syntax lost). A formatted file can be stable under re-formatting and
still not mean what the original meant.

## Modules

`compiler.resolve` scans each file into import edges and provided symbols, constructs a module
table, validates public/private imports, and has parsed-module/check-link APIs. The shipping CLI still
uses `ResolvedProgram.flat` at its parser/checker boundary:

1. discover the entry's transitive import closure;
2. map `std`/`compiler` modules into the checkout and bare local modules beside the entry;
3. validate missing modules/names, visibility, cycles, and duplicate user definitions;
4. prefix namespace-bound direct exports and rewrite qualified uses;
5. deterministically concatenate stripped module bodies;
6. parse, resolve, and emit the flattened compatibility program.

That hybrid explains both the current functionality and its limits. Namespace binds and privacy
work, and the resolver already has per-module graph structures, but nested local package paths and a
signature-linked module world are not the CLI's final architecture yet.

## Semantic architecture today

The semantic layer works, but its shape is the largest maintainability risk.

`check.zen` currently combines:

- declaration indexing and name/receiver dispatch;
- type inference, unification, `fits`, and trait selection;
- generic inlining and monomorphization support;
- match lowering and `or_return` rewriting;
- function-value/closure lifting;
- some pointer and call rules;
- construction of backend-ready lowered nodes.

The `src/compiler/validate/` package then re-walks raw and resolved ASTs for:

- core error counts;
- packed first-error kinds and source positions;
- batch diagnostics plus message enrichment;
- ownership/use-after-consume;
- bound, call, and `or_return` checks that need pre-inline syntax;
- pointer writes/null dereferences;
- escape/address/scratch/sendability analyses;
- must-use, main-signature, infinite-type, and reserved-name checks.

The CLI manually orders these channels and suppresses cascades. This preserves useful diagnostics,
but duplicates traversal and judgments.

Both god files have since been split by prefix family, so the risk is now spread rather than
concentrated (`wc -l src/compiler/check*.zen src/compiler/passes/*.zen src/compiler/validate/*.zen`):

| Package | Files | Lines |
|---|---|---|
| `check.zen` | 1 | 2,397 |
| `check_{desugar,fits,infer,inline,lower,resolve}.zen` | 6 | 3,091 |
| `passes/{closures,lift,orreturn,ptrkind,refcount,subst}.zen` | 6 | 2,249 |
| `validate/{args,core,diag,enrich,kinds,nullalloc,ownership,util}.zen` | 8 | 10,126 |

Size alone was never the problem, and splitting did not fix it: the same fact is still reconstructed
by several walkers, now across more files.

The simplification direction — **Planned**:

| Keep | Consolidate | Separate clearly | Retire after migration |
|---|---|---|---|
| `Ty`, `fits`, declaration index, source spans, typed AST, monomorphization | Count/kind/batch/enrichment into direct `Diagnostic` emission | Module linking, type checking, flow safety, and lowering | Flat-source compatibility, manual diagnostic channel chain, name/shape-only safety guesses |

None of the four columns is finished. The only structural step that has landed is the mechanical
split above — a file-boundary move, not a consolidation: the driver still manually orders the
diagnostic channels, and flat-source compatibility is still the CLI's parser/checker boundary. Read
the table as a direction, not as a progress bar.

A practical sequence is listed in [STATUS.md](STATUS.md). The key constraint is behavioral: every
semantic refactor must preserve accepted/rejected programs, diagnostic kinds/spans, both backends,
and the bootstrap fixpoint before deleting the old path.

## CLI and projects

`driver.zen` owns command dispatch and orchestration. It ships fourteen commands
(`grep -n 'name: "' driver.zen`); three of them — `check`, `emit`, `emit-js` — carry an empty help
string and so do not appear in `--help`:

| Command | Role |
|---|---|
| `init` | Embedded `--bin`/`--lib` project templates. |
| `build` | Build registered targets; dev profile by default, `-r`/`--release` optimized. |
| `run` | Compile and run; `--time` prints per-stage timings. |
| `profile` | Sampling profile (perf, gprof fallback) with Zen-native symbol names. |
| `targets` | List a project's registered targets. |
| `doc` | Minimal doc extraction for a module or file. |
| `audit` | Dead-code, unused-import, and clone report; `--workspace` unions over every main-bearing entry. |
| `lsp` | Diagnostics-only Language Server, JSON-RPC over stdio. |
| `check` | Front-end only; no artifact. |
| `emit` | Emit C. |
| `emit-js` | Emit JavaScript. |
| `fmt` | `--check`/`--stdout`/`--migrate` over the AST formatter. |
| `--build-self` | Regenerate the seed, tree-shaken to what `main` reaches. |
| `--build-self-full` | Regenerate the full seed, no tree-shake. |

Underneath those it reads a single file or resolves `build.zen` projects, runs the checked
compiler pipeline, renders mapped diagnostics from flattened offsets back to source files, invokes
`cc` for C builds, emits JS with `bootstrap/zenrt.js`, and assembles compiler sources for
`--build-self`.

The `lsp` command is a compiler surface, not a driver detail: it is backed by four modules
(`src/compiler/lsp.zen`, `lsp_docs.zen`, `lsp_query.zen`, `lsp_tokens.zen`, 2,129 lines by
`wc -l src/compiler/lsp*.zen`) and its own harness suite (`tests/harness_lsp.zen`). It reuses the
same check pipeline and diagnostic mapping as `check`, so it is a client of the semantic layer rather
than a parallel implementation of it.

`build.zen` is itself compiled and run to emit a target specification. It is the only project
configuration surface. The Zen-side `Target*` record carries twelve fields: `name`, `library_`,
`root_`, `main_`, `out_`, `links_`, `sources_`, `frameworks_`, `libraries_`, `platform_`, `ffi_`,
and `cflags_`. Those
cross the process boundary as a printed ten-line record per target (`std.build::emit_target`) —
name, root, main, out (or the reserved library marker), linker flags, compiler inputs, os, arch, abi, ffi grants — with the
multi-valued fields flattened into the linker-flags and compiler-inputs lines. `driver.zen` parses
that back (`parse_spec_at`) into a nine-field `Spec*` (`driver.zen:2616`: `source`, `out`, `ccflags`,
`links`, `ffi`, `genmods`, `target`, `library`, `ok`). This is a useful proof that build configuration
can use Zen values, but a printed-text ABI between two Zen programs and project-local temporary
naming remain rough.

## Bootstrap and fixpoint

The default build has two layers:

1. `cc` compiles committed `bootstrap/zenc.gen.c` with `bootstrap/zenrt.c` into `./zen`.
2. That compiler reads `bootstrap/sources.txt` plus `driver.zen` and re-emits the committed C.

`bootstrap/sources.txt` is checked against the resolver graph/SCC order. A valid compiler change must
regenerate C and reach a byte-identical fixpoint:

```sh
make regen
cp bootstrap/zenc.gen.c /tmp/zenc.fixpoint.c
make regen
cmp /tmp/zenc.fixpoint.c bootstrap/zenc.gen.c
```

The hand-written C floor supplies process entry, allocation/IO boundaries, threads, signals, and
pooled-actor panic isolation. The JavaScript floor supplies its target runtime.

Everything above those floors is ordinary Zen today, and keeping it that way is a **Planned** policy,
not an enforced invariant: no gate rejects a new hand-written C or JS function added beside the
existing floor. The `tests/harness_boundaries.zen` scans police module layering inside Zen, not the
size of the target substrate.

See [bootstrap/README.md](../bootstrap/README.md) for the exact local workflow.

## Runtime surfaces

Three runtime surfaces coexist in code:

| Surface | Current role | Status |
|---|---|---|
| `std.sys.Sys` | Explicit executable root; attenuates to `Writer`, `Heap`, `Env`, `Clock`, and `Fs`. | Preferred public direction. |
| `std.rt` | Thread-local/process-default ambient allocator runtime; pool actors enter/leave it. | Live legacy/experimental substrate. |
| `std.concurrent.runtime` | Sync/coroutine arenas and checkpoint substrate used by cooperative actors. | Live internal/experimental substrate. |

Concurrency also has two actor surfaces:

- `std.concurrent.actor`: typed cooperative actors drained on the caller thread, including blocking
  request/reply helpers;
- `std.concurrent.pool_actor`: typed actors on OS-worker threads, using a concrete trampoline per
  message/state pair over the pool.

The pool is a real multicore implementation with atomics, mutex/condition primitives, exactly-once
stress tests, and per-actor panic/stack-overflow isolation. Its scheduler is still one global
mutex-protected run queue, not per-worker work stealing. `Sys.Spawner` is a stub: its `spawn` returns
`.Err(.Errno(38))` (ENOSYS) rather than aborting, since the generic signature carries no actor type to
build a trampoline from; actor API convergence is roadmap work, not a shipped abstraction.

## Tests

`tests/harness.zen` dispatches a Zen-native suite. A 16-line C runner supplies only the executable
entry used to run the compiled harness. It imports sixteen category suites
(`grep -n 'harness_' tests/harness.zen`): value, verdict, build, modules, boundaries, misc, fuzz,
argparse, datetime, fmt_roundtrip, lsp, stdsurface, sort, math, iter, and rand.

Two things that read like categories are not: the differential comparison is a separate `make
difftest` gate (`scripts/difftest.sh`, an old-compiler/new-compiler behavioural diff), and the
bootstrap fixpoint check is `fixpoint_ok` in `tests/harness_lib.zen`, called by suites rather than
being one.

The test system's strengths are independent runtime checks, explicit reject kinds, source-span
diagnostics, C/JS differential cases, fixpoint validation, architectural source-boundary checks, and
many adversarial regressions. Its weaknesses are large inline arrays, repeated compilation shells,
duplicated cases across value/verdict/build/modules, source-text implementation assertions, and a
full runtime measured in minutes.

`make harness-fast` runs the value/verdict subset; `make harness` runs everything. The quantified
coverage and reduction plan are in [STATUS.md](STATUS.md).

## Change discipline

For compiler or runtime work. The **CI-enforced** steps fail the merge gate on their own
(`.github/workflows/ci.yml`); the **convention** steps are review discipline with no automated check:

| # | Step | Enforcement |
|---|---|---|
| 1 | Reproduce the behavior with the smallest pass/fail or value pair. | Convention |
| 2 | Run formatter checks on touched Zen. | CI-enforced — `scripts/fmt-check.sh` |
| 3 | Run the smallest relevant harness slice, then the full harness for semantic changes. | CI-enforced — `harness-fast` then `harness` |
| 4 | Regenerate `bootstrap/zenc.gen.c` after any compiler/driver/bootstrap-source change. | CI-enforced — the seed-staleness job re-runs `regen` and diffs |
| 5 | Prove a second regeneration is byte-identical. | CI-enforced — same job; a non-fixpoint seed shows as a diff |
| 6 | Remove a compatibility path only after its replacement passes the same evidence. | Convention |

CI additionally runs `docs-check`, `ffi-verify`, an ASan build, and a conflict-marker scan, none of
which appear in the list above.

Do not use an old plan, audit score, or generated C as semantic authority when the Zen source and
executable tests say otherwise.
