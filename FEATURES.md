# Features

What the language has and does today. The compiler is **self-hosted** — lexer, parser,
checker, and the C backend are all Zen modules in `zen/std/` that compile to C via `cc` and
reproduce their own committed C byte-for-byte (the fixpoint). C is the intentional
intermediate/bootstrap target, not a defect. No Python, no tree-sitter.
(For the *why* — "structure is the constraint" — see [README](README.md); for how the
compiler is structured, [ARCHITECTURE](ARCHITECTURE.md); for where it's headed,
[VISION](VISION.md).)

## Type system
- **Primitives:** `i32`, `i64`, `u8`, `bool`, `void`, `str` (a C string; compile-time literals,
  or built at runtime via `cstr` — see Foreign bindings below). **Char literals** `'a'` are sugar
  for the byte value (reuse the integer path, so `b == ':'` not `b == 58`).
- **Products** — structs: `Point: { x: i32, y: i32 }`.
- **Sums** — enums with optional payloads, variants `|`-separated (a sum is a *choice*):
  `Shape: Circle(i32) | Square(i32) | Dot`
  (lowered to C tagged unions).
- **Slices** — `[T]`, a `(ptr, len)` view (lowers to `struct { T* ptr; int64_t len; }`).
  `[a, b, c]` literals, `xs[i]` indexing, `xs.len`. Iterated with the element-form `loop`.
- **Pointers, three kinds, with a real subtyping lattice:** `Ptr<T>` (read-only),
  `MutPtr<T>` (writable), `RawPtr<T>` (untyped, for FFI). `fits()` enforces direction
  (`MutPtr ≤ Ptr`), nullability (`T ≤ Option<T>`, no bare null), invariant writable
  pointees, and integer widening (`u8 ≤ i32 ≤ i64`). All of it erases to plain C.
- **Generics:** `Box<T>`, bounded `<T: Area>` — unification + **monomorphization** to
  concrete C.
- **Traits & impls (keyword-free):** a trait is a record of method signatures
  `Area*: { area: (Ptr<Self>) i32 }`; an impl is owned by the type
  `Vec.impl(Area, { … })` (no `trait`/`impl`/`for` keywords — the block is an argument,
  like `.match({…})`), structural conformance; trait methods dispatch through bounds, an
  unsatisfied bound is a type error.
- **Inference:** integer literals adapt to the expected type; return types inferred from
  bodies (across calls); `match` exhaustiveness enforced.

## Expressions & control flow
- Full operator set: `+ - * / %  ==  < > <= >=  && ||  !`, each operand-checked. `/` and `%`
  are C truncate-toward-zero, and `/ %` bind tighter than `+ -`.
- `match` with **literal patterns** (`i32`/`bool`), **payload binding** (`.Circle(v) => v`),
  exhaustiveness, and wildcards — the source-level branching form, usable as an expression
  or a statement. The C backend may lower checked matches to `?:` or `if`/`else`
  internally; Zen source does not have an `if` statement.
- **`loop`** — the *one* iteration construct (no `while`/`for`). `loop(n, (h, i) { … })` counts;
  `loop(xs, (h, i, x) { … })` / `xs.loop((h, i, x) { … })` iterates a slice's elements — or a
  **user struct**'s, when it supplies `len` and an `at(Ptr<Self>, i64) T` method (`[]`-overloading);
  `loop((h) { … })` is iterless and handle-driven; the handle does `h.break()` / `h.continue()`.
  It desugars onto the **`@while(cond) { … }`** structured primitive, which lowers to a C `for`
  (kept structured so it stays auto-vectorizable — never gotos).
- **Closures-as-values** — a function with a closure-typed parameter `f: (A, B) C` is an
  *inline template*: it is never emitted as a standalone C function. Each call splices the
  body as a GNU statement-expression with the closure argument `(a, x) { … }` inlined where the
  parameter is called. **Zero-cost** (no function pointers), captures resolve in the caller's
  scope so they read *and* mutate as written, and the C stays clean under `-Wall -Wextra -Werror`.
  So `fold`/`each` are ordinary Zen on top of `loop` — `fold(xs, 0, (a, x) { a + x })`.
