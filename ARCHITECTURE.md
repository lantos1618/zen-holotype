# Architecture

How the **self-hosted** compiler is shaped. For the current language behavior see
[SPEC](SPEC.md); for the feature inventory see [FEATURES](FEATURES.md); for the *why* see
[README](README.md); for the long-term language see [VISION](VISION.md).

The compiler is written entirely in Zen (`zen/compiler/`) and compiles itself, with runtime
and user-facing library modules in `zen/std/`. There is no Python frontend and no tree-sitter —
`cc` builds a `zenc` binary from committed C, and `zenc` regenerates that C. C is the intentional
intermediate/bootstrap target for the self-hosted compiler; a **second backend emits JavaScript**
(`genjs`) over the same checked AST. The repo has **zero `.py` files**: even the test harness is a
Zen program (`tests/harness.zen`) that drives the `zenc` binary as a subprocess.

## The pipeline

Each stage is an ordinary Zen module. The checked user-program commands (`zenc check`,
`zenc build`, `zenc run`) resolve `std` imports first, then parse and validate the resulting
flat module; compiler/internal modules can import from `compiler.*`. `build`/`run` pass the
emitted C to `cc`.

```
.zen source
  → resolve imports (loader: std.X/compiler.X graph → one flat module)   zen/std/internal/resolve.zen
  → scan       (lexer: source → tokens, slice-free)               zen/compiler/lex.zen
  → parse      (recursive-descent → compiler.genc Expr/Stmt/Decl)  zen/compiler/parse{,_expr,_stmt,_type}.zen
  → check      (resolve refs, infer types, fits() each call)      zen/compiler/check.zen + check_validate.zen
  → mono       (specialize generics for every concrete use)       zen/compiler/mono.zen
  → emit       ┬─ C  (lower the specialized AST to C text)        zen/compiler/genc.zen + genc_emit.zen  → cc
               └─ JS (the same AST → JavaScript)                  zen/compiler/genjs.zen                → node
```

`compiler.genc`'s `Expr`/`Stmt`/`Decl` are the **one AST** the parser builds, the checker
annotates, and a backend walks. There are **two backends today** — C (default) and JavaScript;
the AST is deliberately backend-neutral, so a further walk (LLVM, …) is a new emitter, not a new
IR. Both emitters walk the *already-checked* AST and never re-check.

Checked CLI modes reject on any type error before linking. `zenc emit-js <file>` and
`zenc build --target js <file>` run the identical resolve/parse/check pipeline and only swap
`genc`'s `genModule` for `genjs`'s `genJsModule` — a type-broken program never produces JS.
The plain emit form (`zenc file.zen` or stdin) is deliberately lower-level: it expects one
already-flat module, skips `std.internal.resolve`/`check_validate`, and writes C to stdout.

## Multi-module programs: the loader

Programs that span files with `{ … } = std.X` imports use **`zen/std/internal/resolve.zen`** — the
self-hosted loader. It reads a program's import edges, gathers the transitive closure of
`zen/std/<name>.zen` modules, and also understands `compiler.X` for internal compiler/std
dependencies. It strips import lines and concatenates each module body exactly once into one
flat module (per-module dedup breaks cycles; a final per-**name** pass keeps the first definition
of each top-level name, so a cross-module clash resolves deterministically).
Namespace binds (`alias = std.X` or `alias = sibling`) are also source-text based, but they
prefix direct exports before flattening; that lets two bound modules export the same short
function or type name and be used through `left.name` / `right.name` in one program.
The resolver also has a structured `ImportEdge { module, alias, namespace, start, next }`
scanner (`import_edges`) that records destructuring and namespace-bind imports in source
order with byte spans. The checked loader consumes that edge list when loading
destructuring dependencies and namespace-bound modules. Declaration resolution still uses
the flattened source path below, but import-head validation and namespace alias rewrite
sets now use structured
`ProvidedSymbol { name, start, next, decl_start, decl_next, imported, foreign }`
values instead of separate newline-delimited declaration scans. User-module duplicate
tracking and the final per-name dedup pass also consume the same symbol data, using
normalized keys for lowered-name collisions while preserving source spelling in diagnostics.

