# Metaprogramming in Zen — reflection through generics, not `comptime`

## Thesis — now proven in tree

Zen does **not** have (and does not want) a `comptime { ... }` block. Reflection rides
the mechanism we already had: **generic monomorphization**. A generic function `foo<T>`
is evaluated per concrete `T` at compile time (that's how `sizeof(T)` works), so the
metaprogram *is* an ordinary generic function whose body looks at `T`'s structure —
reflect-and-run (serialize, compare, fill a struct from JSON) or reflect-and-emit
(build a `Decl`, hand it to `genModuleIn`).

Everything is a value of an **already-defined type** — no stringly-typed API, no magic
pragma surface. This was the design bet when this doc was written; it is now **shipped
and load-bearing**: three reflection intrinsics, derived struct equality, and a pure-
library JSON serde all work on main.

## What exists today

### 1. Struct-reflection intrinsics (Phases 1+2) — SPEC.md "Struct Reflection"

Three intrinsics expand at inline time, once the receiver's concrete struct type is
known, into ordinary field expressions — zero runtime cost:

- `x.field_eq(y)` — per-field `==` fold; **recursive** (struct-typed fields fold into
  their own compare), strings by content.
- `x.each_field(f)` — unrolls to one inlined call of `f(name, value)` per field.
  `name` is the field's name as a string literal; `value` is statically typed as that
  field, so each unrolled lambda copy is checked against the field's own type
  (Zig `inline for` / Nim `fieldPairs`).
- `x.zip_fields(y, f)` — the paired form: `f(name, x_value, y_value)` per field.

Real syntax (see `tests/fixtures/zen/each_field_unroll.zen` for the full exercised
corpus — generic-struct receivers, receiver-evaluated-once, name matching):

```zen
sum_fields<T> = (v: T) i64 {
    acc :: i64 = 0
    v.each_field((name, fv) { acc = acc + fv })
    acc
}

diff_count<T> = (x: T, y: T) i64 {
    d :: i64 = 0
    x.zip_fields(y, (name, va, vb) {
        (va == vb == false).then({ d = d + 1 })
    })
    d
}
```

Generic-struct receivers (`Box<i64>`) reflect with the instance's type arguments
substituted. Ill-formed shapes are rejected with positioned diagnostics (non-struct
receiver, wrong-shape lambda, self-recursive reflect body → `error[recursive-hof]`).

### 2. Derived struct equality (#577) — SPEC.md "Struct Equality"

`==` / `!=` between two values of the same struct type compare structurally. An `eq`
method provided by an impl on the type **wins**; otherwise the compiler derives a
per-field `==` fold via the same reflection machinery — strings by content, enums by
tag, struct fields recurse, pointers by identity, operands evaluated exactly once.
This is the promised `eq<T>` "falls out of the primitives" — it fell out.

```zen
Point: { x: i64, y: i64 }
p == q                          // derived per-field fold

Tagged.impl(EqOps, {
    eq = (a: Tagged, b: Tagged) bool { a.id == b.id }
})
t1 == t2                        // the impl wins over the derived fold
```

### 3. jsony-style serde as pure library code (Phase 3, #584) — `src/std/format/serde.zen`

`to_json(a, v)` / `from_json(a, s, seed)` are ordinary generic library functions — no
compiler serde support, no per-type impls for structs. Field names become JSON keys via
`each_field`; per-field serialization dispatches through `JsonWrite` impls on the scalar
types. The key deserialization insight: **an `each_field` lambda parameter substitutes to
a real member PLACE**, so `fv = ...` inside the lambda assigns the struct's field — which
is why `from_json` needed **no new intrinsic**.

```zen
{ to_json, from_json } = std.format.serde
{ heap_allocator } = std.mem.alloc
da = heap_allocator()
to_json(da.addr(), Point(x: 3, y: 4))          // .Ok("{\"x\":3,\"y\":4}")
from_json(da.addr(), s, Point(x: 0, y: 0))     // .Ok(Point(x: 3, y: 4)); seed = defaults
```

Errors are values throughout (builder OOM latches into a threaded state → `.Err`;
malformed JSON is the parser's `.Err(JsonError)`).

### 4. Enum-reflection intrinsic — SPEC.md "Enum Reflection"

`e.variant_name()` is the enum mirror of `each_field`: the inliner expands it, once the
receiver's concrete enum type is known, into an ordinary match yielding one string literal
per variant. Zero runtime cost, no allocation, no name table — the emitted C is identical
to the hand-written match it replaces.

```zen
Level: Debug | Info | Warn | Error
tag = (l: Level) StringView { l.variant_name() }   // .Debug => "Debug", .Info => "Info", …
```

The name is VERBATIM by design. Case folding was deliberately left out: it is a runtime
string operation that allocates, and hiding a heap allocation behind a reflection intrinsic
that otherwise returns a borrowed view would contradict the no-implicit-allocation rule
([MEMORY_MODEL.md](MEMORY_MODEL.md)). The declaration is the single source of truth for
the spelling; a caller who wants another one transforms it explicitly.

Five stdlib converters now delegate to it (`std.core.result.name`, `std.text.str
.parse_error_name`, `std.text.regex.error_name`, `std.time.datetime.error_name`,
`std.argparse.ap_error_name`) — the `error_name` boilerplate that every new error enum
was reproducing by hand.

### 5. Reflect-and-emit — worked before, still works

The AST types (`Decl`, `Ty`, `Param`, `Field`, `StructDecl`, `EnumDecl`, `VariantDef`)
are real and exported by `std.internal.ast`; `compiler.genc.genModuleIn` emits a
`MutSlice<Decl>` to C. Building a companion decl from a reflected struct (derive-accessors,
derive-eq style) works as a build program today.

## Remaining — known limits and future intrinsics

**Composition limits (issues #586, #588).** The intrinsics compose less freely than
plain generics; today's sharp edges, all documented at the top of
`src/std/format/serde.zen`:

- **One-wrapper limit**: at most one plain generic may wrap a reflection generic
  (`to_json` wraps `jw_obj1`); a second wrapper layer absorbs the intrinsic one
  pipeline pass too late and its calls die at C link time (#588).
- **Same-name ladder recursion** (impl-owned scalar dispatch + same-named free generic
  struct fallback) poisons the two-pass resolve→inline pipeline — dead splices or bare
  un-emitted template calls surface as C errors instead of diagnostics (#586).
- **Syntactic `recursive-hof`**: the self-recursion check is name-based, so mixed
  scalar/struct fields at one level can't be handled by one recursive `dump<T>` yet —
  hence `to_json` (flat structs) vs `to_json_nested` (two homogeneous levels) as
  separate entry points (#588).

**Place-semantics soundness (in flight: #585, #587).** Spliced lambda params aliasing
the caller's variable (#585) and non-`Var` reflection subjects being temp-bound so
nested field writes silently vanish (#587) are open soundness holes in the
member-place substitution that `from_json` relies on.

**Still-future intrinsics.** `each_variant<E>(f)` — the enum mirror of `each_field`, for
building a name→variant table or a derived parser — is NOT built: nothing in tree wants it
yet (every hand-written enum→text converter is one-directional), and a per-variant unroll
with no value to bind needs a shape decision (`f(name)` alone? a constructed variant, which
payload-carrying variants cannot supply?). It falls out of the same hook when a caller
needs it. `typeinfo(T)` / `a.type` (a *matchable* `Ty` descriptor —
`.Bool`, `.I32`, `.Struct(fields)`, `.Enum(variants)`) and `fields_of<T>()` (field list
without a value, for reflect-and-emit inside a generic) remain unbuilt. They are what
would replace serde's impl-dispatch workaround with a direct type-switch, and what the
`recursive-hof` fix needs to make one `dump<T>` handle every shape. Same rule as
everything above: kinds and types are enum variants from the real AST types, never
strings.

**The ORM sketch — still the target application.** Drizzle-style, schema *is* a struct:

```zen
User: { id: i32, name: StringView, active: bool }   // the table = a plain struct

users = table<User>("users")   // reflect fields -> columns; SQL type from each field's Ty

adults = db.from(users)
    .where(users.col(.active).eq(true))    // typed column ref, not "active"
    .order_by(users.col(.name))
    .select()                              // -> MutSlice<User>, rows scanned back via reflection

db.insert(users, User(id: 1, name: "ada", active: true))   // fields -> bind params
```

`insert`/`select` row mapping is expressible with today's `each_field`/`zip_fields`;
the typed column selector `.col(.name)` and SQL-type-from-`Ty` derivation want
`typeinfo(T)`/`fields_of<T>()`. One reflection mechanism powers schema derivation,
column typing, bind params, and row scanning — one source of truth (the struct).

## Scorecard

- ✅ Reflection rides generics, mono-time, zero runtime cost — shipped, proven by serde.
- ✅ No `comptime` block — none was needed for equality or JSON serde.
- ✅ No stringly-typed API — field names surface as string *literals* to statically
  typed lambdas; kinds/types stay enum variants.
- ✅ Derive-class features as library code: `eq` (compiler-derived `==`), `to_json` /
  `from_json` (`std.format.serde`), enum `variant_name` (five stdlib converters deleted).
- ⛔ Free composition of reflection generics (#586/#588) and place-semantics soundness
  (#585/#587) — the active work.
- ⛔ `typeinfo(T)` / `fields_of<T>()` — the remaining intrinsics; unlock type-switch
  dispatch, one-function recursive serde, and the ORM's typed columns.