- **Mutation** — `x = 5` (reassign a local), `s.f = v` (set a field through a `MutPtr`), `xs[i] = v` (write a slice element).
- **Recursion** (so with literal-pattern `match`, it's Turing-complete — `fact`/`fib` run).
  Branching at source level is match-only; booleans branch by matching `true`/`false`.
- `x := v` let-bindings; struct literals; enum constructors; field access; calls.
- **UFCS** — `x.f(a, b)` is sugar for `f(x, a, b)`: the receiver becomes the first argument.
  It desugars uniformly (checker, reachability scan, lowerer), so it resolves free functions and
  trait-bound methods identically to the free-call form, and chains (`5.inc().dbl()`).
- **Visibility** is a glued `*` on the name — `Vec*: { … }`, `area* = () { … }`, `Area*: { … }` —
  not a `pub` keyword (the [VISION](VISION.md) `name[*]` slot, made real). Bare name = private to
  its file, and **enforced**: another module importing a non-`*` name is a `Private` error.

## Foreign bindings, errors & FFI memory
The boundary to C, and what's on each side of it, kept explicit. A program is built from
three layers: what's **implicitly there** (the head + intrinsics), what **just links**
(libc), and what you must **import** (`std.*`).

- **A bodyless function IS a foreign extern.** `malloc = (n: i64) RawPtr<u8>` with no
  `{ … }` body binds the C symbol `malloc`; the checker learns the signature, the backend
  emits a forward declaration, and the linker binds it (the system headers define it). No
  `extern` keyword. So libc symbols (`malloc`, `putchar`, `strlen`, …) **just link**.
- **The header is a function** — `zen/std/c.zen`'s `libc() [Decl]` builds those bodyless
  bindings *as AST*, and `std.genc.genModule(libc())` emits exactly the C prototypes a
  translation unit needs. One source of truth for the libc surface, instead of the same
  externs re-prototyped in every module (the scatter `std.mem`/`std.io`/`std.cown`/
  `std.result` still have at the top, which `std.c` gathers).
- **Errors are values** (`std.result`) — Zen is `.match`-only with **no `if`, no exceptions,
  and no unwinding**. A fallible call returns a `Result<T, E>` (`.Ok` / `.Err`) the caller
  `.match`es; an optional is `Opt<T>` (`.Some` / `.None`); the standard FFI error is
  `IoError`. `.match` *is* the catch; `return .Err(e)` propagates by value; the boundary
  checkers `ok_if` / `ok_ptr` lift a raw C sentinel (a negative rc, a null pointer) into a
  `Result`; `panic` is the explicit, greppable abort for invariant breaks (not the default
  path).
- **FFI memory rule** (`zen/std/cown.zen`) — FFI is the **raw floor below** the allocator
  discipline (`std.alloc` / `std.drop`). You do *not* thread an allocator through the C
  boundary. A C function that allocates hands back a `RawPtr<T>` — the type-system marker
  for *"the discipline does not reach here — wrap me."* Re-establish ownership the instant
  the pointer crosses back: wrap the raw handle in a struct that `impl(Drop, { … })` and
  put it behind `Own<T>`, so the matching `free`/`close` fires **exactly once**, at refcount
  zero (worked examples: `Buf` over `malloc`/`free`, `File` over `open`/`close`).
- **Metaprogramming is values, not pragmas** — there is no `@emit` and no comptime
  evaluator. A generator is an ordinary function returning `[Decl]`, emitted by
  `std.genc.genModule`; `std.ast` gives fluent heap-allocating builders
  (`var("x").dot("a").eq(…)`). `libc()` above is exactly this shape — a function that
  returns its bindings as AST.
- **Raw memory intrinsics** (handled inline by the backend — never declared or imported):
  `addr(x)`, `load(p)`, `store(p, v)`, `offset(p, i)`, `load_i64`/`store_i64`,
  `atomic_add_i64`, `slice(ptr, len)`, **`sizeof(T)`** (byte size of a named type), and
  **`cstr(p)`** (reinterpret a NUL-terminated byte pointer as a runtime `str`).
  `load`/`offset` also read a `str`'s bytes raw (a `str` is a `const char*`), so source
  text can be scanned slice-free. The emitted C head provides the `zslice` typedef (the
  `[T]` fat pointer); you write nothing to get it.
- Enough to build a **heap-allocating, growable `String`** on an allocator — and on top of
  that, an explicit allocator, a `Vec`, and a self-hosted lexer + parser + checker + C/JS
  backends (the compiler itself; see stdlib below).

## Standard library (`std.*`)
- Ordinary runtime Zen, importable with `{ … } = std.X` from any file, **checked and lowered
  like your code** — including the compiler's own modules (`lex`/`parse*`/`check`/`genc*`).
- **`std.iter`** — `fold` / `each` over slices + closures, plus two flavours of map/filter:
  `map_into`/`filter_into` are **generic** and write into a caller-owned buffer (no allocation),
  while **`map`/`filter`** return a **fresh heap slice** the caller owns (`map([1,2,3], (x){x*2})`
  → a new `[i32]`). The allocating forms are `[i32]` today; a generic version needs
  type-parameter `sizeof`.
- **`std.mem`** — the library's allocator over libc: `alloc` / `zeroed` / `copy` / `release`,
  and `new_i32` (a fresh typed slice). No GC or destructors — ownership is explicit.
- **`slice(ptr, len)`** intrinsic — build a `[T]` view from a raw pointer + length (Rust's
  `from_raw_parts`); the element type comes from the wanted slice type (a return/param slot).
- **`std.str`** — `len` / `eq` / `ne` / `is_empty` on a `str` (C string), plus `view` (a
  read-only `[u8]` byte view that borrows a str's memory) and `dup` (an **owned** heap `[u8]`
  copy the caller frees). An owned string is a length-tracked byte slice — `dup("hi").len`,
  index its bytes, `release(it.ptr)`. String literals are first-class values.
- **`std.string`** — a growable, owned heap **`String`** assembled at **runtime** (vs a
  comptime `str` literal): `new` / `with_cap`, `push` (a byte), `append` (a `str`), `bytes` (a
  `[u8]` view), `free`. Functional — each op returns the updated `(ptr,len,cap)` header while the
  buffer is `realloc`'d underneath, so `s := s.append("…")` threads it. This is the keystone for
  **runtime code generation** — a backend can emit source as a value the running program builds.
- **`std.alloc` — an explicit, Zig-style allocator.** An `Allocator` trait
  (`acquire`/`resize`/`release`) + a stateless libc-backed `Malloc`. A function that allocates
  takes the allocator as a parameter, so allocation is visible in the signature; a `<A: Allocator>`
  bound monomorphizes, so dispatch is zero-cost (`a.acquire(n)` compiles straight to the chosen
  allocator). Nothing hides a `malloc`.
- **`std.vec`** — a growable array that threads the allocator explicitly: `a.vec(cap)` /
  `v.push(a, x)` (grows via `a.resize`) / `v.items()` / `v.vfree(a)`.
- **`std.genc` (+ `genc_emit` / `genc_mono`) — the C backend, in Zen, AND the compiler's own
  codegen.** It defines the **one AST** the whole pipeline shares — expressions
  `Int`/`Var`/`Bin`/`Call`/`Cond`/`Member`/`Arrow`/`MakeEnum`/`Tag`/`Match`/`StrLit`, statements
  `Let`/`Assign`/`Return`/`If`/`While`, `Struct`/`Enum`/`DRaw` decls, typed `[Param]` + a `Ty` enum
  — and walks it to C in a `String`: `genModule([Decl])` for a whole translation unit
  (forward-declared so recursive types compile), with `genc_mono` doing generic
  monomorphization. `If`/`While` here are backend/internal structured target forms; the Zen
  source branch form remains `.match`. This is the actual backend the `zenc` binary uses,
  not a demo.
- **`std.genjs` — a second backend over that same AST**, emitting JavaScript (the computational
  subset). Proof the AST is genuine backend-neutral IR: zen generates its own C and JS.
- **`std.lex` — a lexer written in Zen.** `scan(src, pos) → { tok: { kind, start, len }, next }`,
  kinds `Ident | Int | Str | Sym | Eof`. Reads the source slice-free (a `str` is a `const char*`),
  tokens are spans (allocation-free), and it handles idents, ints, strings (with escapes), multi-char
  operators (`:= == => <= …`), and `//` comments. The token stream is the pure positional `scan`
  iterated to Eof — or a materialized heap cons-list via `tokenize(a, src)`.
- **`std.parse` — a recursive-descent parser written in Zen.** Pulls tokens from `std.lex` and
  builds `std.genc`'s `Expr`/`Stmt`/`Decl` AST (a heap tree, allocated through the allocator).
  Covers a real subset: **expressions** — integers, identifiers, `+ - * /`, comparisons
  (`== < > <= >=`), one-arg calls, parens, and a boolean **`.match`** that the C backend may
  lower to a ternary;
  **statements** — `name := v` (let), `name = v` (assign), a final-expression return, N of them;
  and whole **function declarations** `name* = (typed params) RetType { body }`, **several per
  module** (`parse_module → genModule` = a translation unit). Written UFCS throughout
  (`src.scan(pos)`, `src.byte_at(i).op_str()`).
- **`std.check` + `std.check_validate`** — the resolver and the `fits()` validator, in Zen.
  `check` fills the type information the parser can't (each `match`'s enum name, each
  constructor's enum type) by looking names up among a module's decls; `check_validate` adds
  the validating pass whose exit code is the type-error count (the CHECK binary the oracle drives).
- **The loop is closed — the compiler IS this stdlib.** `std.lex` → `std.parse*` → `std.check`
  → `std.genc` is the whole `zenc` pipeline, all ordinary Zen. Fed its **own** sources, `zenc`
  re-emits the committed `bootstrap/zenc.gen.c` byte-for-byte (the fixpoint). Correctness is the
  **binary-only oracle** (`tests/`): emit/run parity, reject-parity, and the byte-exact
  reproduction — no second compiler to diff against, since the compiler reproduces itself.
- **Zero-cost ambient:** the helpers are templates/generics, so importing `std` emits
  nothing unless a program actually uses them (they inline at the call site).

## Metaprogramming — the AST is data, no pragmas
- **There is no `@emit` pragma and no comptime evaluator.** You metaprogram by building AST
  *values* and emitting them: an ordinary function returns `[Decl]`, and
  `std.genc.genModule` lowers it to C. A generator is just a function over data; a `derive`
  is just a function over a `StructDecl`.
- **`std.ast`** — ergonomic, heap-allocating builders over `std.genc`'s reified AST, in
  fluent UFCS style, so the builder reads like the Zen it generates:

  ```zen
  var("x").dot("a").eq(var("y").dot("a"))   // builds the AST for `x.a == y.a`
  ```

  The builders heap-allocate every node and copy every slice, so generated AST safely
  outlives the function that built it (no dangling `addr()` of a stack literal).
- **The header is a function** — `zen/std/c.zen`'s `libc() [Decl]` is exactly this shape: a
  function that returns the libc foreign bindings as AST, emitted by `genModule(libc())`.
  Bindings live in Zen, as data, never as compiler-special-cased C logic.

## Modules & imports
- An import is a destructuring of a module path — `{ a, b } = std.X` binds `a`, `b` from
  `zen/std/X.zen`. Visibility is the glued `*`: only `name*` declarations are reachable
  across files; importing a non-`*` name is a `Private` error.
- `zenc check`, `zenc build`, and `zenc run` resolve `std` imports from disk before parsing:
  **`zen/std/resolve.zen`** follows the program's import edges, gathers the transitive
  closure of `zen/std/*.zen` modules, strips the import lines, and concatenates each body
  exactly once (per-module dedup breaks cycles; a per-name pass keeps the first definition
  of each top-level name, so a cross-module clash like `string.free` vs `mem.free` resolves
  deterministically).
- Plain emit mode (`zenc file.zen` or stdin) remains flat and unvalidated: it expects an
  already-flattened module and writes C to stdout. `tools/loader/` still packages the same
  resolver as a standalone runnable driver.

## Diagnostics
- A type error carries its **structured location** (a `ns`+`(row,col)`), and the check
  report draws a **caret** under the offending column straight from that structure. Checked
  CLI modes reject on any type error; lower-level codegen can still operate on the accepted
  declarations.

## Pipeline
Checked commands run `resolve std imports (std.resolve) → scan (std.lex) → parse
(std.parse*) → check (std.check/check_validate) → emit C (std.genc) → cc`, all ordinary Zen
modules that the `zenc` binary runs and that compile themselves. `build`/`run` reject an
ill-typed program before linking.
Plain emit mode skips the std-import loader and validator and writes C for one flat module.

## Not yet (the honest gaps)
- Plain emit mode is still a flat-module C emitter, not the checked multi-module path.
- `zenc check`/`build`/`run` resolve `std.X` imports from the repo's `zen/std/`; a broader
  package/module system beyond that std-import closure is still future work.
- The self-hosted checker covers a real but **partial** slice of the language; growing it to
  full parity with what `zenlang` describes is the active arc.
- The allocating `map`/`filter` are `[i32]`-only; a generic version needs type-parameter `sizeof`
  (the `map_into`/`filter_into` forms are already generic).
- Two backends (`std.genc` for C, `std.genjs` for JS — the latter the computational subset).
  An LLVM backend and the one-structure surface syntax from [VISION](VISION.md) are the
  *direction*, not the current state.
