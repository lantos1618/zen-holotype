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
    │                         check.zen + mono.zen
    ▼
type, diagnostic, ownership, escape, send, and boundary validation
    │                         check_validate.zen + diagnostic.zen
    ├──────────────► faithful source formatter       pretty.zen
    ├──────────────► C emitter → cc → executable     backend/c/c_emit.zen
    └──────────────► JavaScript emitter              backend/js/js.zen
```

The backends walk the same resolved/monomorphized AST. C is the complete bootstrap path. JavaScript
is a second emitter with a smaller runtime floor and a target-limited subset; it does not define a
separate frontend or type system.

## Source and AST ownership

`compiler.ast.ast_types` defines the shared declaration, statement, expression, and type data;
parser, checker, C emitter, JS emitter, formatter, and AST-building APIs all use it. `compiler.genc`
(name historical) keeps the value constructors and shared base helpers over those types.

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

The parser is split by concern:

| Source | Responsibility |
|---|---|
| `lex.zen` | Tokens, literals, comments, and source positions. |
| `parse_type.zen` | Types, parameters, delimiters, and parser state. |
| `parse_expr.zen` | Expressions, operators, calls, lambdas, matches, and guards. |
| `parse_stmt.zen` | Blocks, bindings, assignment, return, and internal lowered statements. |
| `parse.zen` | Top-level declarations, records, enums, imports, impls, and module assembly. |

`pretty.zen` renders that parsed structure while retaining source comments. `zenc fmt --check` and
the in-place formatter compare/render the same canonical result; fixtures enforce idempotence.

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

`check_validate.zen` then re-walks raw and resolved ASTs for:

- core error counts;
- packed first-error kinds and source positions;
- batch diagnostics plus message enrichment;
- ownership/use-after-consume;
- bound, call, and `or_return` checks that need pre-inline syntax;
- pointer writes/null dereferences;
- escape/address/scratch/sendability analyses;
- must-use, main-signature, infinite-type, and reserved-name checks.

The CLI manually orders these channels and suppresses cascades. This preserves useful diagnostics,
but duplicates traversal and judgments. `check.zen` is roughly 4.7k lines and
`check_validate.zen` roughly 6.1k lines; size alone is not the problem, but the same fact being
reconstructed by several walkers is.

The simplification direction is:

| Keep | Consolidate | Separate clearly | Retire after migration |
|---|---|---|---|
| `Ty`, `fits`, declaration index, source spans, typed AST, monomorphization | Count/kind/batch/enrichment into direct `Diagnostic` emission | Module linking, type checking, flow safety, and lowering | Flat-source compatibility, manual diagnostic channel chain, name/shape-only safety guesses |

A practical sequence is listed in [STATUS.md](STATUS.md). The key constraint is behavioral: every
semantic refactor must preserve accepted/rejected programs, diagnostic kinds/spans, both backends,
and the bootstrap fixpoint before deleting the old path.

## CLI and projects

`driver.zen` owns command dispatch and orchestration:

- reads a single file or resolves `zen.toml`/`build.zen` projects;
- runs the checked compiler pipeline;
- renders mapped diagnostics from flattened offsets back to source files;
- invokes `cc` for C builds and runs binaries;
- emits JS with `bootstrap/zenrt.js`;
- implements `fmt`, `doc`, and the embedded `init` templates;
- assembles compiler sources for `--build-self`.

`build.zen` is itself compiled and run to emit a five-field target specification. It wins over
`zen.toml`. This is a useful proof that build configuration can use Zen values, but project-local
temporary naming and single-target/single-link-library limits remain rough.

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
pooled-actor panic isolation. The JavaScript floor supplies its target runtime. Everything above
those floors is intended to remain ordinary Zen.

See [bootstrap/README.md](../bootstrap/README.md) for the exact local workflow.

## Runtime surfaces

Three runtime ideas coexist in code:

| Surface | Current role | Status |
|---|---|---|
| `std.sys.Sys` | Explicit executable root; attenuates to `Writer`, `Allocator`, `Env`, `Clock`, and `Fs`. | Preferred public direction. |
| `std.rt` | Thread-local/process-default ambient allocator runtime; pool actors enter/leave it. | Live legacy/experimental substrate. |
| `std.scope` + `std.concurrent.runtime` | Generic sync/async scope, arena, cancellation/checkpoint experiment. | Live and tested, but not the settled target. |

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
entry used to run the compiled harness. Major suites are split into value, verdict, modules, build,
boundaries, misc/differential, fuzz, argparse, datetime, and fixpoint groups.

The test system's strengths are independent runtime checks, explicit reject kinds, source-span
diagnostics, C/JS differential cases, fixpoint validation, architectural source-boundary checks, and
many adversarial regressions. Its weaknesses are large inline arrays, repeated compilation shells,
duplicated cases across value/verdict/build/modules, source-text implementation assertions, and a
full runtime measured in minutes.

`make harness-fast` runs the value/verdict subset; `make harness` runs everything. The quantified
coverage and reduction plan are in [STATUS.md](STATUS.md).

## Change discipline

For compiler or runtime work:

1. reproduce the behavior with the smallest pass/fail or value pair;
2. run formatter checks on touched Zen;
3. run the smallest relevant harness slice, then the full harness for semantic changes;
4. regenerate `bootstrap/zenc.gen.c` after any compiler/driver/bootstrap-source change;
5. prove a second regeneration is byte-identical;
6. remove a compatibility path only after its replacement passes the same evidence.

Do not use an old plan, audit score, or generated C as semantic authority when the Zen source and
executable tests say otherwise.
