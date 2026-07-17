# Features

What the language has and does today. The compiler is **self-hosted** — lexer, parser,
checker, and the C backend are all Zen modules in `zen/compiler/`; the runtime and loader live in
`zen/std/`. They compile to C via `cc` and
reproduce their own committed C byte-for-byte (the fixpoint). C is the intentional
intermediate/bootstrap target, not a defect. No Python, no tree-sitter.
(For the *why* — "structure is the constraint" — see [README](README.md); for how the
compiler is structured, [ARCHITECTURE](ARCHITECTURE.md); for where it's headed,
[VISION](VISION.md).)

## Type system
- **Primitives:** `i32`, `i64`, `u8`, `f64`, `bool`, `void`, plus the non-owning string family
  `string_literal`, `string_cstr`, and `string_view`. **Char literals** `'a'` are sugar
  for the byte value (reuse the integer path, so `b == ':'` not `b == 58`). **Float literals**
  (`1.5`) carry their source lexeme verbatim and are typed `f64`.
- **String provenance types:** `string_literal` is static literal storage, `string_cstr` is a
  borrowed NUL-terminated pointer, and `string_view` is the general readable borrow. All three emit
  `const char*` in Phase 1, but the checker keeps their one-way conversions and aggregate identity
  distinct. `text`, `Cstr`, and `str` remain parser aliases; the formatter and diagnostics use the
  canonical names. See [STRING_TYPES.md](STRING_TYPES.md).
- **Products** — structs: `Point: { x: i32, y: i32 }`.
- **Sums** — enums with optional payloads, variants `|`-separated (a sum is a *choice*):
  `Shape: Circle(i32) | Square(i32) | Dot`
  (lowered to C tagged unions).
- **Slices** — `[T]`, a `(ptr, len)` view (lowers to `struct { T* ptr; int64_t len; }`).
  `[a, b, c]` literals, `xs[i]` indexing, `xs.len`. Iterated with the element-form `loop`.
- **Pointers:** `Ptr<T>` is a non-null read-only borrow, `MutPtr<T>` is a non-null writable
  borrow, and `RawPtr<T>` is the nullable FFI form. All three lower to plain C pointers, but
  their kinds remain distinct in checking and generic-instance identity. `MutPtr<T>` widens
  to `Ptr<T>`; nested pointer, slice, and generic arguments are invariant. `RawPtr<u8>` is the
  deliberately permissive allocator/FFI floor (and the type of `null_ptr()`). Typed raw pointers
  require proof, but the byte floor remains an explicit unsafe boundary. Read-only provenance is
  preserved through `assert_nonnull` and `.addr()`, every store/atomic write is
  direction-checked, and a writable `[T]` cannot be built with `slice(Ptr<T>, len)`.
- **Generics:** `Box<T>`, bounded `<T: Area>` — unification + **monomorphization** to
  concrete C.
- **Traits & impls (keyword-free):** a trait is a record of method signatures
  `Area*: { area: (Ptr<Self>) i32 }`; an impl is owned by the type
  `Vec.impl(Area, { … })` (no `trait`/`impl`/`for` keywords — the block is an argument,
  like `.match({…})`), structural conformance; trait methods dispatch through bounds, an
  unsatisfied bound is a type error. Read-only string traits canonicalize their receiver to
  `string_view`, so one impl serves literal, C-string, and view provenance without making their
  stored types covariant.
- **Inference:** integer literals adapt to the expected type; return types inferred from
  bodies (across calls); `match` exhaustiveness enforced.

## Expressions & control flow
- Full operator set: `+ - * / %  ==  < > <= >=  && ||  !`, each operand-checked. `/` and `%`
  are C truncate-toward-zero, and `/ %` bind tighter than `+ -`.
- `match` with **literal patterns** (`i32`/`bool`), **payload binding** (`.Circle(v) => v`),
  exhaustiveness, and wildcards — the source-level branching form, usable as an expression
  or a statement. The C backend may lower checked matches to `?:` or `if`/`else`
  internally; Zen source does not have an `if` statement or match guard. An exact `if`
  token reports `error[no-if]` with the boolean `.match` replacement.
