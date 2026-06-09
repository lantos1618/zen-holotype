# zen

**zen** is a tiny, **self-hosted** compiler for a small [Zen](https://github.com/lantos1618/zenlang)-flavoured
language, built to test one idea: **pin down what every value _is_ with type structure,
and you lock out everything it isn't.** Do that for pointers, modules, and functions
alike, and module imports, type-checking, and pointer safety all become the _same_
operation — checking that a signature fits in one shared space.

The compiler is written in Zen and compiles itself: `cc` builds a `zenc` binary from
committed C, and `zenc` re-emits that C byte-for-byte. C is the intentional
intermediate/bootstrap target today — not a defect or a host-language fallback. There is
**no Python and no tree-sitter** in the build — see [Build & run](#build--run).

> Every path resolves to exactly **one** canonical node — the single definition that
> *is* the meaning of a name — and diamond imports collapse onto it.

## What we're actually doing: structure *is* the constraint

We're not writing checks that hunt for bad programs — no null pass, no borrow pass, no
separate linker. We do the opposite: **we describe exactly what each thing is, and that
description locks out everything it isn't.** A type is a closed door; "checking" is just
confirming the key fits the lock.

Take one annotation. `Ptr<Vec>` is not "a pointer" — it's three locks at once:

```
   Ptr < Vec >
    │     └──── points at THIS type only      (a different struct? rejected)
    ├──────── read-only   →  mutation locked out      (write needs MutPtr)
    └──────── non-null    →  absence locked out       (null needs Option<…>)
```

Every capability is **opt-in**. Didn't write `MutPtr`? You cannot mutate. Didn't write
`Option`? There is no null. Whatever you didn't permit isn't "checked for and rejected" —
it's *unrepresentable*. The same move scales: a **path** locks identity (`core.vec.Vec`
is one node, so you can't mean a different `Vec`), and a **function signature** locks its
call sites (only values whose locks match the parameter get in).

So the three things a compiler usually does separately — resolve names, check types, prove
pointer safety — are here the single act of **fitting a key to a lock**. That's why one
`fits()` does all of it, and why the legal program is exactly the shape the structure
allows, nothing more.

## How it works

```
   lex.zen ──tokens──► parse_*.zen ──► std.genc AST ──► check.zen ──► genc_emit.zen ──► C ──► cc
   (all four stages are ordinary Zen, in zen/std/)
```

```
   core/vec.zen   ops.zen   main.zen
        │
        ▼  std.lex + std.parse  (lexer + recursive-descent parser, in Zen)
   ┌──────────┐
   │   AST    │   std.genc Expr / Stmt / Decl values
   └────┬─────┘
        │  insert every decl at its path
        ▼
  ╔═══════════ Namespace — ONE trie (path = identity) ═══════╗
  ║  root                                                    ║
  ║   ├─ core.vec.Vec         (struct)                       ║   diamond imports
  ║   ├─ ops.len   ops.cap    (fns)                          ║   collapse to ONE
  ║   └─ main.area   main.main  (fns)                        ║   node, for free
  ╚═════════════════════╤════════════════════════════════════╝
                        │  resolve refs · infer() each body · fits() each call
                        ▼
              ┌─────────────────────┐
     PASS ✓ ◄─┤  fits(given, want)? ├─► FAIL ✗   reported, excluded from codegen
              └──────────┬──────────┘   null → nonnull ✗  ·  read → mut ✗
                         ▼               (rules: nonnull ≤ Option,  MutPtr ≤ Ptr)
              ┌─────────────────────┐
              │     lower to C      │   Ptr → const* ,  Option → *   (types erase away)
              └──────────┬──────────┘
                         ▼  cc -Wall -Wextra
                    build/vecdemo   ──►   12
```

## Why it pays off

Folding name-resolution, type-checking, and pointer-safety into one `fits()` isn't just
tidy — it buys real things:

- **Imports come for free.** A path *is* a type's identity, so importing is just a trie
  lookup. Diamond imports (A and B both import C) land on the same node automatically — no
  dedup, no conflict logic. The only way to clash is two files claiming one path, which the
  filesystem already forbids.
- **Pointer safety *is* type-checking.** Nullability (`Option<T>`) and direction
  (`Ptr`/`MutPtr`) are axes of the type, so a null flowing into a non-null — or a read-only
  pointer into a mutable slot — is caught by the *same* `fits()` that checks everything
  else. No separate null pass, no borrow checker to write or keep in sync.
- **Zero runtime cost.** The discipline is a compile-time fiction: `Ptr` erases to
  `const*`, `Option` to a bare pointer. Once it checks, the emitted C carries no tags and
  no guards — and `cc` re-verifies the const-correctness, a free second opinion.
- **It stays tiny, and it's its own proof.** The whole checker is one trie + a ~20-line
  `fits()` — written in Zen, and it compiles itself (a deterministic fixpoint).

The trade: it leans on **nominal** identity (a type *is* its path) and asks you to write
every pointer's direction and nullability down. In return you delete two entire passes.

## The whole compiler, in four ideas

**1. One trie is the namespace, the import resolver, and the conflict checker.**
A file's path *is* its name. `core/vec.zen` defining `Vec` becomes the one node
`core.vec.Vec` — so every import of it lands on that same node, and the only way
to get a name conflict is for two files to claim the same path.

```
core/vec.zen     Vec*: { len: i32, cap: i32 }      →  defines node  core.vec.Vec

ops/area.zen     { Vec } = core.vec    ─┐
main.zen         { Vec } = core.vec    ─┴─►  both resolve to that ONE node
                                             (a diamond import — never duplicated)

conflict?  ONLY if two files both define  core.vec.Vec
```

No separate symbol table, import resolver, or conflict pass — they're the same
lookup in one trie. (`std.resolve` is the self-hosted loader that walks a program's
`{ … } = std.X` imports, gathers the transitive closure, and hands `zenc` one flat
module — see [Modules & imports](#modules--imports).)

**2. Pointers are types. `fits()` is the only logic outside the trie.**
Direction (`Ptr`/`MutPtr`/`RawPtr`) and nullability (`Option<T>`, no bare null)
are axes of the type, so the same check that resolves everything else also locks
pointer direction and rejects nulls — no separate null pass, no separate borrow pass.

```
 DIRECTION              NULLABILITY
   MutPtr   (subtype)     Option<T>   nullable
     |                       |
    Ptr      read-only       T         nonnull
```

```
fits(given, want):
    nonnull T    where Option<T> wanted   -> ok      (T ≤ Option<T>)
    Option<T>    where plain    T wanted   -> REJECT  (the null guard)
    MutPtr<T>    where Ptr<T>   wanted     -> ok      (MutPtr ≤ Ptr)
    Ptr<T>       where MutPtr<T> wanted    -> REJECT  (direction locked)
```

**3. The type system erases to plain C.** `Ptr` → `const *`, `MutPtr` → `*`,
`Option<ptr>` → a bare pointer. All safety is proven *before* codegen, so the
output is zero-overhead and the C compiler re-checks the const-correctness for free. The
source language still branches with `.match` only; the C backend is free to lower checked
matches to target-level `if`/`else` or `?:` because those are backend details, not Zen
syntax.

**4. The compiler is Zen, and self-hosting.** Lexer, parser, checker, and the C
backend are all ordinary Zen modules in `zen/std/` (`lex`, `parse*`, `check`, `genc*`).
`zenc` compiles them to C; fed its **own** sources it re-emits byte-for-byte the committed
`bootstrap/zenc.gen.c` — a deterministic **fixpoint**. New backend = new walk over the same
AST (a JavaScript one, `std.genjs`, already exists alongside the intentional bootstrap C
backend, `std.genc`).

## Build & run

The compiler is the `zenc` binary. `cc` builds it from committed C; nothing else is needed.

```sh
make -f bootstrap/Makefile zenc        # cc bootstrap/{zenc.gen.c,zenrt.c,main.c} -o zenc
./zenc path/to/flat.zen > out.c        # plain emit: read flat Zen → emit C on stdout
echo 'add* = (a: i32, b: i32) i32 { a + b }' | ./zenc > out.c
```

Plain emit mode is deliberately small: it expects **one already-flat module**, does not load
`std` imports from disk, and is not the validating user-program path. Use the checked CLI
modes for programs:

```sh
./zenc check prog.zen                  # resolve std imports, type-check, no binary
./zenc build prog.zen -o prog          # resolve std imports, type-check, emit C, link with cc
./zenc run prog.zen                    # same as build, then run the temporary binary
```

`build`/`run` require `main = () i32 { … }`; `check` accepts library-like modules without
`main`. A program with `{ … } = std.X` imports is flattened by the self-hosted loader inside
those checked modes — see [Modules & imports](#modules--imports).

**Regenerate the committed C** after editing any compiler/bootstrap source under
`zen/std/{lex,parse*,check*,genc*,io,resolve}.zen` or `zen/std/check_validate.zen` — the
binary rebuilds its own C, with no Python:

```sh
make -f bootstrap/Makefile regen       # builds zenc, then: ./zenc --build-self bootstrap/zenc.gen.c .
git diff --quiet bootstrap/zenc.gen.c  # the fixpoint: the regenerated C must be byte-identical
```

**Tests** — the **binary-only oracle**. `pytest` here is just the test *runner*: it drives
the compiled `zenc` (and a check-mode build of it) as subprocesses and imports **zero**
compiler code. It is the correctness reference while a Zen-native oracle is brought up.

```sh
pip install -r requirements-dev.txt    # only pytest (no mypy, no compiler deps)
pytest tests/                          # emit/run parity, reject-parity, the fixpoint, modules, traits, genjs
```

## Foreign bindings & the prelude

A program is built from three layers — what's *implicitly there*, what *just links*, and
what you must *import*. Keeping that boundary explicit is the point.

- **The compiler-emitted head.** Every emitted translation unit opens with the `zslice`
  typedef (`typedef struct { void* ptr; int64_t len; } zslice;` — the `[T]` fat pointer)
  and the C `stdint`/`stdbool` types. You write nothing to get these.
- **Intrinsics — handled inline by the backend**, never declared or imported:
  `slice`, `addr`, `load`, `store`, `offset`, `cstr`, `null_ptr`, `load_i64`, `store_i64`,
  `atomic_add_i64`, and `sizeof(T)`. They lower to raw C (a pointer deref, a struct
  literal), so they need no binding.
- **Foreign bindings — a bodyless function IS a C extern.** `malloc = (n: i64) RawPtr<u8>`
  with no `{ … }` body binds the libc symbol `malloc`; the checker learns the signature and
  the backend emits a forward declaration. libc symbols (`malloc`, `putchar`, `strlen`, …)
  then **just link** — the system headers define them. No `extern` keyword.
- **The header *is* a function.** `zen/std/c.zen`'s `libc() [Decl]` builds those bodyless
  bindings *as AST* and `std.genc.genModule(libc())` emits exactly the C prototypes a TU
  needs — the bindings live in **one** Zen module instead of being re-prototyped in every
  file. (`std.mem`, `std.io`, `std.cown`, `std.result` still re-declare the handful of
  symbols they each need at the top, which is the scatter `std.c` is gathering.)
- **std modules — you must import them.** `std.mem`, `std.str`, `std.string`, `std.alloc`,
  `std.vec`, `std.iter`, … are ordinary Zen you bring in with `{ … } = std.X`; they are
  checked and lowered like your own code.

The FFI memory rule (`zen/std/cown.zen`): FFI is the **raw floor below** the allocator
discipline. A C function that allocates hands you a `RawPtr<T>` — the type-system marker
for *"the discipline does not reach here — wrap me."* Re-establish ownership the instant
the pointer crosses back in: wrap the raw handle in a struct that `impl(Drop, …)` and put
it behind `Own<T>` (`std.drop`), so the matching `free`/`close` fires **exactly once**, at
refcount zero. See **[FEATURES.md](FEATURES.md)** for the full bindings/errors/memory
inventory.

## Modules & imports

Imports are a destructuring of a module path: `{ a, b } = std.X` binds `a` and `b` from
`zen/std/X.zen`. The checked CLI modes (`zenc check`, `zenc build`, `zenc run`) call
`zen/std/resolve.zen` before parsing, so std imports resolve from disk and the program is
then checked as one flattened module:

- it reads the program's `{ … } = std.X` import lines, follows each edge to
  `zen/std/X.zen`, and gathers the **transitive closure**;
- it strips the import lines and concatenates each module's body **once** (per-module dedup
  breaks import cycles; a final per-**name** pass keeps the first definition of each
  top-level name, so a cross-module clash like `string.free` vs `mem.free` resolves the same
  way "nearest defining module wins" would);
- the result is one flat module handed to the normal parse/check/codegen pipeline.

The bare emit form (`zenc file.zen` or stdin) remains lower-level: it expects the source to
already be flat and emits C without the `std` import-loading/check/build wrapper.
`tools/loader/` also packages the resolver as a runnable driver (`loader_driver.zen` +
`loader_main.c`):
`loader <prog.zen> <out_flat.zen> <root>` writes the flattened module. It is itself a
multi-module program, so it bootstraps once via `tools/loader/bootstrap_driver.sh` — the
loader's analogue of `zenc` being built from committed C.

## Errors are values

Zen is `.match`-only — **no exceptions, no stack unwinding** (hidden control flow is
banned). A fallible call returns a `Result<T, E>` (`std.result`): `.Ok(T)` or `.Err(E)`,
which the caller `.match`es. `.match` *is* the catch; `return .Err(e)` propagates by value.
An optional value is `Opt<T>` (`.Some` / `.None`); the standard FFI error is `IoError`. The
boundary helpers `ok_if` / `ok_ptr` lift a raw C sentinel (a negative rc, a null pointer)
into a `Result`. `panic` is the explicit, greppable abort for invariant breaks — *not* the
default path.

## What it covers

The language now covers structs and **generic data types** (`Box<T>` — the type-arg
inferred from field values, monomorphized to concrete C), **user enums** (`|`-separated
variants, C tagged unions), **generic functions** (`id<T>` — type-args inferred by
unification, **monomorphized**), **traits / constrained generics** (keyword-free: a trait
is a record of signatures `Area*: { … }`, an impl is `Vec.impl(Area, { … })`,
`<T: Trait>` — bound methods dispatch to the concrete impl; an unsatisfied bound is a type
error), **`.match`** with payload-binding, exhaustiveness, and **literal patterns** on
`i32`/`bool` (so with **recursion** the language is Turing-complete — `fact`/`fib` compile
and run; there is no source-level `if` statement), **return-type inference** (omit the
return type and it's inferred from the body, across calls), `Ptr/MutPtr/RawPtr` and
`Option`, `i32`/`i64`/`u8`/`bool` with widening, the full operator set
(`+ - * / %  ==  < > <= >=  && ||  !`, each operand-checked), `x := v` let-bindings, the
single `loop` iteration construct, mutation, slices `[T]`, a heap-allocating `String`/`Vec`
on an explicit allocator, and **metaprogramming as values** (build AST with `std.ast` →
emit with `std.genc.genModule` — no `@emit` pragma). Type errors carry `ns:line:col`.

See **[FEATURES.md](FEATURES.md)** for the full inventory,
**[ARCHITECTURE.md](ARCHITECTURE.md)** for how the self-hosted compiler is structured,
**[VISION.md](VISION.md)** for the why, and **[CHANGELOG.md](CHANGELOG.md)** for history.

## Layout

| path | role |
|---|---|
| `zen/std/lex.zen` | the lexer — `scan(src, pos)` over a `str`, slice-free |
| `zen/std/parse.zen` + `parse_expr` / `parse_stmt` / `parse_type` | recursive-descent parser → `std.genc` AST |
| `zen/std/check.zen` + `check_validate.zen` | resolver + the `fits()` validator |
| `zen/std/genc.zen` + `genc_emit` / `genc_mono` | the C backend (the shared AST + emit + monomorphization) |
| `zen/std/genjs.zen` | a JavaScript backend over the *same* AST |
| `zen/std/{mem,str,string,alloc,vec,iter}.zen` | the runtime stdlib (allocator, slices, strings, iterators) |
| `zen/std/{c,result,cown,drop,io,resolve}.zen` | bindings, errors-as-values, FFI-memory rule, module loader |
| `bootstrap/` | `zenc.gen.c` (committed emitted C) + `zenrt.c` (runtime) + `main.c` + `Makefile` |
| `tools/loader/` | the runnable transitive-closure import resolver |
| `tests/` | the binary-only oracle (pytest as runner; imports no compiler code) |

Inspired by treeform's [jsony](https://github.com/treeform/jsony) (parse straight
into typed objects, hook-based) and the syntax of
[zenlang](https://github.com/lantos1618/zenlang).
