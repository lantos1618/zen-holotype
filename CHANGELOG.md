# Changelog

All notable changes to **zen**. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions are tagged `vX.Y.Z`
(a `v*` tag triggers `.github/workflows/release.yml`).

## Unreleased

**Recent arc — capabilities, a second backend, and a broader stdlib** (factual summary):

- **JS backend (`compiler.genjs`)** — a second backend walking the *same* post-monomorphization
  `[Decl]` AST the C backend consumes, emitting JavaScript for Node/browser over a linear-memory
  floor (`bootstrap/zenrt.js`). Driven by `zenc emit-js <file>` and `zenc build --target js
  <file> [-o out]`. Covers the computational subset; full i64/64-bit bitwise and scalar aliasing
  through `MutPtr<i32>` are deferred. `std.web.dom` exposes the browser DOM as typed Zen.
- **Sys phase 1 — the capability entry.** `main = (sys: Sys) i32` is accepted alongside
  `main = () i32`; the compiler renames the body to `zen_user_main` and emits a niladic `zen_main`
  trampoline that feeds it `std.sys.root()`, keeping the `zenrt.c` boundary byte-identical.
  `std.sys` bundles narrow capabilities — `Writer` (stdout/stderr), the process `Allocator`,
  `Env`, `Clock`, `Fs` — for attenuation. `Writer.write` returns `Result<i64, IoError>` (Sys
  phase 2; see `docs/sys-phase2-print-writer.md`).
- **Actor safety made static.** The checker's SENDABILITY pass enforces move-on-send (an `Own<T>`
  passed into a `send` kills the sender's binding), deep-immutability for sending `Ptr<T>`, and a
  scratch-escape pass; at runtime, a `panic` inside one actor is isolated to that actor
  (per-worker catch in `zenrt.c`), and a multi-threaded actor pool runs actors across N OS cores
  (global run queue today; work-stealing deques are roadmap).
- **Namespace hygiene.** Namespace binds (`alias = std.X`) prefix a module's direct exports, so
  two modules can both export `thing`/`Box`/`of`/`default` and be used as `left.thing()` /
  `right.thing()` without a short-name collision; `zenc emit` runs the same resolver as
  `build`/`run`. Std public surfaces were renamed to natural namespace-friendly names
  (`alloc.default`, `vec.of`, `maps.of`, `raw.of`, `file.contents`, `num.integer`, …).
- **Broader stdlib.** Added a usable systems surface — `std.os`, `std.time`, `std.math`,
  `std.rand`, `std.path`, `std.fs`, `std.io.stdin`, `std.process`, `std.net`, `std.json`,
  `std.csv`, `std.encoding`, `std.log`, `std.testing`, `std.state.store` — plus generic
  `HMap<K, V>` / `Set<T>` collections and real OS threads/locks (`std.thread`, `std.sync`).
- **Errors as values, tightened.** `panic` is abort-only; recoverable failures are `Result`/`Opt`
  threaded with `.or_return()`/`.match`. Runtime safety guards make div/mod-zero, slice OOB, and
  stack overflow deterministic message-bearing panics (see [ERROR_POLICY.md](ERROR_POLICY.md) and
  `docs/runtime-design.md`). String provenance types `Cstr`/`Text` landed as backend `Ty`
  variants (Phase 1 of [STRING_TYPES.md](STRING_TYPES.md)); `f64` + float literals are supported.
- **Note on the runtime direction.** The ambient runtime (`std.rt`, `std.scope`) is an experiment,
  not the shipped model; the direction is explicit capabilities, with the rt rework tracked as
  "ambient-within-scope, explicit-at-boundary" (`docs/runtime-design.md`).

**Documentation alignment for current compiler decisions**:

- **C is the intentional intermediate/bootstrap target** — not a defect or fallback. The
  self-hosted compiler still reproduces `bootstrap/zenc.gen.c` byte-for-byte, and `compiler.genc`
  remains the concrete backend used to build `zenc` today.
- **Branching is source-level `.match` only.** Zen source has no `if` statement; checked
  matches may still lower to C `if`/`else` or `?:` inside the backend.
- **CLI module behavior clarified.** `zenc check`, `zenc build`, and `zenc run` resolve
  `{ … } = std.X` imports from `zen/std/` before parsing/checking. Plain emit mode
  (`zenc file.zen` or stdin) remains a flat, unvalidated C emitter.

**Explicit foreign & module boundaries** — the foundation for binding to C and spanning
multiple modules, all in Zen:

- **`std.io.c`** — the libc foreign bindings as a **built AST namespace**: `libc() [Decl]` is a
  function that returns the bodyless `malloc`/`calloc`/`memcpy`/`free`/`strlen`/`strcmp`/`abort`
  declarations, which `genModule` emits as C prototypes. The "header is a function" — one source
  of truth instead of the same externs re-prototyped in every module that frees.
- **`std.core.result`** — errors as **values**: generic `Result<T, E>` / `Opt<T>`, the FFI error enum
  `IoError`, boundary checkers (`ok_if` / `ok_ptr`) that lift a raw C sentinel into a `Result`,
  and `panic` (the explicit, greppable abort). No exceptions, no unwinding — `.match` is the catch
  and `return .Err(e)` propagates.
- **`std.concurrent.cown`** — allocator-owned buffers and C-handle ownership in code:
  `Buf` takes an explicit allocator for memory, while `File` wraps the `open`/`close`
  handle boundary.
- **`std.internal.resolve`** — the self-hosted **module loader**: reads a program's `{ … } = std.X` import
  edges, gathers the transitive closure, strips imports, and concatenates each module body once
  (per-module dedup breaks cycles; a per-name pass keeps the first definition of each top-level
  name) into one flat module for `zenc`.

**Self-hosted — Python and tree-sitter removed.** The compiler is now the `zenc` binary alone:
`cc` builds it from `bootstrap/{zenc.gen.c,zenrt.c,driver.c}`, and `zenc --build-self` regenerates
`zenc.gen.c` byte-for-byte (the fixpoint). The former Python reference frontend, `tree-sitter-zen`,
`generate.py`, and `mypy` are gone; only the binary-only test oracle (pytest as a runner that
imports no compiler code) remains, and it is being ported to a Zen-native oracle.

- **`compiler.genjs`** — a second backend over the *same* `compiler.genc` AST, emitting JavaScript (the
  computational subset). Demonstrates reuse of the shared AST for a second backend: zen generates its
  own C and a partial JS target.
- **Enum variants are `|`-separated** (was `,`): `Opt*<T>: None | Some(T)`. A sum type is a
  *choice*, so `|` ("or") — visually distinct from the `{a, b}` *record* (comma = "and").

CI (`.github/workflows/ci.yml`) builds `zenc` and runs the Zen-native oracle on every push and PR.

## History — the self-hosting / bootstrap path (now complete)

The compiler's backend, then its whole front end, moved into Zen and the host was retired:

```
zen sources ──(zenc, the compiler written in zen)──▶ C files ──(cc)──▶ zenc binary
                                                       │                   │
                                               commit the C        release the binary
```

1. **Backend in Zen** — `compiler.genc` walked an AST and emitted C: scalars, structs, enums +
   `match`, pointers, control flow, recursion; `genModule([Decl])` for a whole translation unit.
2. **Front end in Zen** — `compiler.lex` (lexer) + `compiler.parse*` (recursive-descent parser) building
   `compiler.genc`'s AST, plus `compiler.check` (resolver + `fits()` validator).
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
