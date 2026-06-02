# Changelog

All notable changes to **zen**. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions are tagged `vX.Y.Z`
(a `v*` tag triggers `.github/workflows/release.yml`).

## Unreleased

- **Enum variants are `|`-separated** (was `,`): `Opt*<T>: None | Some(T)`. A sum type is
  a *choice*, so `|` ("or") — visually distinct from the `{a, b}` *record* (comma = "and").
  The old comma form no longer parses.

Toward **self-hosting** — the compiler's backend, written in zen, run at runtime:

- **`std.string`** — a growable, owned heap `String` assembled at runtime (the
  keystone: source can now be built as a value while a program runs).
- **`std.genc`** — a C backend *written in zen*, run at runtime. Coverage: expressions
  `Int`/`Var`/`Bin`/`Call`/`Cond` (ternary); statements `Let`/`Return`; **typed,
  multiple parameters** (`[Param]` + a `Ty` enum → C type names) and a return `Ty`;
  control-flow (if/while/assign); field access (value `.` and pointer `->`); pointer types (`T*`); **enums + match** (tagged unions, construction, tag-tested dispatch); whole function bodies; **struct typedefs** (`StructDecl`) via a top-level `Decl` union, so
  `genModule([Decl])` emits a real translation unit (structs + functions); and a **raw
  escape** (`DRaw`) that emits verbatim C — the hatch for anything the AST doesn't model
  (qualifiers like `volatile`/`static`, `__attribute__`s, pragmas, SIMD intrinsics/vector
  types). The loop
  closes — a running zen program emits a **recursive factorial**
  `int32_t fact(int32_t n) { return ((n <= 1) ? 1 : (n * fact((n - 1)))); }` → `fact(5) == 120`,
  a 2-arg `int32_t add(int32_t a, int32_t b) { return (a + b); }` → `add(3,4) == 7`, a
  `dbl`+`calc` module (`calc(4) == 10`), and a `let`+`return` body → `f(10) == 225`.
- Language work enabling the above: division `/` and remainder `%`; `match`
  auto-derefs a `Ptr<Enum>` (recursive heap structures); type definitions are
  toposorted (recursive types in any declaration order); UFCS (`x.f(a)` == `f(x, a)`).
- Codegen bug fixes: slice-of-struct typedef ordering; `Option`-as-enum no longer
  crashes the checker; generic structs infer their type param from a `[T]` field
  literal; a lone-wildcard `match` is `-Werror`-clean.
- Internals: `main.py` split into `resolve.py` / `emit.py` / `build.py`; `build.zen`
  is now *executed* (not scraped) through the comptime engine.

CI (`.github/workflows/ci.yml`) runs mypy + the pytest suite + a smoke build on every
push and PR.

## The self-hosting / bootstrap plan

The end state, and why releases ship what they ship:

```
zen sources ──(zenc, the compiler written in zen)──▶ C files ──(cc)──▶ zenc binary
                                                       │                   │
                                               commit the C        release the binary
```

1. **Reach parity** — grow `std.genc` (and a zen-written parser + checker) until the
   whole compiler is expressible in zen. Today `lower.py` (Python) is the bootstrap host.
2. **Generate + commit the C** — `python -m zen ...` lowers the zen compiler to C; that
   C is committed under `bootstrap/` (a *tracked* path, unlike the gitignored build
   output). Now `cc bootstrap/*.c -o zenc` builds the compiler with no Python and no
   tree-sitter-from-source — the committed C is the bootstrap seed.
3. **Fixpoint** — `zenc` recompiles the zen compiler to C; if it byte-matches the
   committed C, the compiler reproduces itself. CI guards this (codegen is already
   deterministic — see `tests/test_reproducible.py`).
4. **Release the binary**, **retire the Python.** Once the fixpoint holds, `lower.py`
   and the rest of the Python host are no longer needed and get deleted; releases ship
   the `zenc` binary plus the committed bootstrap C.

The release workflow already publishes the *generated C* alongside the binary, so the
artifact shape is in place; only the parity work (step 1) remains before the C being
generated is the compiler itself rather than an example.
