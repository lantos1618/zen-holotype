# Architecture

How the **self-hosted** compiler is shaped. For *what* the language does see
[FEATURES](FEATURES.md); for the *why* see [README](README.md); for the long-term language
see [VISION](VISION.md).

The compiler is written entirely in Zen (`zen/std/`) and compiles itself. There is no
Python frontend and no tree-sitter — `cc` builds a `zenc` binary from committed C, and
`zenc` regenerates that C. The only Python left in the repo is the **test runner**
(`tests/`), which drives the `zenc` binary as a subprocess and imports no compiler code.

## The pipeline

Each stage is an ordinary Zen module. `zenc` runs them over **one flat module** of source
and prints C; `cc` compiles that C.

```
.zen source (one flat module)
  → scan       (lexer: source → tokens, slice-free)               zen/std/lex.zen
  → parse      (recursive-descent → std.genc Expr/Stmt/Decl)      zen/std/parse{,_expr,_stmt,_type}.zen
  → check      (resolve refs, infer types, fits() each call)      zen/std/check.zen + check_validate.zen
  → emit C     (monomorphize generics, lower the AST to C text)   zen/std/genc.zen + genc_emit.zen + genc_mono.zen
  → cc         (the system C compiler)
```

`std.genc`'s `Expr`/`Stmt`/`Decl` are the **one AST** the parser builds, the checker
annotates, and a backend walks. `std.genjs` is a second backend over that same AST (it
emits JavaScript), which is what proves the AST is genuinely backend-neutral IR rather than
a C-specific tree.

Ill-typed functions are reported by the checker and excluded from codegen; the rest builds.

## Multi-module programs: the loader

`zenc` compiles a single flat module. A program that spans files with `{ … } = std.X`
imports is resolved first by **`zen/std/resolve.zen`** — the self-hosted loader. It reads a
program's import edges, gathers the transitive closure of `zen/std/<name>.zen` modules,
strips the import lines, and concatenates each module body exactly once into one flat module
(per-module dedup breaks cycles; a final per-**name** pass keeps the first definition of
each top-level name, so a cross-module clash resolves deterministically). `tools/loader/`
wraps it as a runnable driver. See [README → Modules & imports](README.md#modules--imports).

## The bootstrap: building the compiler, and the fixpoint

`bootstrap/` holds everything needed to build `zenc` with **no Python**:

| file | what it is |
|---|---|
| `zenc.gen.c` | the compiler's `.zen` sources, already compiled to C (committed, the bootstrap seed) |
| `zenrt.c` / `zenrt.h` | a ~30-line runtime: the growable `String`, `eq`/`is_empty`, `heap` |
| `main.c` | the CLI entry — reads Zen (file/stdin → C on stdout), plus `--build-self` regen |
| `Makefile` | `zenc:` builds the binary; `regen:` regenerates `zenc.gen.c` with it |

```
make -f bootstrap/Makefile zenc     # cc bootstrap/{zenc.gen.c,zenrt.c,main.c} -o zenc
make -f bootstrap/Makefile regen     # builds zenc, then ./zenc --build-self bootstrap/zenc.gen.c .
```

**The fixpoint.** `--build-self` reads the compiler sources, flattens them (the same
import-strip + concat `std.resolve` reproduces), and emits C. Fed its **own** sources,
`zenc` emits **byte-for-byte** the committed `zenc.gen.c` — the compiler reproduces itself.
`tests/test_bootstrap.py` builds the binary from the committed C and checks the
reproduction; codegen is deterministic, so the byte-exact match is the parity guarantee
(no separate "compare two compilers" oracle is needed).

## Correctness: the binary-only oracle

The test suite (`tests/`, run with `pytest`) is the **sole correctness reference**, and it
is Python-*free* in the sense that matters: it imports **no compiler code**. It builds two
artifacts from the committed bootstrap C with `cc` only —

- an **EMIT** binary (`bootstrap/{zenc.gen.c,zenrt.c,main.c}`): Zen source → C on stdout;
- a **CHECK** binary (the same gen.c plus `check_validate.zen`, linked with a tiny
  `check_main.c`): exit code = the number of type errors —

then drives them as subprocesses: `emit_value(src, want)` compiles and runs the emitted C
and asserts the result (a silent-miscompile guard); `verdict(src)` asserts accept/reject
(a reject-parity guard). The harness is being ported to a Zen-native oracle; until then
this is the reference.

The checker is told about a small **runtime prelude** the loader would otherwise supply —
`heap`, `putchar` — prepended as bodyless `DForeign` decls so a checked program treats them
as known imported signatures (`tests/_oracle.py`'s `_PRELUDE`).

## One AST, many emitters

There is a single AST — `std.genc`'s `Expr`/`Stmt`/`Decl`. The parser builds it, the
checker annotates it (filling enum names on `match`/constructors, etc.), and each backend is
a walk over it:

| backend | module | target |
|---|---|---|
| `genc` | `zen/std/genc_emit.zen` | C |
| `genjs` | `zen/std/genjs.zen` | JavaScript (the computational subset) |

A new backend is a new walk; it never re-checks, because the checker already proved the
structure fits. This is the [VISION](VISION.md) "kernel + a row of emitters" made real for
the subset the self-hosted compiler covers today.

## Metaprogramming, as values

There is **no `@emit` pragma and no comptime evaluator** in the self-hosted compiler. You
metaprogram by building AST values and emitting them: an ordinary function returns
`[Decl]`, and `std.genc.genModule` lowers it to C — `std.ast` gives fluent heap-allocating
builders (`var("x").dot("a").eq(…)`), and `zen/std/c.zen`'s `libc()` is exactly this shape
(a function that returns the libc bindings as `[Decl]`). The AST is data; a generator is a
function over data.

## What's deferred

- A typed IR boundary distinct from the source AST (lowering still re-runs inference,
  entangled with monomorphization).
- Growing the self-hosted frontend to full parity with the language `zenlang` describes
  (the checker covers a real but partial slice today).
- More backends (`gen.llvm`, a richer `gen.js`), and the one-structure surface syntax from
  [VISION](VISION.md).