- **`loop`** — postfix slice iteration: `xs.loop((h, i, x) { … })` iterates a slice's
  elements. The backend also has an internal structured `@while(cond) { … }` form, lowered
  to a C `for`; Zen source does not expose `while`/`for`.
- **Closures-as-values** — a function with a closure-typed parameter `f: (A, B) C` is an
  *inline template*: it is never emitted as a standalone C function. Each call splices the
  body as a GNU statement-expression with the closure argument `(a, x) { … }` inlined where the
  parameter is called. **Zero-cost** (no function pointers), captures resolve in the caller's
  scope so they read *and* mutate as written, and the generated C is compiled by the system `cc`
  in the bootstrap/build paths.
  So `fold`/`each` are ordinary Zen on top of `loop` — `fold(xs, 0, (a, x) { a + x })`.
- **Mutation** — `x = 5` (reassign a local), `s.f = v` (set a field through a `MutPtr`), `xs[i] = v` (write a slice element).
- **Recursion** (so with literal-pattern `match`, it's Turing-complete — `fact`/`fib` run).
  Branching at source level is match-only; booleans branch by matching `true`/`false`.
- `x := v` let-bindings; struct literals; enum constructors; field access; calls.
- **UFCS** — `x.f(a, b)` is sugar for `f(x, a, b)`: the receiver becomes the first argument.
  It desugars uniformly (checker, reachability scan, lowerer), so it resolves free functions and
  trait-bound methods identically to the free-call form, and chains (`5.inc().dbl()`).
- **Visibility** is a glued `*` on the name — `Vec*: { … }`, `area* = () { … }`, `Area*: { … }` —
  not a `pub` keyword (the [VISION](VISION.md) `name[*]` slot, made real). It marks the intended
  public surface. Checked module loading enforces it for destructured values, qualified values, and
  qualified types with `error[private-name]`; the raw flat-module emitter has no module boundary.

## Foreign bindings, errors & FFI memory
The boundary to C, and what's on each side of it, kept explicit. A program is built from
three layers: what's **implicitly there** (the head + intrinsics), what **just links**
(libc), and what you must **import** (`std.*`).

- **A bodyless function IS a foreign extern.** `malloc = (n: i64) RawPtr<u8>` with no
  `{ … }` body binds the C symbol `malloc`; the checker learns the signature, the backend
  emits a forward declaration, and the linker binds it (the system headers define it). No
  `extern` keyword. So libc symbols (`malloc`, `putchar`, `strlen`, …) **just link**.
- **The header is a function** — `zen/std/io/c.zen`'s `libc() [Decl]` builds those bodyless
  bindings *as AST*, and `compiler.genc.genModule(libc())` emits exactly the C prototypes a
  translation unit needs. One source of truth for the libc surface, instead of the same
  externs re-prototyped in every module (the scatter `std.mem.raw`/`std.io.file`/
  `std.core.result` still have at the top, which `std.io.c` gathers).
- **Errors are values** (`std.core.result`) — Zen is `.match`-only with **no `if`, no exceptions,
  and no unwinding**. A fallible call returns a `Result<T, E>` (`.Ok` / `.Err`) the caller
  `.match`es; an optional is `Opt<T>` (`.Some` / `.None`); the standard FFI error is
  `IoError`. `.match` *is* the catch; `return .Err(e)` propagates by value; the boundary
  checkers `ok_if` / `ok_ptr` lift a raw C sentinel (a negative rc, a null pointer) into a
  `Result`; `panic` is the explicit, greppable abort for invariant breaks (not the default
  path). The stdlib fast/fallible contract is documented in [ERROR_POLICY.md](ERROR_POLICY.md).
- **Allocator and FFI ownership rule** (`zen/std/concurrent/cown.zen`) — Zen-owned memory takes
  an explicit allocator from program setup (`cown.buf(alloc, n)` returns `Result` /
  `Buf.free(alloc)`).
  FFI handles remain the raw floor below that discipline: a C descriptor or pointer crosses
  back as a raw handle, then gets wrapped in a small type with the matching release operation
  (`cown.file(path)` / `cown.file_in(alloc, path)` over `open`/`close`, closing the descriptor
  again if wrapping it in `Own<File>` cannot allocate).
- **Coroutine allocation is Result-shaped** (`zen/std/concurrent/coroutine.zen`) —
  `spawn` / `spawn_in` return `Result<Coro, IoError>` and clean up partial
  stack/context allocations on failure; there is no separate `try_*` doubling.
  The scheduler exposes `run` / `run_in`, which return `Result` directly (no `try_*` doubling),
  so the caller can keep flag-buffer allocation failure in the value flow.
- **Metaprogramming is values, not pragmas** — there is no `@emit` and no comptime
  evaluator. A generator is an ordinary function returning `[Decl]`, emitted by
  `compiler.genc.genModule`; `std.internal.ast` gives fluent heap-allocating builders
  (`var("x").dot("a").eq(…)`). `libc()` above is exactly this shape — a function that
  returns its bindings as AST.
- **Raw memory intrinsics** (handled inline by the backend — never declared or imported):
  `x.addr()`, `load(p)`, `store(p, v)`, `offset(p, i)`, `load_i64`/`store_i64`,
  `atomic_add_i64`, `slice(ptr, len)`, **`sizeof(T)`** (byte size of a named type), and
  **`cstr(p)`** (reinterpret a NUL-terminated byte pointer as `string_cstr`).
  `load`/`offset` also read string bytes raw (all Phase-1 non-owning strings are `const char*`), so source
  text can be scanned slice-free. The emitted C head provides the `zslice` typedef (the
  `[T]` fat pointer); you write nothing to get it.
- Enough to build a **heap-allocating, growable `String`** on an allocator — and on top of
  that, an explicit allocator, a `Vec`, and a self-hosted lexer + parser + checker + C/JS
  backends (the compiler itself; see stdlib below).

## Capability entry — `main = (sys: Sys) i32` (Sys phase 1)
The outside world enters through an **explicit capability**, not ambient globals. Two entry
shapes coexist:
- `main = () i32` — the niladic entry.
- `main = (sys: Sys) i32` — the **capability entry**. The compiler renames the user body to
  `zen_user_main` and emits a niladic `zen_main` trampoline that feeds it `std.sys.root()`, so
  the C boundary (`zenrt.c`) stays byte-identical either way.
- **`Sys` (`std.sys`)** bundles narrow capabilities: `heap()` the process-heap `Allocator`,
  `stdout()`/`stderr()` fd-1/fd-2 `Writer`s, `env()` (argv + env vars), `clock()` (mono + wall
  time), `fs()` (file read/write). The design point is **attenuation** — a library function takes
  the narrowest capability it actually needs (`greet = (w: Writer) void`), never the whole `Sys`.
- **`Writer` Result spine (Sys phase 2, shipped):** `Writer.write` / `write_bytes` / `write_line`
  return `Result<i64, IoError>`; `write_or_panic` for scripts. Ambient `println` remains
  best-effort during migration — see [`docs/sys-phase2-print-writer.md`](docs/sys-phase2-print-writer.md).
  Threading `Sys`/allocators explicitly is the model; the ambient-runtime experiment (`std.rt`,
  `std.scope`) is being reworked toward ambient-within-scope, not adopted as the model — see
  [MEMORY_MODEL.md](MEMORY_MODEL.md) and [`docs/two-memory-design.md`](docs/two-memory-design.md).

## Actors & concurrency safety
- **Two actor surfaces (do not conflate):**
  - **Cooperative** (`std.concurrent.actor`) — typed message enums, `Receiver<M>`,
    `ActorRef` / `ReplyRef` / `ActorHandle`. `send` enqueues; `run` / `request` / `ask` drain
    **inline on the caller thread** (optional coroutine checkpoint). Good for demos and
    request/reply; **not** N-core parallel.
  - **Parallel typed** (`std.concurrent.pool_actor`) — same `receive` shape, scheduled on
    `std.concurrent.pool` workers. Requires one concrete trampoline stub per `(Msg, ActorT)`
    (Zen cannot take the address of a generic fn yet). This is the KEEP path for real parallelism.
- **Pool** (`std.concurrent.pool`) — multi-threaded actor run queue across N OS cores (global
  mutex queue today; work-stealing deques are roadmap). `std.thread`/`std.sync` are the floor.
- **Sendability is statically checked** (`compiler.check_validate`, the SENDABILITY pass):
  **move-on-send** — passing an owned `Own<T>` into a send transfers it, so the sender's binding
  is killed (a later use is `error`), which stops the double-free where both actors free the same
  block. A `Ptr<T>` is only sendable when `T` is deeply immutable; `Arc<T>` is the shared-sendable
  path. A companion **scratch-escape** pass keeps actor-local scratch from escaping across a send.
- **Panic isolation** (`zenrt.c`, per-worker) — a `panic` inside one actor's behavior (div-zero,
  OOB, null deref, or stack overflow) unwinds into a per-worker catch and kills **that one actor**;
  the worker and the rest of the pool live on.

