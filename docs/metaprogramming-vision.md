# Metaprogramming in Zen — reflection through generics, not `comptime`

## Thesis

Zen does **not** want a `comptime { ... }` block. Reflection should ride the mechanism
we already have: **generic monomorphization**. A generic function `foo<T>` is already
evaluated per concrete `T` at compile time (that's how `sizeof(T)` works). So the
metaprogram *is* an ordinary generic function that can look at `T`'s structure and act
on it — reflect-and-run (serialize, bind a SQL row) or reflect-and-emit (generate a
`Decl` and hand it to `genModuleIn`).

Everything is a value of an **already-defined type** — no stringly-typed API. Kinds are
enum variants (`.DFunc`, `.DEnum`, `.Struct`), types are the real `Ty` enum
(`.Bool`, `.I32`, `.Ptr`, `.Slice`), not `"func"`/`"bool"`.

## The two primitives (the whole feature)

Both are monomorphization-time, like `sizeof(T)` — zero runtime cost, no reflection at
run time (an `insert<User>` compiles to three `bind_*` calls, nothing reflective).

1. **`typeinfo(T)` / `a.type`** — a *matchable* type descriptor. The checker already
   holds a `Ty` for every `T`, plus the `StructDecl.fields` / `EnumDecl.variants` behind
   a `Named` type. The missing piece is exposing that to a generic body as a value:
   ```zen
   a.type.match ({ .Bool => ..., .Struct(fields) => ..., .Enum(variants) => ... })
   ```
2. **`fields(a)` / `fields_of<T>()`** — per-field iteration yielding `(name, typed value)`,
   *unrolled* at mono time (Zig's `inline for`, Nim's `fieldPairs`). The field list is a
   compile-time constant for a concrete `T`, so the loop expands to typed field accesses.

The AST types (`Decl`, `Ty`, `Param`, `Field`, `StructDecl`, `EnumDecl`, `VariantDef`)
are real and already exported by `std.internal.ast`; `compiler.genc.genModuleIn` already
emits a `[Decl]` to C. So **reflect-and-emit works today** as a build program; the two
intrinsics above are what make **reflect-in-place** (`foo<T>` over your own types)
ergonomic.

## Example 1 — jsony-style serialize, auto-derived (no per-type impl)

```zen
dump<T> = (a: T, out: MutPtr<String>) void {
    a.type.match ({
        .Bool        => out.s(a.match({ true => "true", false => "false" })),
        .I32 | .I64  => out.int(a),
        .StringView  => out.quoted(a),
        .Struct(_)   => {
            out.ch('{')
            fields(a).loop((h, i, fv) {          // fv.val is statically typed as its field
                (i > 0).then({ out.ch(',') })
                out.quoted(fv.name)  out.ch(':')
                dump(fv.val, out)                // recurse on the field's own type
            })
            out.ch('}')
        },
        .Enum(_)     => a.variant.match ({
            .Unit(name)       => out.quoted(name),
            .Payload(name, p) => { out.ch('{')  out.quoted(name)  out.ch(':')  dump(p, out)  out.ch('}') },
        }),
        .Slice(_)    => { out.ch('[')  a.loop((h, i, x) { (i>0).then({out.ch(',')})  dump(x, out) })  out.ch(']') },
    })
}
```

`parse<T>` is the inverse walk (this is jsony's `parseHook`). Same for `eq<T>`,
`hash<T>`, `debug<T>` — all fall out of the same two primitives.

## Example 2 — Drizzle-style ORM (schema *is* a struct)

```zen
User: { id: i32, name: string_view, active: bool }   // the table = a plain struct

users := table<User>("users")   // reflect fields -> columns; SQL type from each field's Ty

// type-safe fluent query; .active is a typed column ref, not "active"
adults := db.from(users)
    .where(users.col(.active).eq(true))    // .eq(true) type-checks true : bool
    .order_by(users.col(.name))
    .select()                              // -> [User], rows scanned back via reflection

db.insert(users, User(id: 1, name: "ada", active: true))   // fields -> bind params
```

One reflection mechanism powers schema derivation, column typing, `insert` binding, and
`select` scanning — the schema, the query types, and the row mapping are one source of
truth (the struct). The SQL type of a column comes from matching the field's real `Ty`:

```zen
sql_ty := f.ty.match ({ .I32|.I64 => .Int, .Bool => .Bool, .StringView => .Text, .F64 => .Real, _ => .Blob })
```

## Example 3 — reflect-and-emit (build a `Decl`, inject a type)

The `: Node`-returning form: reflect `T`, build a `Decl`/`Stmt`, emit it.

```zen
derive_table<T> = () Decl {
    cols := fields_of<T>().map((f) { Field(name: f.name, ty: f.ty) })
    // build a StructDecl for the companion table + typed Column per field, then:
    .DStruct(StructDecl(name: /* T's name + "Table" */, fields: cols))
}
// genModuleIn([...derive_table<User>()...]) emits it — this works today via std.internal.ast.
```

## Status / what to build

- ✅ Reflect-and-emit as a build program: works now (`std.internal.ast` + `genModuleIn`;
  see the existing `derive_accessors` / `derive_eq` that already loop `StructDecl.fields`).
- ⛔ The bounded feature: `typeinfo(T)` (matchable descriptor) + `fields(a)` (typed unrolled
  field iteration) + a typed field-selector for `.col(.name)`. All ride monomorphization
  like `sizeof(T)`; the checker already has the data. No `comptime` block, no runtime cost.

This one lever unlocks **derive, serde, ORM, equality, hashing, debug** from ordinary
`foo<T>` functions — the "everything is a type / metaprogramming as values" direction.
