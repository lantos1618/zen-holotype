# The String and Vec model

`String` is `Vec<u8>`. Not "like" it — the structs are byte-for-byte identical today:

```zen
Vec*<T>: { ptr: RawPtr<u8>, len: i64, cap: i64 }
String*: { ptr: RawPtr<u8>, len: i64, cap: i64 }
```

So there is one model, over an element type, and text is the `u8` case of it. Five roles, five
names, no special cases.

## The five

| name | representation | mutable | grows | size known | allocator | freed by |
|---|---|---|---|---|---|---|
| `VecLiteral<T>` / `StringLiteral` | `{ptr}` → `.rodata` | no | no | **compile time** | no | never |
| `VecConst<T>` / `StringConst` | `{ptr, len}` | no | no | runtime | to create | **you** |
| `VecFixed<T>` / `StringFixed` | `{ptr, len}` | **yes** | no | runtime, fixed at creation | to create | **you** |
| `Vec<T>` / `String` | `{ptr, len, cap}` | yes | **yes** | runtime, changes | **yes** | **you** |
| `VecView<T>` / `StringView` | `{ptr, len}` | no | no | runtime | no | **not yours** |

Three axes decide the row, and every combination that makes sense has a name:

- **ownership** — static, owned, or borrowed
- **mutability** — can you write through it
- **growth** — is there a `cap` to grow into

`cap` is the whole difference between `Vec` and everything else. It is where spare room is
recorded; without it there is nowhere to put the answer to "how much space is left", so growth
is impossible by construction rather than by convention.

`VecConst`, `VecFixed` and `VecView` are all `{ptr, len}` — the same two machine words. They
differ only in what the checker will let you do. That is the good kind of type: it changes what
compiles and changes nothing about what runs.

## Creating them

```zen
gpa = mem.gpa()

// StringLiteral — no allocator, no ceremony; it is already in the binary.
name := "zen"

// StringView — borrows. Costs nothing, frees nothing, accepts anything.
v    := name.view()
part := name.slice(0, 2)                        // a sub-view: still zero allocation

// StringFixed — state the size once. Writable, never grows.
buf := gpa.string_fixed(64).or_return()
buf.set(0, 'h')

// String — the only one whose length is not decided at creation.
s := gpa.string(16).or_return()
s.add("hello").add(" world")

// StringConst — owned but frozen. Not built directly: build a String, then give up
// the right to change it.
frozen := s.freeze()
```

`Vec<T>` is the same five, with an element type:

```zen
xs      := [1, 2, 3]                            // VecLiteral<i64>
view    := xs.view()                            // VecView<i64>
scratch := gpa.vec_fixed<i64>(64).or_return()   // VecFixed<i64>
v       := gpa.vec<i64>(16).or_return()         // Vec<i64>
v.add_one(1)
locked  := v.freeze()                           // VecConst<i64>
```

## Conversions

```
literal ──copy(a)──▶ String ──freeze()──▶ StringConst
                       │                      │
                       │  .view()             │  .view()
                       ▼                      ▼
                        ─── StringView ───────
```

**`.view()` is free from every row and always yields the same type.** That is why `StringView`
is the correct parameter type for anything read-only: it accepts literals and all three owned
kinds with no conversion at any call site, and the signature promises the function cannot
allocate or free.

**`freeze()` shrinks to fit and gives up growth.** A `String` carries `cap >= len`; freezing
returns the slack to the allocator and yields a type with no `cap`. One realloc buys memory back
and an immutability guarantee.

**There is deliberately no `thaw()`.** Going back means copying, so it is spelled
`gpa.string_from(frozen)` — the allocation is visible because the allocator is named.

## Naming rules

**Prefix, not natural word order.** `StringFixed`, not `FixedString`. The shared prefix groups
the family in a flat namespace and in autocomplete, and the flat namespace is the constraint that
matters here — every top-level name is global.

**`add`, not `append`.** Shorter, and it reads identically for both:

```zen
s.add("hello")
v.add(other)
```

**`add` means many; `add_one` means one.** Zen has no function overloading, so `add` can only
mean one thing, and `String = Vec<u8>` forces `Vec` and `String` to agree. The frequent case wins:
`s.add("hello")` is written constantly, `v.add_one(5)` rarely. Optimising the common case is the
same reasoning that chose `add` over `append`.

**Text-specific API stays on the text type.** `split`, `trim`, `to_upper` are string-shaped and
belong to `String`. `add`, `view`, `freeze`, `drop` are `Vec` operations that `String` inherits by
being `Vec<u8>`.

## What exists today, and what this model needs

**Real now:** `String`, `Vec<T>`, views (as `[T]`), the `(a: Allocator)` sugar, `or_return`,
sticky-error chaining (as `std.text.sb`).

**Exists but misnamed:** three internal types, now with exactly three surface spellings —
`string_literal`, `string_view`, `string_cstr` — each of which a diagnostic prints as itself.
(The `str`, `text` and `Cstr` aliases are gone.) The names are still the old ones, so the
CamelCase rename to `StringLiteral`/`StringView` remains ahead.

**Does not exist:** `StringConst`, `StringFixed`, `VecConst`, `VecFixed`, `freeze()`.

### Two language changes gate the missing rows

**1. Slices need a mutability bit.** `Ty` spells pointers as `Ptr` / `MutPtr` / `RawPtr`, but
slices are `Slice(elem)` with no read/write distinction — so every `[T]` is writable. That is why
this compiles and then segfaults:

```zen
s: string_cstr := "hello"
v: [u8] := s.view()      // .view() launders const away
v[0] = 'H'               // writes into .rodata
```

`zen check` accepts it. Until a slice can be immutable, `StringConst` and `StringFixed` cannot be
told apart from `StringView`, and immutability has nowhere to live once you take a view.

**2. The allocator decision.** `s.freeze()` and `s.drop()` taking no argument require the
container to carry its allocator. Today the rule is: **carry the allocator and you give up
errors-as-values** (`AVec`/`ASet`/`AHMap` store a `DynAlloc` and panic); **thread it and you keep
them** (`Vec`/`String` return `Result`). `std.text.sb` is the single type that does both, via a
sticky error flag settled once at `done()` — which is the shape this model assumes.

Deciding that for `String` also decides `AVec`: it either becomes the default or disappears.

## Why this is worth the churn

One set of rules instead of two. `cap` means growable everywhere; `View` means borrowed
everywhere; `Fixed` means sized-once-and-writable everywhere. Learn it for `Vec<i64>` and you
already know `String`.

And it makes the dangerous cases unrepresentable rather than merely discouraged: a function taking
`StringView` cannot free its argument, a `StringConst` cannot be written through, and a
`StringFixed` cannot silently reallocate under a view someone else is holding.
