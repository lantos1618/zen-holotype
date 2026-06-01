# Features

What the language has and does today. ~2,890 LOC of compiler, 285 tests, compiles to C
via `cc`. (For the *why* — "structure is the constraint" — see [README](README.md); for
where it's headed, [VISION](VISION.md).)

## Type system
- **Primitives:** `i32`, `i64`, `u8`, `bool`, `void`, `str` (`str` is comptime-only).
- **Products** — structs: `Point: { x: i32, y: i32 }`.
- **Sums** — enums with optional payloads: `Shape: Circle(i32), Square(i32), Dot`
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
  `Vec.impl(Area) { … }` (no `trait`/`impl`/`for` keywords),
  structural conformance; trait methods dispatch through bounds, an unsatisfied bound is a
  type error.
- **Inference:** integer literals adapt to the expected type; return types inferred from
  bodies (across calls); `match` exhaustiveness enforced.

## Expressions & control flow
- Full operator set: `+ - * / %  ==  < > <= >=  && ||  !`, each operand-checked. `/` and `%`
  are C truncate-toward-zero (the comptime folder agrees), and `/ %` bind tighter than `+ -`.
- `match` with **literal patterns** (`i32`/`bool`), **payload binding** (`.Circle(v) => v`),
  exhaustiveness, and wildcards — usable as an expression *or* a statement (`?:` or `if/else`).
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
- `x := v` let-bindings; struct literals; enum constructors; field access; calls.
- **UFCS** — `x.f(a, b)` is sugar for `f(x, a, b)`: the receiver becomes the first argument.
  It desugars uniformly (checker, reachability scan, lowerer), so it resolves free functions and
  trait-bound methods identically to the free-call form, and chains (`5.inc().dbl()`).
- **Visibility** is a glued `*` on the name — `Vec*: { … }`, `area* = () { … }`, `Area*: { … }` —
  not a `pub` keyword (the [VISION](VISION.md) `name[*]` slot, made real). Bare name = private to
  its file, and **enforced**: another module importing a non-`*` name is a `Private` error.

## Systems / FFI
- **Foreign C bindings** — a function with **no body** binds the C symbol of the same name
  (`malloc = (n: i64) RawPtr<u8>`); no `extern` keyword. libc by bare name, headers auto-included.
- **`build.zen` is executed, not scraped** — `build(b)` runs at compile time through the
  comptime engine with `b` a live `Builder`, so `b.add` / `b.use` / `b.config` are real calls
  and helper functions, conditionals and computed values in the script are honoured.
  `b.config()` finalizes to a `Result<BuildConfig, BuildError>`.
- **Build flags from `build.zen`** — `Executable { …, cflags: ["-O2", "-g"], links: ["m"] }`
  threads through to `cc` (`-O2 -g … -lm`), for the exe and its tests.
- **Incremental builds** — the C is byte-deterministic, so `zen build` skips `cc` when the
  source it would emit is unchanged (the cc command is stamped in the `.c`, so flag changes
  bust the cache).
- **Dead-code elimination** — an executable emits only the functions reachable from its entry
  (generic instances and trait impls were already pruned; this extends it to plain functions).
  A `check`/library build still emits everything that type-checks.
- **Binding modules via the build object** — `c = b.use("libc")` in `build.zen` installs a
  bundled Zen binding module (bodyless fns) under the namespace `c`; code then `{ malloc, free } = c`.
  A foreign binding is just a Zen module of decls — the kernel only loads-a-module-as-a-namespace,
  no C-specific logic in the compiler.
- **Generating adapters** — a binding module can `@emit` its bindings instead of listing them: the
  reified `Ast` has an `Extern` `Decl` variant, so a generator produces `[Decl]` of bodyless C
  bindings, spliced + installed by `b.use` exactly like a static one. A translate-c adapter is this
  shape — parse a header, `@emit` one `Extern` per declaration (`bindings/gen_demo.zen` shows it).
- **Raw memory intrinsics:** `addr(x)`, `load(p)`, `store(p, v)`, `offset(p, i)`.
- Enough to build a **heap-allocating, growable `String`** on an allocator.

## Standard library (`std.*`)
- A third bundled category beside the comptime-only **prelude** and the FFI **bindings**:
  ordinary runtime Zen, importable from any file, **checked and lowered like your code**.
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
- **`std.genc` — a C backend written in Zen, run at RUNTIME.** It walks a **recursive** AST
  (ordinary lowered structs + enums — runtime values; a `Bin` holds `Ptr<Expr>` children) and
  emits C source into a `String`: `genC(f: Func) → String`. A function body is a `[Stmt]` (`Let`
  / `Return`), so it emits **whole function bodies**. A running zen program builds an AST and gets
  C source as a value — and that emitted C compiles and computes (the test closes the loop: zen
  emits `int32_t f(int32_t x) { int32_t y = (x + 5); return (y * y); }`, which is then compiled
  and run → `f(10) == 225`). The self-hosting seed: codegen is the language's own ordinary code,
  not the host's. (A subset today; the path is to grow it toward lowering zen in zen.)
- **Zero-cost ambient:** the helpers are templates/generics, so importing `std` emits
  nothing unless a program actually uses them (they inline at the call site).

## Comptime + metaprogramming — the AST is defined in Zen
- **`comptime(expr)`** — a dedicated pass evaluates pure Zen at compile time and folds the
  result into a constant.
- **`@emit(gen(reflect(T)))`** — a generator runs at comptime and **splices a real declaration**
  (free fn or trait impl) into your program, which is then checked and lowered like
  hand-written code.
- **The reified AST lives in Zen** (`prelude/derive.zen`). The compiler keeps only:
  - a **reflection kernel** — over types (`reflect`, `name_of`, `field_count`,
    `field_name_at`, `variant_count`, `variant_name_at`, `variant_has_payload`) and over
    traits (`reflect_trait`, `trait_method_name`, `trait_method_count`,
    `trait_method_name_at` — every method, not just the first), plus `concat` — and
  - a ~40-line **reifier** (Zen `Ast` value → real `ast.Fn`/`Impl`).
- **The `Ast` model is public**, so *you* can write generators, not just the prelude. A
  generator is an ordinary Zen fn returning `Decl` — so it's **type-checked against the
  `Ast`** (a malformed construction like `FuncData { nm: <i32> }` is a `str` mismatch at
  check time, not a crash at reify) — yet never lowered (it's comptime-only).
- **Five self-hosted derives, all ordinary Zen functions:**

  | derive | generates |
  |---|---|
  | `derive_zero` | a zero-constructor `() T { T { f0: 0, … } }` |
  | `derive_eq` | structural equality `(a, b: Ptr<T>) bool` |
  | `derive_tag` | the variant index `(e: E) i32 { match … }` |
  | `derive_payload` | extract the bound payload (or 0) |
  | `derive_tag_impl` | a trait **impl** for *any* single-method `(Self) i32` trait (trait + method name reflected), dispatched through a bound |

  ```zen
  { derive_eq } = prelude.derive
  @emit(derive_eq(reflect(Point)))   // -> bool Point_eq(Point const*, Point const*) { ... }
  ```

## Diagnostics
- A type error carries its **structured location** (a `Located` message holding `ns`+`(row,col)`),
  and the `check`/`build` report draws a **caret** under the offending column straight from that
  structure — no re-parsing of the formatted string. Each ill-typed function is reported
  independently (the rest still builds).

## Pipeline
`parse (tree-sitter) → trie → resolve → fold comptime → run emits → typecheck → lower to C → cc`,
driven by a `build.zen` written in the language itself. Ill-typed functions are reported and
excluded from codegen; the rest builds and runs.

## Not yet (the honest gaps)
- No modules beyond files.
- The allocating `map`/`filter` are `[i32]`-only; a generic version needs type-parameter `sizeof`
  (the `map_into`/`filter_into` forms are already generic).
- Trait reflection exposes method *names* (any arity), but not method *signatures* (param/return
  types) — so `derive_tag_impl` still assumes a `(Self) i32` shape.
- One backend (C). The kernel/backend split is designed for `gen.llvm`/`gen.js`; they don't
  exist (the `build.zen` `target` field is the slot, `native` the only value).
- The one-structure grammar from VISION is the *direction*, not the current syntax.
