# Zen — the vision: **one structure**

> The compiler today (structs, enums, traits, generics, `fits()`, a self-hosted front end +
> C/JS backends, metaprogramming as AST values) proves *"structure is the constraint."* This
> document is where it's headed: take that to the end, until there are no keywords — because
> there is only **one** kind of thing. A `{ }`. Everything else is how you read it.

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

## Grammar sketch (the one-structure direction)

The whole front end gets small because there's one declaration shape. (EBNF-ish; the
self-hosted parser `std.parse*` accepts the keyword-ful form today — this is the shape it
collapses toward.)

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

## Today → the direction

The compiler today is a working, tested one for a keyword-ful surface (`trait`, `impl`,
`Name: { }`) — though visibility is already the VISION's glued `*` (`Vec*`, `area*`), not a `pub`
keyword. Getting to the one-structure form above is a front-end change — fold
struct/enum/trait/impl/visibility into the trie under the single `decl` shape — while the back
end (monomorphize → C) and the `fits()` lattice **carry straight over**: a record is still a
product, a sum is still a tagged union, a method is still a trie node. The grammar evolves in
place; there is **one** language, growing toward its own end state — not two.

## The architecture: kernel + backends + Zen generators

The compiler does exactly **two** things — *check that structure fits*, and *hand off a checked
AST*. Everything else plugs in. (It is already self-hosted: kernel and backends are all Zen.)

```
                         ┌──────────────────────────────────┐
   text ──parse──► AST ──►  trie · fits()                    ──► CHECKED AST
                         └────────────────┬─────────────────┘
                                          │  one structure, many emitters
              ┌──────────┬────────────────┼────────────────┬──────────┐
              ▼          ▼                ▼                ▼          ▼
           gen.c     gen.llvm          gen.js           gen.json   gen.???
```

The three layers and the contract between them:

```
kernel   :  text       → CheckedAst      // parse + trie + fits
backend  :  CheckedAst → target          // gen.c (std.genc) / gen.js (std.genjs) / gen.llvm / …
generator:  () → [Decl]  (in Zen)        // a function that BUILDS AST and returns it
```

- The **kernel** never knows about C, JS, or LLVM. It produces a *checked, resolved* AST —
  structure that has been proven to fit. It only ever answers "does this fit?".
- A **backend** is a walk over that AST emitting a target. `gen.c` exists (`std.genc`), and a
  JavaScript one (`std.genjs`) walks the *same* AST; `gen.llvm` / `gen.json` are *more of the
  same* — each keeps its own variable/type tables, but never re-checks, because the kernel
  already did. **New target = new backend.**
- **Metaprogramming is Zen, as values** (not pragmas). A generator is an ordinary function
  that builds AST values and returns `[Decl]`, emitted by `std.genc.genModule`; `std.ast`
  gives the fluent builders. There is no `@emit` and no comptime evaluator — code is data, so
  generating it is just a function over data. **New feature = new generator**, not compiler
  code.

So the kernel stays tiny *forever*: it checks structure and emits; targets and features both live
outside it. **Structure is king** — data is shape, behavior is functions over shape, and code is
shape too (the AST), so one checker + a row of emitters is the entire compiler.

### Roadmap

1. **Self-host** — define the AST in Zen (`std.genc`) and write the whole front end in Zen
   (`std.lex` / `std.parse*` / `std.check`). ✅ The compiler compiles itself to C and reproduces
   its committed C byte-for-byte (the fixpoint); Python and tree-sitter are gone.
2. **Metaprogramming as values** — generators that build `[Decl]` and emit via `genModule`,
   with `std.ast`'s builders. ✅ (`std.c`'s `libc()` is the canonical example: a function that
   returns its bindings as AST.) *Remaining: grow the self-hosted checker to full language parity.*
3. **the one-structure grammar** — collapse the keyword-ful surface into the single `decl` shape
   (fold struct/enum/trait/impl/visibility into the trie). Same back end, same `fits()`.
4. **more backends** — `gen.llvm`, a richer `gen.js` — each just another walk over the same CheckedAst.

### How a generator works today (the self-hosted loop)

```
  generator.zen:   libc = () [Decl] { [ ffi("malloc", …), ffi("free", …), … ].dup() }

  emit       :     genModule(libc())  ─►  C prototypes for the whole binding set
```

A generator is **ordinary Zen** (`std.c`, built on `std.ast`/`std.genc`): it reads or builds
structure and returns AST values, which `genModule` lowers to C — the same backend that lowers
hand-written code. The shape of every node — `Int`, `Bin`, `Struct`, `Func`, the field/param
lists — is **defined in Zen** (`std.genc`). New generator = new Zen function, not compiler code.
