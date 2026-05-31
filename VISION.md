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
| `name = value` | a **provision** (const) — a field value, a method body, a nested record. |
| `name := value` | a **provision** (mutable). |

(`*` after the name = public; full table under **Declarations** below.) From this, everything:

```
all `:`        → a trait / interface   (pure shape, nothing provided)
all `=`        → a module / value      (fully concrete)
mixed          → a struct with methods (some fields declared, some methods defined)
nested `{ }`   → a namespace
```

A record is **abstract** if any `:` is unprovided, **concrete** (instantiable) once every `:`
has an `=`. **That is impl:** filling a record's requirements.

## Products and sums

The separator *is* the distinction — `,` inside `{ }` is **AND** (product); `|` is **OR** (sum):

- **Product** — a record: `{ a: T, b: T }`.
- **Sum** — a `|`-list of variants. A variant carries its payload with `:` (a payload is a type).

```zen
Vec   = { len: i32, cap: i32 }              // product: has len AND cap
Bool  = True | False                         // sum: the smallest one (why `if` doesn't exist)
Shape = Circle : { r: i32 } | Rect : { w: i32, h: i32 } | Point
Opt<T> = None | Some : T                     // generic sum
```

Matching tears a sum back down — the same record syntax both ways:

```zen
area = (s: Shape) i32 {
    s.match {
        Circle(c) => c.r * c.r * 3,
        Rect(r)   => r.w * r.h,
        Point     => 0,
    }
}
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

## Declarations — the one grammar

Every declaration — field, const, var, fn, type, method, requirement — is one line:

```
name  [*]   [ : Type ]   ( =  |  := )   value
  │    │         │           │
 name pub      label   = const · := mutable     (omit operator+value → a requirement)
```

Four independent slots, nothing special-cased:

| | private | public (`*`) |
|---|---|---|
| **requirement** (no value) | `Foo : i32` | `Foo* : i32` |
| **const**, inferred | `Foo = 0` | `Foo* = 0` |
| **const**, typed | `Foo : i32 = 0` | `Foo* : i32 = 0` |
| **mutable**, inferred | `Foo := 0` | `Foo* := 0` |
| **mutable**, typed | `Foo : i32 := 0` | `Foo* : i32 := 0` |

- **`=` const · `:=` mutable** — the operator is the whole mutability story (no `let`/`var`/`mut`).
- **no operator** (just `: T`) → a *requirement* — the abstract `:` of a record (a field / method sig).
- **`*` = public surface.** `name* = …` attaches the name to the enclosing record (gives it a path);
  bare `name = …` keeps it local (no path). So `*` *is* the structural visibility, made explicit —
  not capitalization (case is already taken: `Vec` is a type, `area` a value).

It's the same for everything:

```zen
Vec*  = { len: i32, cap: i32 }          // public type
tau*  : i32 = 6                          // public const
count*       := 0                        // public var
area* = (v: Ptr<@Self>) i32 { … }        // public fn
scale =       (n: i32) i32 { … }         // private fn
area  : (Ptr<@Self>) i32                 // a requirement (the trait part)
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

`pub` · `@export` · `trait` · `impl` · `for` (the keyword) · `if` · `else` · `switch` ·
`while` · `for`-loops · `let`/`var`/`const`/`mut` · `struct` · `enum` · `fn`/`proc`.
**One construct, read four ways.** (`*` stays — it's the one mark, for public surface.)

## Open forks (not yet locked)

1. **Sum payloads** — `FooBar = { a: i64 }` (record) only, or also positional `FooBar(i64)`?
2. **Method receiver** — is `@self` implicit in every function-valued field of a record, or only
   when the body names it?
3. **Abstract rule** — a record is abstract *iff* it has ≥1 unprovided `:`. Confirm that's the
   instantiability gate.
4. **`@Self` in a trait** — `(Ptr<@Self>)` binds to the completing type at use. Variance/dispatch
   to be specified.
5. **Result/`Ok`** — is everything a `Result` (so bodies wrap in `Ok`), or only when annotated?

## Grammar sketch (v2)

The whole front end is small because there's one declaration shape. (EBNF-ish; the real
tree-sitter grammar comes when we build v2 — v1's `grammar.js` stays the working one until then.)

```
file        = decl*                                  // a file is the outermost record body
decl        = name "*"? (":" type)? ( ("=" | ":=") value )?   // the one grammar (see table)
name        = ident
type        = record | sum | path | "Ptr<" type ">" | prim | "@Self"
record      = "{" decl* "}"                           // product
sum         = variant ("," variant)*                  // sum;  a variant may carry a payload
variant     = ident ("=" record)?                     //   FooBar = { a: i64 }
value       = record | sum | fn | expr
fn          = "(" param,* ")" type? block             // params + optional ret + body
param       = name ":" type
block       = "{" stmt* "}"
expr        = literal | path | call | postfix | binop
postfix     = expr "." name args?                     // field access / method call (x.area())
            | expr "." "match" "{" arm,* "}"           // match is a postfix method
arm         = pattern "=>" expr
pattern     = variant_pat | literal | "_"
path        = name ("." name)*                        // vec.Vec, @self.foo, @Self
```

Everything above resolves into the **same trie**: a `record` is a subtree, a `path` is a walk,
a method is a node, visibility is "does it have a node." No separate symbol table, no IR.

## v1 → v2

v1 is a working, tested compiler for a keyword-ful subset (145 tests green). v2 is this. The
migration is a front-end rewrite (the one record grammar above) plus folding
struct/enum/trait/impl/visibility into the trie — but the back end (monomorphize → C) and the
`fits()` lattice **carry straight over**: a record is still a product, a sum is still a tagged
union, a method is still a trie node. **v1 stays green the whole way; v2 grows beside it.**