## Backends — two, over one checked AST
- **C backend (`compiler.genc` / `genc_emit`)** — the shipping and bootstrap backend. Lowers the
  checked, monomorphized AST to C and invokes `cc` for `build`/`run`. C is the intentional
  intermediate/bootstrap target; `zenc` reproduces its own committed C byte-for-byte.
- **JS backend (`compiler.genjs`)** — a second backend over the **same** post-mono `[Decl]` AST,
  emitting JavaScript for Node/browser (the computational subset) on a small linear-memory floor
  (`bootstrap/zenrt.js`, the JS analog of `zenrt.c`). Driven by `zenc emit-js <file>` and
  `zenc build --target js <file> [-o out]`. Known deferrals: full i64/64-bit bitwise (needs
  BigInt) and aliasing a scalar through `MutPtr<i32>` (needs boxed refs). This is the browser
  direction, made real — new target = new walk over the checked AST, no re-checking.
- An LLVM backend and the one-structure surface syntax from [VISION](VISION.md) remain the
  *direction*, not the current state.

## Standard library (`std.*`)
- Ordinary runtime Zen, importable with `{ … } = std.X` from any file, **checked and lowered
  like your code** — including the compiler's own modules (`lex`/`parse*`/`check`/`genc*`).
- **`std.collections.iter`** — `fold` / `each` over slices + closures, plus two flavours of map/filter:
  `map_into`/`filter_into` are **generic** and write into a caller-owned buffer (no allocation),
  while **`map`/`filter`** return a **fresh heap slice** the caller owns (`map([1,2,3], (x){x*2})`
  → a new `[i32]`). `map_in` / `filter_in` return `Result<[i32], IoError>` for
  allocator failure. The allocating forms are `[i32]` today; a generic version needs
  type-parameter `sizeof`.
