# Changelog

All notable changes to **zen**. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions are tagged `vX.Y.Z`
(a `v*` tag triggers `.github/workflows/release.yml`).

## Unreleased

Toward **self-hosting** — the compiler's backend, written in zen, run at runtime:

- **`std.string`** — a growable, owned heap `String` assembled at runtime (the
  keystone: source can now be built as a value while a program runs).
- **`std.genc`** — a C backend *written in zen*, run at runtime. It walks a recursive
  expression AST (incl. `Call` — `fn(arg)`), emits **whole function bodies** (`Func`
  body is a `[Stmt]` of `Let` / `Return`), and a **multi-function module** via
  `genModule([Func]) -> String`. The loop closes — a running zen program emits a
  translation unit of `dbl` + `calc` (which calls `dbl`), compiled and run as
  `calc(4) == 10`; and `int32_t f(int32_t x) { int32_t y = (x + 5); return (y * y); }`
  → `f(10) == 225`.
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
