# Changelog

All notable changes to **zen**. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions are tagged `vX.Y.Z`
(a `v*` tag triggers `.github/workflows/release.yml`).

## Unreleased

**Explicit foreign & module boundaries** — the foundation for binding to C and spanning
multiple modules, all in Zen:

- **`std.c`** — the libc foreign bindings as a **built AST namespace**: `libc() [Decl]` is a
  function that returns the bodyless `malloc`/`calloc`/`memcpy`/`free`/`strlen`/`strcmp`/`abort`
  declarations, which `genModule` emits as C prototypes. The "header is a function" — one source
  of truth instead of the same externs re-prototyped in every module that frees.
- **`std.result`** — errors as **values**: generic `Result<T, E>` / `Opt<T>`, the FFI error enum
  `IoError`, boundary checkers (`ok_if` / `ok_ptr`) that lift a raw C sentinel into a `Result`,
  and `panic` (the explicit, greppable abort). No exceptions, no unwinding — `.match` is the catch
  and `return .Err(e)` propagates.
- **`std.cown`** — the FFI memory convention, in code: FFI is the raw floor below the allocator
  discipline; a C allocator hands back a `RawPtr<T>` (the "wrap me" marker), which gets wrapped in
  a `Drop`-implementing owner behind `Own<T>` (`std.drop`) so the matching `free`/`close` fires
  exactly once at refcount zero (`Buf`/`malloc` and `File`/`open` worked examples).
- **`std.resolve`** — the self-hosted **module loader**: reads a program's `{ … } = std.X` import
  edges, gathers the transitive closure, strips imports, and concatenates each module body once
  (per-module dedup breaks cycles; a per-name pass keeps the first definition of each top-level
  name) into one flat module for `zenc`. `tools/loader/` packages it as a runnable driver.

**Self-hosted — Python and tree-sitter removed.** The compiler is now the `zenc` binary alone:
`cc` builds it from `bootstrap/{zenc.gen.c,zenrt.c,main.c}`, and `zenc --build-self` regenerates
`zenc.gen.c` byte-for-byte (the fixpoint). The former Python reference frontend, `tree-sitter-zen`,
`generate.py`, and `mypy` are gone; only the binary-only test oracle (pytest as a runner that
imports no compiler code) remains, and it is being ported to a Zen-native oracle.

- **`std.genjs`** — a second backend over the *same* `std.genc` AST, emitting JavaScript (the
  computational subset). Proves the AST is genuine backend-neutral IR: zen generates its own C
  **and** JS.
- **Enum variants are `|`-separated** (was `,`): `Opt*<T>: None | Some(T)`. A sum type is a
  *choice*, so `|` ("or") — visually distinct from the `{a, b}` *record* (comma = "and").

CI (`.github/workflows/ci.yml`) builds `zenc` and runs the pytest oracle on every push and PR.

## History — the self-hosting / bootstrap path (now complete)

The compiler's backend, then its whole front end, moved into Zen and the host was retired:

```
zen sources ──(zenc, the compiler written in zen)──▶ C files ──(cc)──▶ zenc binary
                                                       │                   │
                                               commit the C        release the binary
```

1. **Backend in Zen** — `std.genc` walked an AST and emitted C: scalars, structs, enums +
   `match`, pointers, control flow, recursion; `genModule([Decl])` for a whole translation unit.
2. **Front end in Zen** — `std.lex` (lexer) + `std.parse*` (recursive-descent parser) building
   `std.genc`'s AST, plus `std.check` (resolver + `fits()` validator).
3. **Generate + commit the C** — `zenc` lowered the Zen compiler to C, committed under
   `bootstrap/` as the tracked bootstrap seed; now `cc bootstrap/*.c -o zenc` builds it with no
   Python and no tree-sitter.
4. **Fixpoint + retire the host** — `zenc --build-self` recompiles the Zen compiler to C
   byte-for-byte (guarded by `tests/test_bootstrap.py`); the Python reference frontend,
   tree-sitter, and `generate.py` were then **deleted**. Releases ship the `zenc` binary plus the
   committed bootstrap C.

Along the way: division `/` and remainder `%`; `match` auto-derefs a `Ptr<Enum>` (recursive heap
structures); toposorted type definitions (recursive types in any declaration order); UFCS
(`x.f(a)` == `f(x, a)`); a growable owned heap `String` (source can be built as a value at
runtime); slice-of-struct typedef ordering and assorted codegen fixes.