- **`std.mem.raw`** — the library's raw libc heap floor: `alloc` / `zeroed` / `copy` / `release`,
  plus namespace-bound `raw.of(seed, n)` for a typed heap slice seeded at index 0. `try_alloc`,
  `try_zeroed`, and `try_of` lift nullable allocation into `Result`. No GC or destructors —
  ownership is explicit.
- **`slice(ptr, len)`** intrinsic — build a `[T]` view from a raw pointer + length (Rust's
  `from_raw_parts`); the element type comes from the wanted slice type (a return/param slot).
- **`std.text.str`** — `len` / `eq` / `ne` / `is_empty` on a `string_view`, plus `view` (a
  `[u8]` byte view that borrows the string's memory), `at` (safe byte indexing with 0
  out of range), and allocator-first `dup` / `substr` helpers for owned copies. An owned string
  is a length-tracked byte slice — `text.dup(a, "hi").len`, index its bytes, release through
  the same allocator, or allocate scoped copies through an arena. String literals are first-class values.
- **`std.text.string`** — a growable, allocator-backed **`String`** assembled at **runtime** (vs a
  `string_literal`): `new_in` / `init`, `push_in` (a byte), `append_in` (a `string_view`),
  `bytes` (a `[u8]` view), `free_in`. Construction takes an allocator, and each op returns the
  updated `(ptr,len,cap)` header while the buffer is resized underneath, so
  `s := s.append_in(a, "…")` threads it. This is the keystone for
  **runtime code generation** — a backend can emit source as a value the running program builds.
