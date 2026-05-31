# Features

What the language has and does today. ~2,140 LOC of compiler, 178 tests, compiles to C
via `cc`. (For the *why* — "structure is the constraint" — see [README](README.md); for
where it's headed, [VISION](VISION.md).)

## Type system
- **Primitives:** `i32`, `i64`, `u8`, `bool`, `void`, `str` (`str` is comptime-only).
- **Products** — structs: `Point: { x: i32, y: i32 }`.
- **Sums** — enums with optional payloads: `Shape: Circle(i32), Square(i32), Dot`
  (lowered to C tagged unions).
- **Pointers, three kinds, with a real subtyping lattice:** `Ptr<T>` (read-only),
  `MutPtr<T>` (writable), `RawPtr<T>` (untyped, for FFI). `fits()` enforces direction
  (`MutPtr ≤ Ptr`), nullability (`T ≤ Option<T>`, no bare null), invariant writable
  pointees, and integer widening (`u8 ≤ i32 ≤ i64`). All of it erases to plain C.
- **Generics:** `Box<T>`, bounded `<T: Area>` — unification + **monomorphization** to
  concrete C.
- **Traits & impls:** `trait Area { area: (Ptr<Self>) i32 }` + `impl Area for Vec { … }`,
  structural conformance; trait methods dispatch through bounds, an unsatisfied bound is a
  type error.
- **Inference:** integer literals adapt to the expected type; return types inferred from
  bodies (across calls); `match` exhaustiveness enforced.

## Expressions & control flow
- Full operator set: `+ - *  ==  < > <= >=  && ||  !`, each operand-checked.
- `match` with **literal patterns** (`i32`/`bool`), **payload binding** (`.Circle(v) => v`),
  exhaustiveness, and wildcards.
- **`while` loops** and **mutation** — `x = 5` (reassign a local), `s.f = v` (set a field
  through a `MutPtr`).
- **Recursion** (so with literal-pattern `match`, it's Turing-complete — `fact`/`fib` run).
- `x := v` let-bindings; struct literals; enum constructors; field access; calls.

## Systems / FFI
- **`extern`** C bindings (binds libc by bare name; libc headers auto-included).
- **Raw memory intrinsics:** `addr(x)`, `load(p)`, `store(p, v)`, `offset(p, i)`.
- Enough to build a **heap-allocating, growable `String`** on an allocator.

## Comptime + metaprogramming — the AST is defined in Zen
- **`comptime(expr)`** — a dedicated pass evaluates pure Zen at compile time and folds the
  result into a constant.
- **`emit gen(reflect(T))`** — a generator runs at comptime and **splices a real declaration**
  (free fn or trait impl) into your program, which is then checked and lowered like
  hand-written code.
- **The reified AST lives in Zen** (`prelude/derive.zen`). The compiler keeps only:
  - a **reflection kernel** — over types (`reflect`, `name_of`, `field_count`,
    `field_name_at`, `variant_count`, `variant_name_at`, `variant_has_payload`) and over
    traits (`reflect_trait`, `trait_method_name`), plus `concat` — and
  - a ~40-line **reifier** (Zen `Ast` value → real `ast.Fn`/`Impl`).
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
  emit derive_eq(reflect(Point))     // -> bool Point_eq(Point const*, Point const*) { ... }
  ```

## Pipeline
`parse (tree-sitter) → trie → resolve → fold comptime → run emits → typecheck → lower to C → cc`,
driven by a `build.zen` written in the language itself. Ill-typed functions are reported and
excluded from codegen; the rest builds and runs.

## Not yet (the honest gaps)
- No `for`/iterators, closures, modules beyond files, or first-class **runtime** strings.
- Generators aren't **type-checked against the Zen `Ast`** — they run comptime-dynamically.
- Trait reflection is single-method only, and assumes a `(Self) i32` shape (no full
  method-signature reflection yet).
- One backend (C). The kernel/backend split is designed for `gen.llvm`/`gen.js`; they don't
  exist.
- The one-structure grammar from VISION is the *direction*, not the current syntax.
