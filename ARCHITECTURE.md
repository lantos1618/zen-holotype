# Architecture

How the **self-hosted** compiler is shaped. For *what* the language does see
[FEATURES](FEATURES.md); for the *why* see [README](README.md); for the long-term language
see [VISION](VISION.md).

The compiler is written entirely in Zen (`zen/std/`) and compiles itself. There is no
Python frontend and no tree-sitter — `cc` builds a `zenc` binary from committed C, and
`zenc` regenerates that C. C is the intentional intermediate/bootstrap target for the
self-hosted compiler. The only Python left in the repo is the **test runner**
(`tests/`), which drives the `zenc` binary as a subprocess and imports no compiler code.

## The pipeline

Each stage is an ordinary Zen module. The checked user-program commands (`zenc check`,
`zenc build`, `zenc run`) resolve `std` imports first, then parse and validate the resulting
flat module; `build`/`run` pass the emitted C to `cc`.

```
.zen source
  → resolve std imports (loader: std.X graph → one flat module)   zen/std/resolve.zen
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

Checked CLI modes reject on any type error before linking.
The plain emit form (`zenc file.zen` or stdin) is deliberately lower-level: it expects one
already-flat module, skips `std.resolve`/`check_validate`, and writes C to stdout.

## Multi-module programs: the loader

Programs that span files with `{ … } = std.X` imports use **`zen/std/resolve.zen`** — the
self-hosted loader. It reads a program's import edges, gathers the transitive closure of
`zen/std/<name>.zen` modules, strips the import lines, and concatenates each module body
exactly once into one flat module (per-module dedup breaks cycles; a final per-**name** pass
keeps the first definition of each top-level name, so a cross-module clash resolves
deterministically).

That loader is folded into the shipping CLI for `zenc check`, `zenc build`, and `zenc run`,
so std-importing programs resolve from disk in those modes. Plain emit mode remains flat and
unvalidated. `tools/loader/` still wraps the same resolver as a standalone runnable driver.
See [README → Modules & imports](README.md#modules--imports).

## The bootstrap: building the compiler, and the fixpoint

`bootstrap/` holds everything needed to build `zenc` with **no Python**:

| file | what it is |
|---|---|
| `zenc.gen.c` | the compiler's `.zen` sources, already compiled to C (committed, the bootstrap seed) |
| `zenrt.c` / `zenrt.h` | a ~30-line runtime: the growable `String`, `eq`/`is_empty`, `heap` |
| `main.c` | the CLI entry — plain emit, `check`/`build`/`run`, plus `--build-self` regen |
| `Makefile` | `zenc:` builds the binary; `regen:` regenerates `zenc.gen.c` with it |

```
make -f bootstrap/Makefile zenc     # cc bootstrap/{zenc.gen.c,zenrt.c,main.c} -o zenc
make -f bootstrap/Makefile regen     # builds zenc, then ./zenc --build-self bootstrap/zenc.gen.c .
```

**The fixpoint.** `--build-self` reads the compiler sources, strips their `std` import lines
into the fixed bootstrap order, concatenates them, and emits C. Fed its **own** sources,
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

then drives them as subprocesses: `emit_value(src, want)` compiles and runs emitted C and
asserts the result (a silent-miscompile guard); `verdict(src)` asserts accept/reject
(a reject-parity guard). Command-level tests also drive the shipping `zenc check`,
`zenc build`, and `zenc run` paths, including std-import resolution. The harness is being
ported to a Zen-native oracle; until then this is the reference.

The checker is told about a small **runtime prelude** the loader would otherwise supply —
`heap`, `putchar` — prepended as bodyless `DForeign` decls so a checked program treats them
as known imported signatures (`tests/_oracle.py`'s `_PRELUDE`).

## One AST, many emitters

There is a single AST — `std.genc`'s `Expr`/`Stmt`/`Decl`. The parser builds it, the
checker annotates it (filling enum names on `match`/constructors, etc.), and each backend is
a walk over it:

| backend | module | target |
|---|---|---|
| `genc` | `zen/std/genc_emit.zen` | C, the bootstrap/intermediate target |
| `genjs` | `zen/std/genjs.zen` | JavaScript (the computational subset) |

A new backend is a new walk; it never re-checks, because the checker already proved the
structure fits. Source branching is `.match` only, but a backend can choose target-native
branches such as C `if` or `?:` when lowering a checked match. This is the
[VISION](VISION.md) "kernel + a row of emitters" made real for the subset the self-hosted
compiler covers today.

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
- A broader package/module system beyond the std-import closure that `check`/`build`/`run`
  resolve today; plain emit remains a flat-module C emitter.
- More backends (`gen.llvm`, a richer `gen.js`), and the one-structure surface syntax from
  [VISION](VISION.md).