That loader is folded into the shipping CLI for `zenc check`, `zenc build`, and `zenc run`,
so std-importing programs resolve from disk in those modes. Plain emit mode remains flat and
unvalidated.
See [README → Modules & imports](README.md#modules--imports).

## The bootstrap: building the compiler, and the fixpoint

`bootstrap/` holds everything needed to build `zenc` with **no Python**:

| file | what it is |
|---|---|
| `zenc.gen.c` | the compiler's `.zen` sources (including `driver.zen`, the CLI entry, lowered to a `zen_main`), already compiled to C — committed, the bootstrap seed |
| `zenrt.c` / `zenrt.h` | the 161-line C runtime floor: the growable `String`, `eq`/`is_empty`, `heap`, and the thin OS shims the emitted C calls |
| `zenrt.js` | the ~70-line JavaScript runtime floor, prepended to `genjs` output so a program runs under `node` |
| `sources.txt` | the graph/SCC-checked manifest of Zen sources used to regenerate `zenc.gen.c` |
| `Makefile` | `zenc:` builds the binary; `regen:` regenerates `zenc.gen.c` with it |

There is **no `driver.c`** — the CLI is `driver.zen`, an ordinary Zen module compiled into the
seed. The whole `zenc` binary is `cc bootstrap/{zenc.gen.c,zenrt.c}`; the only hand-written C is
the runtime floor.

```
make -f bootstrap/Makefile zenc     # cc bootstrap/{zenc.gen.c,zenrt.c} -o zenc
make -f bootstrap/Makefile regen     # builds zenc, then ./zenc --build-self bootstrap/zenc.gen.c .
```

**The fixpoint.** `--build-self` reads `bootstrap/sources.txt`, strips each listed source's
module import lines, concatenates them in the graph-derived SCC order checked by the resolver harness,
and emits C. Fed its **own** sources,
`zenc` emits **byte-for-byte** the committed `zenc.gen.c` — the compiler reproduces itself.
The harness's `fixpoint` suite builds the binary from the committed C and checks the
reproduction; codegen is deterministic, so the byte-exact match is the parity guarantee
(no separate "compare two compilers" oracle is needed).

## Correctness: the Zen-native harness

The test suite (`tests/`, run with `make harness`) is the **sole correctness reference**, and it
is Python-*free*: the harness is itself a Zen program (`tests/harness.zen` plus the `harness_*.zen`
suites) and the repo has zero `.py` files. It is built with the freshly-made `zenc` and drives
that same shipping binary as a subprocess:

- **value cases** — `emit_value(src, want)` runs `zenc emit`, `#include`s the emitted C body into
  `tests/harness_runner.c`, compiles and runs it, and asserts the printed result (a silent-miscompile
  guard);
- **verdict cases** — `verdict(src)` runs the shipping `zenc check`/`build` and asserts accept vs.
  reject (a reject-parity guard);
- **command / module / build / fuzz / fixpoint** suites drive the real `zenc check`, `zenc build`,
  and `zenc run` paths end to end, including std-import resolution and the self-host fixpoint.

`make harness-fast` runs just the quick value + verdict subset for the inner loop; `make harness`
(the full suite) is the merge gate. Its exit code is the failing-case count.

## One AST, many emitters

There is a single AST — `compiler.genc`'s `Expr`/`Stmt`/`Decl`. The parser builds it, the
checker annotates it (filling enum names on `match`/constructors, etc.), and each backend is
a walk over it:

| backend | module | target |
|---|---|---|
| `genc` | `zen/compiler/genc.zen` + `genc_emit.zen` | C, the default + bootstrap/intermediate target |
| `genjs` | `zen/compiler/genjs.zen` | JavaScript, run under `node` (floor: `bootstrap/zenrt.js`) |

A new backend is a new walk; it never re-checks, because the checker already proved the
structure fits. Source branching is `.match` only, but a backend can choose target-native
branches such as C `if` or `?:` when lowering a checked match. This is the
[VISION](VISION.md) "kernel + a row of emitters" made real for the subset the self-hosted
compiler covers today.

## Metaprogramming, as values

There is **no `@emit` pragma and no comptime evaluator** in the self-hosted compiler. You
metaprogram by building AST values and emitting them: an ordinary function returns
`[Decl]`, and `compiler.genc.genModule` lowers it to C — `std.internal.ast` gives fluent heap-allocating
builders (`var("x").dot("a").eq(…)`), and `zen/std/io/c.zen`'s `libc()` is exactly this shape
(a function that returns the libc bindings as `[Decl]`). The AST is data; a generator is a
function over data.

## What's deferred

- A typed IR boundary distinct from the source AST (lowering still re-runs inference,
  entangled with monomorphization).
- Growing the self-hosted frontend to full parity with the language `zenlang` describes
  (the checker covers a real but partial slice today).
- A broader package/module system beyond the std-import closure that `check`/`build`/`run`
  resolve today; plain emit remains a flat-module C emitter.
- Further backends (e.g. `gen.llvm`) beyond the C and JavaScript emitters that ship today, and
  the one-structure surface syntax from [VISION](VISION.md).