- **`std.mem.alloc` — an explicit, Zig-style allocator.** An `Allocator` trait
  (`acquire`/`resize`/`release`) + a stateless libc-backed `Heap`. A function that allocates
  takes the allocator as a parameter, so allocation is visible in the signature; a `<A: Allocator>`
  bound monomorphizes, so dispatch is zero-cost (`a.acquire(n)` compiles straight to the chosen
  allocator). Namespace-bound `alloc.default()` constructs the standard heap allocator.
  `Arena` also implements the trait; namespace-bound `arena.new_in` lets callers
  choose the backing allocator.
- **`std.mem.own` / `std.mem.rc` / `std.mem.arc`** — library ownership types with allocator-first
  constructors (`new_in`) returning `Result` for value-shaped allocation failure. These modules can
  all export the same natural names when imported through namespace binds such as `rc = std.mem.rc`
  and `arc = std.mem.arc`.
- **`std.collections.vec`** — a growable array that threads the allocator explicitly:
  namespace-bound `vec.of(a, [1, 2])`, then `v.push(a, x)` (grows via `a.resize`) /
  `v.get(i)` / `v.len()` / `v.free(a)`; `of` and `push` return `Result` directly for
  `Result`-shaped allocation failure (no `try_*` doubling).
- **`std.collections.map`** — a `string_view`-keyed `Map<T>` with the same allocator-visible
  shape: namespace-bound `maps.of(a, "k", 1)` (returns `Result`), with receiver
  methods `m.put` (returns `Result`), `m.get`, `m.has`, `m.len`, and `m.free`. The
  collections also include a **fully generic `HMap<K, V>`** (`std.collections.hmap`, any hashable
  key), a generic `Set<T>` (`std.collections.set`), and an integer-keyed `IntMap`.
- **Broader stdlib breadth** — beyond the memory/collections/text core above, the tree ships a
  usable systems surface, all ordinary allocator-explicit Zen: **`std.os`** (argv/env),
  **`std.time`** (monotonic + wall clock), **`std.math`** (int + f64 math), **`std.rand`** (a
  deterministic xorshift PRNG), **`std.path`** (POSIX path ops), **`std.fs`** / **`std.io.file`**
  (filesystem read/write), **`std.io.stdin`** (line-oriented input for filters/REPLs),
  **`std.process`** (spawn a subprocess + capture stdout/exit), **`std.net`** (blocking TCP over
  raw sockets), **`std.json`** (a value type + recursive-descent parser + serializer),
  **`std.csv`**, **`std.encoding`** (base64 + hex), **`std.log`** (leveled logging to an explicit
  `Writer`/fd, no ambient state), **`std.testing`** (a value-based unit-test surface),
  **`std.state.store`** (a Redux-style state + reducer + dispatch), and **`std.web.dom`** (the
  browser DOM as typed Zen declarations — the JS-backend target surface).
