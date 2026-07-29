# The String and Vec model

> **How to read this document.** Sections marked **TARGET MODEL** describe where
> the string/vec family is going. They are written in the present tense because
> that is how the design reads best, but they are **not** a description of the
> current tree, and code copied out of them may not compile. The one section
> that is a report on the tree as it stands today is
> ["What exists today, and what this model needs"](#what-exists-today-and-what-this-model-needs) —
> read that if you want to know what you can write right now. Individual rows and
> claims that do not exist yet are marked inline with **NOT BUILT**.

`String` and `Vec<u8>` have the same field layout — byte-for-byte identical today:

```zen
Vec*<T>: { ptr: RawPtr<u8>, len: i64, cap: i64, carried: bool, oom: bool, alloc: DynAlloc }
String*: { ptr: RawPtr<u8>, len: i64, cap: i64, carried: bool, oom: bool, alloc: DynAlloc }
```

They are **not** the same type. Zen's types are nominal, so identical layout buys
nothing at the type checker: assigning a `String` to a `Vec<u8>` binding is
`error[assign-fit]: expected 'Vec<u8>', got 'String'`. "`String` is `Vec<u8>`" is a
statement about representation and about the API the two are meant to share — it is
not an identity the compiler recognises, today or (as written) under the target
model. Read it as "one model, instantiated twice", not as "one type".

The last three fields are the allocator the value was born under and its sticky failure flag —
"The allocator decision" below says what each one carries and why.

So there is one model, over an element type, and text is the `u8` case of it. Five roles, five
names, no special cases — that is the target. **NOT BUILT:** two of the ten names it asks for do not exist
yet; the next section marks which.

## The five

> **TARGET MODEL.** Two of these five names do not exist. `grep -rn 'VecLiteral\|VecView' src/ tests/`
> returns nothing: there is no `VecLiteral<T>` and no `VecView<T>` anywhere in the tree. The rows are
> marked **NOT BUILT** below. The `String*` column is real for all five; the `Vec` column is real for three.

| name | representation | mutable | grows | size known | allocator | freed by |
|---|---|---|---|---|---|---|
| **NOT BUILT** `VecLiteral<T>` / `StringLiteral` | `{ptr}` → `.rodata` | no | no | **compile time** | no | never |
| `VecConst<T>` / `StringConst` | `{ptr, len}` + allocator | no | no | runtime | **yes** | **you** |
| `VecFixed<T>` / `StringFixed` | `{ptr, len}` + allocator | **yes** | no | runtime, fixed at creation | **yes** | **you** |
| `Vec<T>` / `String` | `{ptr, len, cap}` + allocator | yes | **yes** | runtime, changes | **yes** | **you** |
| **NOT BUILT** `VecView<T>` / `StringView` | `{ptr, len}` | no | no | runtime | no | **not yours** |

The `Vec` side of the borrowed row is spelled `Slice<T>` / `MutSlice<T>` (`[T]`) today — a slice, not a
named `VecView<T>` — and the literal row has no `Vec` spelling at all: a slice literal `[1, 2, 3]` is
just a `[T]`.

Three axes decide the row, and every combination that makes sense has a name:

- **ownership** — static, owned, or borrowed
- **mutability** — can you write through it
- **growth** — is there a `cap` to grow into

`cap` is the whole difference between `Vec` and everything else. It is where spare room is
recorded; without it there is nowhere to put the answer to "how much space is left", so growth
is impossible by construction rather than by convention.

`VecConst`, `VecFixed` and the unbuilt `VecView` are all `{ptr, len}` in the part that describes the bytes. They
differ only in what the checker will let you do. That is the good kind of type: it changes what
compiles and changes nothing about what runs.

The two OWNED ones carry one more thing the borrowed one does not: the allocator. `drop()` takes no
argument, so the value itself has to be the only thing that decides where the bytes go back to —
otherwise freeing through the wrong allocator stays a live mistake. The borrowed row frees nothing
and so carries nothing.

### `StringCstr` is not one of the five

The compiler also has `StringCstr`, and it is deliberately absent from the table. (It is the sixth
live string spelling, not a fourth — `StringLiteral`, `StringView`, `StringCstr`, `String`,
`StringConst` and `StringFixed` are all real annotatable types today; see "What exists today"
below.) The three axes above are ownership, mutability and growth; NUL-termination is none of
them. It is a property of the *representation at the C boundary* — "there is a `\0` after the
last byte, so a `const char*` handed to libc will terminate" — which is orthogonal to who owns
the bytes and whether they can be written or grown. Folding it into the table would mean either
inventing a role it does not fill or doubling every row into terminated/unterminated variants,
and both would be lies about what the type is for.

So `StringCstr` keeps the family prefix for spelling consistency and nothing else changed about
it: it is the FFI-boundary spelling, it covers both `.rodata` literals and heap blocks from
`sb().done()`, and a view of one is read-only. When the five roles land it will still be a
separate axis, most likely a property carried alongside a role rather than a role of its own.
Naming it honestly as an outsider is better than a forced fit.

## Creating them

> **Mostly real.** The `String` side of this section describes the tree as it stands: the
> constructors, `add`, `freeze` and `drop` shown here all exist and compile. Every place where the
> original design sketch differs from the tree is marked **NOT BUILT** or corrected inline.

The block below compiles today, inside a `Result`-returning function (for `or_return()`):

```zen
gpa = alloc.dyn_heap()                          // the process heap, as a value the row can carry

// StringLiteral — no allocator, no ceremony; it is already in the binary.
name = "zen"

// Borrowing. Costs nothing, frees nothing. Note `.view()` does NOT yield a `StringView`: on a
// literal it yields a read-only `Slice<u8>`. `StringView` is what a PARAMETER is spelled, and a
// literal or a StringCstr is accepted there directly, with no `.view()` at the call site.
v = name.view()

// A SUB-view is NOT free today: there is no `name.slice(0, 2)` (`slice` is the two-argument
// pointer intrinsic, and std.text.str has no `slice`). The live API is `substr_in`, and it
// ALLOCATES — it copies the range through the allocator you hand it and returns a Result.
part = h.substr_in(name, 0, 2).or_return()      // h: Allocator. One allocation, not zero.

// StringFixed — state the size once. Writable, never grows. One allocation, so it settles here.
buf = gpa.string_fixed(64).or_return()
buf.set(0, 'h')

// String — the only one whose length is not decided at creation. Construction is INFALLIBLE:
// a failed birth allocation is recorded, and the whole chain settles once, at freeze().
s ::= gpa.string(16)
s = s.add("hello").add(" world")

// StringConst — owned but frozen. Not built directly: build a String, then give up
// the right to change it.
frozen = s.freeze().or_return()
frozen.drop()                                   // no allocator argument — it carries its own
```

`Vec<T>` is the same family, with an element type. It has no element to infer `T` from at
construction, and a UFCS receiver cannot carry an explicit type argument, so `T` comes from the
binding's annotation:

```zen
xs = [1, 2, 3]                                  // a `[i32]` slice literal — NOT a `VecLiteral`
scratch: Result<VecFixed<i64>, IoError> = gpa.vec_fixed(64)
v :: Vec<i64> = gpa.vec(16)                     // infallible, like `string`
v = v.add_one(1)
locked = v.freeze().or_return()                 // VecConst<i64>
```

**NOT BUILT:** the `view = xs.view()` line that used to sit in that block is gone: a slice literal has no
`.view()` method (`error[undefined-name]`, or `error[arg-type]: expected 'StringView', got '[i32]'`
if `std.text.str`'s `view` is in scope). A slice literal already *is* the borrowed row.

**Every op returns the updated value.** `s.add(…)` does not mutate `s` in place — the header moves
when the buffer is realloc'd, so a chain has to be bound back (`s = s.add(…).add(…)`), exactly as
`std.text.sb` and `Vec.push` already do. Only the settle points (`freeze`) and the readers
(`view`, `get`, `drop`) can be left un-bound.

## Conversions

> **Partly TARGET MODEL.** `freeze()`, `drop()` and `string_from` are real. The
> "one free view type" story below is the part of this design that the tree does **not**
> implement — it is corrected in place rather than deleted, because it is still the goal.

```
literal ──gpa.string(n).add(lit)──▶ String ──freeze()──▶ StringConst
                                      │                      │
                                      │  .view() → [u8]      │  .view() → Slice<u8>
                                      ▼                      ▼
                                    (two DIFFERENT view types — see below)
```

There is no `copy(a)` literal-to-`String` conversion; the live path is `gpa.string(n)` followed by
`.add(literal)` (and `gpa.string_from(frozen)` for the `StringConst` direction).

**`.view()` is cheap from every row, but it does NOT always yield the same type**, and this is the
one claim in this document that most needs correcting. Today:

| receiver | `.view()` yields |
|---|---|
| `String` | `[u8]` (writable — `MutSlice<u8>`) |
| `StringFixed` | `[u8]` (writable) |
| `StringView` | `[u8]` (writable) |
| `StringConst` | `Slice<u8>` (read-only) |
| `StringLiteral` / `StringCstr` | `Slice<u8>` (read-only) |

So a `[u8]` parameter rejects a `StringConst`, `StringLiteral` or `StringCstr` view
(`error[arg-type]: expected '[u8]', got 'Slice<u8>'`), and the writable rows and the read-only
rows are not interchangeable at a call site. Also note the receiver, not the callee, decides:
`std.text.str`'s `view` is declared once as `(s: StringView) [u8]`, and the checker narrows the
result to `Slice<u8>` from the provenance of what you called it on.

**A `StringView` parameter does not accept the owned kinds either.** `StringView` is the borrowed
*string* type, not a supertype of the family: passing a `String` to a `(v: StringView)` parameter is
`error[arg-type]: expected 'StringView', got 'String'`. It does accept a `StringLiteral` and a
`StringCstr` with no conversion, which is why it is the right parameter type for read-only text that
arrives from a literal or the C boundary — but an owned `String` still has to be converted at the
call site.

**NOT BUILT:** "one view type that every row converts into for free" is a **goal** of the target model, not a
property of the tree. Until it lands, a read-only API has to pick: `StringView` (literals and cstrs,
plus an explicit step from owned text) or `Slice<u8>` (everything, via `.view()`, at the cost of
losing the string-shaped API).

**`freeze()` shrinks to fit and gives up growth.** A `String` carries `cap >= len`; freezing
returns the slack to the allocator and yields a type with no `cap`. One realloc buys memory back
and an immutability guarantee.

**`freeze()` is also the ONE settle point.** Construction cannot fail into your hands and neither
can any `add`: a failed allocation trips a sticky flag, every later `add` is a no-op, and the whole
chain becomes a single `Result` here — `.Ok(StringConst)` or the first failure, with the partial
buffer freed on the way out. That is `std.text.sb`'s policy, moved onto the type it was a builder
for. It is why there is no `or_return` per step, and why there is exactly one per chain.

**There is deliberately no `thaw()`.** Going back means copying, so it is spelled
`gpa.string_from(frozen)` — the allocation is visible because the allocator is named.

## Naming rules

> **TARGET MODEL.** These are the rules the family is being named *by*. The `String` names
> they produce exist; the `Vec` ones marked **NOT BUILT** above do not, so read this as the convention a
> new name must satisfy, not as an index of what you can call today.

**Prefix, not natural word order.** `StringFixed`, not `FixedString`. The shared prefix groups
the family in a flat namespace and in autocomplete, and the flat namespace is the constraint that
matters here — every top-level name is global.

**`add`, not `append`.** Shorter, and it reads identically for both:

```zen
s.add("hello")
v.add(other)
```

**`add` means many; `add_one` means one.** Zen has no function overloading, so `add` can only
mean one thing, and the shared model forces `Vec` and `String` to agree. The frequent case wins:
`s.add("hello")` is written constantly, `v.add_one(5)` rarely. Optimising the common case is the
same reasoning that chose `add` over `append`.

**Text-specific API stays on the text type.** `split`, `trim`, `to_upper` are string-shaped and
belong to `String`. `add`, `view`, `freeze`, `drop` are `Vec`-shaped operations that `String`
declares in parallel — separate impls on a separate nominal type, not inheritance.

## What exists today, and what this model needs

> **THE TREE.** This is the one section that reports the current state rather than the target
> model. Where it disagrees with anything above, this section wins.

**Real now:** `String`, `Vec<T>`, views (as `[T]` / `Slice<T>`), the `(a: Allocator)` sugar,
`or_return`, sticky-error chaining (as `std.text.sb`).

**Real but partial:** the borrowed/static string family — `StringLiteral`, `StringView`,
`StringCstr` — each of which a diagnostic prints as itself. (The `str`, `text` and `Cstr` aliases
are gone, as are the old snake_case spellings. Two *different* mechanisms keep them dead, and it
is worth not confusing them: the compiler rejects `str`/`text`/`Cstr` as unknown type names at
check time, while the `tests/harness_boundaries.zen` rule scans source bytes for exactly the three
snake_case spellings — `string_view`, `string_literal`, `string_cstr` — and fails the build if one
reappears. The harness does **not** gate the short aliases.)

**Real now, as of the carrying rebuild:** `StringConst`, `StringFixed`, `VecConst`, `VecFixed`,
`freeze()`, `drop()`, `add`/`add_one`, and the carrying constructors `string` / `string_fixed` /
`string_from` / `vec` / `vec_fixed` / `vec_from`.

**Not done:** the threaded API (`init`/`push_in`/`append_in`/`finish_in`/`free_in`) and
`std.text.sb` are still present and still work, and every consumer still uses them. Until they are
deleted a `String` can arrive from either surface, which is what the `carried` field records: false
means "built by the threaded API, no allocator inside", and the carrying ops refuse rather than
call through an empty vtable. That field exists only to make the transition safe and goes away with
the threaded API.

### The two language changes that used to gate this — both resolved

Nothing in the language is blocking the remaining rows. Both items below were open questions
when this document was written; one is DONE and the other is DECIDED. What is left is ordinary
work: naming and building the `Vec` counterparts, and deleting the threaded API.

**1. Slices need a mutability bit.** DONE. Slices now carry the same kind tag pointers do:
`Slice<T>` is the read-only window, `MutSlice<T>` the writable one, and `[T]` is the sugar for
`MutSlice<T>`. Both are the same `{ptr, len}` layout. `.view()` propagates: a window over a
`StringLiteral`/`StringCstr` is a `Slice<T>`, so this is now `error[slice-write]` at check time
instead of a segfault:

```zen
s: StringCstr = "hello"
v ::= s.view()           // Slice<u8> — a read-only window
v[0] = 'H'               // error[slice-write]: cannot write through a read-only `Slice<T>`
```

The default stayed on `[T]` = writable, measured: making `[T]` read-only broke 233 write sites in
73 files, while making views-of-immutable read-only broke 5. Flipping it later is one line
(`k_slice_dflt` in compiler.genc) now that both spellings exist.

Immutability now has somewhere to live once you take a view, which is what `StringConst` and
`StringFixed` needed — and both of those types have since landed (see "Real now, as of the
carrying rebuild" above). `StringFixed` **is** the "owned, writable bytes" type this paragraph
used to say was missing: `StringFixed.view` hands back a writable `[u8]`, `StringConst.view` a
read-only `Slice<u8>`. What remains is a representation wart, not a missing type: `StringCstr`
still covers BOTH `.rodata` literals and heap blocks from `sb().done()`, so a view of one is
conservatively read-only, while `str.view` on a plain `StringView` still yields a writable `[u8]`.

**2. The allocator decision.** DECIDED: the container carries it. The old rule was **carry the
allocator and you give up errors-as-values** (`AVec`/`ASet`/`AHMap` store a `DynAlloc` and panic)
versus **thread it and you keep them** (`Vec`/`String` return `Result`), with `std.text.sb` the one
type that did both. Sb's shape won: the row carries a `DynAlloc` AND keeps errors as values,
because the sticky flag defers them all to one settle point.

Three fields do it, in this order, identically on `Vec<T>` and `String`:

- `carried: bool` — this header owns an allocator. Transitional; see above.
- `oom: bool` — the sticky flag. Set by the first failed allocation, never cleared.
- `alloc: DynAlloc` — the Allocator trait as a VALUE (three fn-pointers + state), which is what
  lets the field exist at all: a `MutPtr<A>` allocator cannot be erased into a value, because a
  generic function cannot be taken as a fn-pointer and an impl method cannot be named as one. So
  the carrying constructors take a `DynAlloc` (`alloc.dyn_heap()`, or any `dyn_of(...)` vtable)
  rather than the `a: Allocator` the threaded API takes. Note that `std.rt`'s `dyn_of_rt` is
  **private** — its declaration carries no `*` (`src/std/rt.zen:155`), so naming it from outside
  the module is `error[private-name]`. Its wrapper `dyn_current` (`:159`) is private too, so
  there is currently **no** public `std.rt` route from an `Rt` to a `DynAlloc`; the ambient
  runtime cannot supply a carrying constructor from outside `std.rt` until one is exported.

Deciding that for `String` also decides `AVec`: it either becomes the default or disappears.

## Why this is worth the churn

> **TARGET MODEL.** This section argues for the design; it is not a claim about what the tree
> guarantees today. The one part of it that IS enforced right now is called out below.

One set of rules instead of two. `cap` means growable everywhere; `View` means borrowed
everywhere; `Fixed` means sized-once-and-writable everywhere. Learn it for `Vec<i64>` and you
already know `String`. **NOT BUILT:** not yet true in the direction that matters most — the `Vec` side is
missing the literal and view rows entirely, and the two families are separate nominal types, so
knowledge transfers but code does not.

And it makes the dangerous cases unrepresentable rather than merely discouraged: a function taking
`StringView` cannot free its argument, a `StringConst` cannot be written through, and a
`StringFixed` cannot silently reallocate under a view someone else is holding. The middle one is
**real today** — `StringConst.view` yields a `Slice<u8>` and writing through it is
`error[slice-write]` at check time, which is the payoff item 1 above bought.
