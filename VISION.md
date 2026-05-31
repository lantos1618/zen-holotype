# Zen — the vision: **one structure**

> The current compiler (structs, enums, traits, generics, `fits()`) is **v1** — it proved
> *"structure is the constraint."* This is **v2**: take that to the end. There are no
> keywords, because there is only **one** kind of thing. A `{ }`. Everything else is how you
> read it.

## The one rule

Inside any `{ }`:

| you write | it means |
|---|---|
| `name : Type` | a **requirement** — a field, or a method signature. The *shape*. |
| `name = value` | a **provision** — a field value, a method body, a nested record. The *fill*. |

That's the whole grammar of declarations. From it, everything:

```
all `:`        → a trait / interface   (pure shape, nothing provided)
all `=`        → a module / value      (fully concrete)
mixed          → a struct with methods (some fields declared, some methods defined)
nested `{ }`   → a namespace
```

A record is **abstract** if any `:` is unprovided, **concrete** (instantiable) once every `:`
has an `=`. **That is impl:** filling a record's requirements.

## Products and sums

- **Product** — a record: `{ }`.
- **Sum** — a comma-list. A variant may carry a payload.

```zen
Vec   = { len: i32, cap: i32 }              // product
Shape = Circle = { r: i32 }, Square = { s: i32 }   // sum, payloads are records
Bool  = True, False                          // the smallest sum — this is why `if` doesn't exist
```

## Traits & impl are just completion — no keywords

```zen
Area = { area: (Ptr<@Self>) i32 }            // a trait = a record of requirements

Vec = Area {                                  // "impl Area" = complete its requirements
    len: i32
    cap: i32
    area = (v: Ptr<@Self>) i32 { v.len * v.cap }
}
```

No `trait`, no `impl`, no `for`. You extend a record and fill what's missing.

## Self & paths

- `@Self` — the **type** of the enclosing record (Rust's `Self`).
- `@self` — the **instance** (Rust's `self`). Fields are `@self.foo`; params are bare.
- `@self` is **lexical and relative**: it rebinds at every `{ }`. At file scope it's the module.
- Names are **paths into the one trie**. A file `core/vec.zen` is the record `vec`; you reach
  it as `vec.Vec` from anywhere — inside or out. *What you type is the path.*

## Visibility = structure (no `pub`, no `*`, no `@export`)

Attach a name to a scope and it **has a path** → it's public. Leave it bare and it has no node
→ it's private. Privacy is *where you put it*, checked by the same trie that resolves it.

```zen
multiplier = 2                  // bare → private to this file
vec.Tau    = 6                  // on the module → public, path = vec.Tau
```

## Control flow is postfix methods — no statements

`if`, `else`, `switch`, `for`, `while` do not exist. There are values, and methods on them.

```zen
// `match` — a postfix method; every arm is an expression, so match returns a value
describe = (e: Shape) i32 {
    e.match {
        Circle(c) => c.r,
        Square(s) => s.s,
    }
}

// no `if` — a Bool is a 2-variant sum, so branching IS match
sign = (n: i32) i32 { (n > 0).match { True => 1, False => 0 - 1 } }

// no `for` — iteration is a method taking a closure
[1, 2, 3].loop((i: i32) { @self.add(i) })
```

Arm separator is `=>` ("maps to") — `:` is taken by *declare*, `=` reads as assignment.

## A whole file, in the language

```zen
// core/vec.zen   — this record is `vec`

Vec = Area {
    len: i32
    cap: i32
    area = (v: Ptr<@Self>) i32 { v.len * v.cap }
}

Area = { area: (Ptr<@Self>) i32 }

scale = (n: i32) i32 { n * 2 }       // bare → private helper
```

```zen
// main.zen
run = (v: Ptr<vec.Vec>) i32 {
    v.area().match { 0 => 1, _ => v.area() }   // path access, postfix method, postfix match
}
```

## What's gone

`pub` · `*` · `@export` · `trait` · `impl` · `for` · `if` · `else` · `switch` · `for`-loops ·
`while` · `struct` · `enum` · `fn`/`proc`. **One construct, read four ways.**

## Open forks (not yet locked)

1. **Sum payloads** — `FooBar = { a: i64 }` (record) only, or also positional `FooBar(i64)`?
2. **Method receiver** — is `@self` implicit in every function-valued field of a record, or only
   when the body names it?
3. **Abstract rule** — a record is abstract *iff* it has ≥1 unprovided `:`. Confirm that's the
   instantiability gate.
4. **`@Self` in a trait** — `(Ptr<@Self>)` binds to the completing type at use. Variance/dispatch
   to be specified.
5. **Result/`Ok`** — is everything a `Result` (so bodies wrap in `Ok`), or only when annotated?

## v1 → v2

v1 is a working, tested compiler for a keyword-ful subset. v2 is this. The migration is a
front-end rewrite (one record grammar) plus folding struct/enum/trait/impl/visibility into the
trie — but the back end (monomorphize → C) and `fits()` lattice **carry straight over**: a
record is still a product, a sum is still a tagged union, a method is still a trie node.