- **`compiler.genc` (+ `mono` / `genc_emit`) — shared AST + monomorphization, then the C backend, in Zen, AND the compiler's own
  codegen.** It defines the **one AST** the whole pipeline shares — expressions
  `Int`/`Var`/`Bin`/`Call`/`Cond`/`Member`/`Arrow`/`MakeEnum`/`Tag`/`Match`/`StrLit`, statements
  `Let`/`Assign`/`Return`/`If`/`While`, `Struct`/`Enum`/`DRaw` decls, typed `[Param]` + a `Ty` enum
  — and walks it to C in a `String`: `genModule([Decl])` for a whole translation unit
  (forward-declared so recursive types compile), with `compiler.mono` doing generic
  monomorphization. `If`/`While` here are backend/internal structured target forms; the Zen
  source branch form remains `.match`. This is the actual backend the `zenc` binary uses,
  not a demo.
- **`compiler.lex` — a lexer written in Zen.** `scan(src, pos) → { tok: { kind, start, len }, next }`,
  kinds `Ident | Int | Str | Sym | Eof`. Reads the source slice-free (Phase-1 `string_view` is a
  `const char*`),
  tokens are spans (allocation-free), and it handles idents, ints, strings (with escapes), multi-char
  operators (`:= == => <= …`), and `//` comments. The token stream is the pure positional `scan`
  iterated to Eof — or a materialized heap cons-list via `tokenize(a, src)`.
- **`compiler.parse` — a recursive-descent parser written in Zen.** Pulls tokens from `compiler.lex` and
  builds `compiler.genc`'s `Expr`/`Stmt`/`Decl` AST (a heap tree, allocated through the allocator).
  Covers a real subset: **expressions** — integers, identifiers, `+ - * /`, comparisons
  (`== < > <= >=`), one-arg calls, parens, and a boolean **`.match`** that the C backend may
  lower to a ternary;
  **statements** — `name := v` (let), `name = v` (assign), a final-expression return, N of them;
  and whole **function declarations** `name* = (typed params) RetType { body }`, **several per
  module** (`parse_module → genModule` = a translation unit). Written UFCS throughout
  (`src.scan(pos)`, `src.at(i).op_str()`).
- **`compiler.check` + `compiler.check_validate`** — the resolver and the `fits()` validator, in Zen.
  `check` fills the type information the parser can't (each `match`'s enum name, each
  constructor's enum type) by looking names up among a module's decls; `check_validate` adds
  the validating pass whose exit code is the type-error count (the CHECK binary the harness drives).
- **The loop is closed — the compiler is ordinary Zen.** `compiler.lex` → `compiler.parse*` → `compiler.check`
  → `compiler.genc` is the whole `zenc` pipeline, all ordinary Zen. Fed its **own** sources, `zenc`
  re-emits the committed `bootstrap/zenc.gen.c` byte-for-byte (the fixpoint). Correctness is the
  **binary-only harness** (`tests/`): emit/run parity, reject-parity, and the byte-exact
  reproduction — no second compiler to diff against, since the compiler reproduces itself.
- **Zero-cost ambient:** the helpers are templates/generics, so importing `std` emits
  nothing unless a program actually uses them (they inline at the call site).

## Metaprogramming — the AST is data, no pragmas
- **There is no `@emit` pragma and no comptime evaluator.** You metaprogram by building AST
  *values* and emitting them: an ordinary function returns `[Decl]`, and
  `compiler.genc.genModule` lowers it to C. A generator is just a function over data; a `derive`
  is just a function over a `StructDecl`.
- **`std.internal.ast`** — ergonomic, heap-allocating builders over `compiler.genc`'s reified AST, in
  fluent UFCS style, so the builder reads like the Zen it generates:

  ```zen
  var("x").dot("a").eqx(var("y").dot("a"))  // builds the AST for `x.a == y.a`
  ```

  The builders heap-allocate every node and copy every slice, so generated AST safely
  outlives the function that built it (no dangling `.addr()` of a stack literal).
  Declaration-buffer helpers also have allocator-threaded forms such as `dbuf_in`
  and `derive_accessors_in`.
- **The header is a function** — `zen/std/io/c.zen`'s `libc() [Decl]` is exactly this shape: a
  function that returns the libc foreign bindings as AST, emitted by `genModule(libc())`.
  Bindings live in Zen, as data, never as compiler-special-cased C logic.

## Modules & imports
- An import is a destructuring of a module path — `{ a, b } = std.X` binds `a`, `b` from
  `zen/std/X.zen`. Visibility is the glued `*` marker on public names; the checked resolver rejects
  imports or qualified uses of unstarred declarations as `error[private-name]`.
- `zenc check`, `zenc build`, and `zenc run` resolve `std` imports from disk before parsing:
  **`zen/std/internal/resolve.zen`** follows the program's import edges, gathers the transitive
  closure of `zen/std/*.zen` modules, strips the import lines, and concatenates each body
  exactly once (per-module dedup breaks cycles; a per-name pass keeps the first definition
  of each top-level name, so a cross-module clash like `string.free` vs `mem.free` resolves
  deterministically).
- Namespace binds (`c = std.io.c`, `left = sibling`) are also resolved by the checked loader.
  Direct exports from a bound module are prefixed in the flattened source, so two modules can
  both export `thing` or `Box` and be used as `left.thing()` / `right.thing()` without a
  short-name collision.
- The same resolver understands `compiler.X` for internal compiler/std dependencies, but
  normal user-facing library imports live under `std.X`.
- Plain emit mode (`zenc file.zen` or stdin) remains flat and unvalidated: it expects an
  already-flattened module and writes C to stdout.

## Diagnostics
- Checked CLI modes reject on any type error and report the source path, stable error kind,
  message, mapped line/column where available, a source-line caret when the source maps
  cleanly, and a hint. The checker exposes
  `CheckDiagnostic { code, kind, source_offset, span_width, count, message, hint }` for
  the checked CLI path and `Diagnostic { code, kind, span: SourceSpan, count, message, hint }`
  as a first-class Zen value. `diagnostic_from_source` and the module diagnostic helpers
  provide structured spans; lower-level codegen can still operate on accepted declarations.

## Pipeline
Checked commands run `resolve imports (std.internal.resolve) → scan (compiler.lex) → parse
(compiler.parse*) → check (compiler.check/check_validate) → emit C (compiler.genc) → cc`, all ordinary Zen
modules that the `zenc` binary runs and that compile themselves. `build`/`run` reject an
ill-typed program before linking.
Plain emit mode skips the std-import loader and validator and writes C for one flat module.

## Not yet (the honest gaps)
- Plain emit mode is still a flat-module C emitter, not the checked multi-module path.
- `zenc check`/`build`/`run` resolve `std.X` imports from the repo's `zen/std/`; a broader
  package/module system beyond that std-import closure is still future work.
- The self-hosted checker covers a real but **partial** slice of the language; growing it to
  full parity with what `zenlang` describes is the active arc.
- The allocating `map`/`filter` are `[i32]`-only; a generic version needs type-parameter `sizeof`.
- Two shipping backends (C + JS); the JS backend is the **computational subset** (i64/64-bit
  bitwise and scalar-through-`MutPtr` aliasing are deferred). An LLVM backend and the
  one-structure surface syntax from [VISION](VISION.md) are the *direction*, not the current state.
- **`Writer.write` returns `i64`, not `Result`** — RESOLVED (Sys phase 2): `Writer.write` returns
  `Result<i64, IoError>`. Ambient `println` migration remains open.
- **The ambient runtime is not the model.** `std.rt` (a thread-local `Rt` capability) and
  `std.scope` exist as an experiment, but the shipped direction is **explicit** capabilities —
  threaded allocators and a `Sys` at the entry. Reworking the ambient rt toward
  "ambient-within-scope, explicit-at-boundary" (and the two-memory scratch/shared split) is
  roadmap, not shipped (the current runtime source of truth is `docs/runtime-design.md`).
- String provenance Phase 1 is canonical: `string_literal`, `string_cstr`, and `string_view` are
  distinct checker types. Turning `string_view` into `(ptr, len)` and auditing every stdlib
  signature/capability remains Phase 2 of [STRING_TYPES.md](STRING_TYPES.md).
