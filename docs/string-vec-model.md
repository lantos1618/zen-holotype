# The String and Vec model

`String` is `Vec<u8>`. Not "like" it — the structs are byte-for-byte identical today:

```zen
Vec*<T>: { ptr: RawPtr<u8>, len: i64, cap: i64, carried: bool, oom: bool, alloc: DynAlloc }
String*: { ptr: RawPtr<u8>, len: i64, cap: i64, carried: bool, oom: bool, alloc: DynAlloc }
```

The last three fields are the allocator the value was born under and its sticky failure flag —
"The allocator decision" below says what each one carries and why.

So there is one model, over an element type, and text is the `u8` case of it. Five roles, five
names, no special cases.

## The five

| name | representation | mutable | grows | size known | allocator | freed by |
|---|---|---|---|---|---|---|
| `VecLiteral<T>` / `StringLiteral` | `{ptr}` → `.rodata` | no | no | **compile time** | no | never |
| `VecConst<T>` / `StringConst` | `{ptr, len}` + allocator | no | no | runtime | **yes** | **you** |
| `VecFixed<T>` / `StringFixed` | `{ptr, len}` + allocator | **yes** | no | runtime, fixed at creation | **yes** | **you** |
| `Vec<T>` / `String` | `{ptr, len, cap}` + allocator | yes | **yes** | runtime, changes | **yes** | **you** |
| `VecView<T>` / `StringView` | `{ptr, len}` | no | no | runtime | no | **not yours** |

Three axes decide the row, and every combination that makes sense has a name:

- **ownership** — static, owned, or borrowed
- **mutability** — can you write through it
- **growth** — is there a `cap` to grow into

`cap` is the whole difference between `Vec` and everything else. It is where spare room is
recorded; without it there is nowhere to put the answer to "how much space is left", so growth
is impossible by construction rather than by convention.

`VecConst`, `VecFixed` and `VecView` are all `{ptr, len}` in the part that describes the bytes. They
differ only in what the checker will let you do. That is the good kind of type: it changes what
compiles and changes nothing about what runs.

The two OWNED ones carry one more thing the borrowed one does not: the allocator. `drop()` takes no
argument, so the value itself has to be the only thing that decides where the bytes go back to —
otherwise freeing through the wrong allocator stays a live mistake. `VecView` frees nothing and so
carries nothing.

### `StringCstr` is not one of the five

The compiler also has a fourth string spelling, `StringCstr`, and it is deliberately absent from
the table. The three axes above are ownership, mutability and growth; NUL-termination is none of
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

```zen
gpa := alloc.dyn_heap()                         // the process heap, as a value the row can carry

// StringLiteral — no allocator, no ceremony; it is already in the binary.
name := "zen"

// StringView — borrows. Costs nothing, frees nothing, accepts anything.
v    := name.view()
part := name.slice(0, 2)                        // a sub-view: still zero allocation

// StringFixed — state the size once. Writable, never grows. One allocation, so it settles here.
buf := gpa.string_fixed(64).or_return()
buf.set(0, 'h')

// String — the only one whose length is not decided at creation. Construction is INFALLIBLE:
// a failed birth allocation is recorded, and the whole chain settles once, at freeze().
s := gpa.string(16)
s = s.add("hello").add(" world")

// StringConst — owned but frozen. Not built directly: build a String, then give up
// the right to change it.
frozen := s.freeze().or_return()
frozen.drop()                                   // no allocator argument — it carries its own
```

`Vec<T>` is the same five, with an element type. It has no element to infer `T` from at
construction, and a UFCS receiver cannot carry an explicit type argument, so `T` comes from the
binding's annotation:

```zen
xs      := [1, 2, 3]                            // VecLiteral<i64>
view    := xs.view()                            // VecView<i64>
scratch: Result<VecFixed<i64>, IoError> := gpa.vec_fixed(64)
v: Vec<i64> := gpa.vec(16)                      // infallible, like `string`
v       = v.add_one(1)
locked  := v.freeze().or_return()               // VecConst<i64>
```

**Every op returns the updated value.** `s.add(…)` does not mutate `s` in place — the header moves
when the buffer is realloc'd, so a chain has to be bound back (`s = s.add(…).add(…)`), exactly as
`std.text.sb` and `Vec.push` already do. Only the settle points (`freeze`) and the readers
(`view`, `get`, `drop`) can be left un-bound.

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

**`freeze()` is also the ONE settle point.** Construction cannot fail into your hands and neither
can any `add`: a failed allocation trips a sticky flag, every later `add` is a no-op, and the whole
chain becomes a single `Result` here — `.Ok(StringConst)` or the first failure, with the partial
buffer freed on the way out. That is `std.text.sb`'s policy, moved onto the type it was a builder
for. It is why there is no `or_return` per step, and why there is exactly one per chain.

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

**Real but partial:** three internal types, with exactly three surface spellings —
`StringLiteral`, `StringView`, `StringCstr` — each of which a diagnostic prints as itself.
(The `str`, `text` and `Cstr` aliases are gone, as are the old snake_case spellings; a
`tests/harness_boundaries.zen` rule fails the build if any of the three comes back.)

**Real now, as of the carrying rebuild:** `StringConst`, `StringFixed`, `VecConst`, `VecFixed`,
`freeze()`, `drop()`, `add`/`add_one`, and the carrying constructors `string` / `string_fixed` /
`string_from` / `vec` / `vec_fixed` / `vec_from`.

**Not done:** the threaded API (`init`/`push_in`/`append_in`/`finish_in`/`free_in`) and
`std.text.sb` are still present and still work, and every consumer still uses them. Until they are
deleted a `String` can arrive from either surface, which is what the `carried` field records: false
means "built by the threaded API, no allocator inside", and the carrying ops refuse rather than
call through an empty vtable. That field exists only to make the transition safe and goes away with
the threaded API.

### Two language changes gate the missing rows

**1. Slices need a mutability bit.** DONE. Slices now carry the same kind tag pointers do:
`Slice<T>` is the read-only window, `MutSlice<T>` the writable one, and `[T]` is the sugar for
`MutSlice<T>`. Both are the same `{ptr, len}` layout. `.view()` propagates: a window over a
`StringLiteral`/`StringCstr` is a `Slice<T>`, so this is now `error[slice-write]` at check time
instead of a segfault:

```zen
s: StringCstr := "hello"
v := s.view()            // Slice<u8> — a read-only window
v[0] = 'H'               // error[slice-write]: cannot write through a read-only `Slice<T>`
```

The default stayed on `[T]` = writable, measured: making `[T]` read-only broke 233 write sites in
73 files, while making views-of-immutable read-only broke 5. Flipping it later is one line
(`k_slice_dflt` in compiler.genc) now that both spellings exist.

Immutability now has somewhere to live once you take a view, which is what `StringConst` and
`StringFixed` needed. What is still missing for them is a type that says "owned, writable bytes":
`StringCstr` today covers BOTH `.rodata` literals and heap blocks from `sb().done()`, so a view of
one is conservatively read-only while a view of a plain `StringView` stays writable.

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
  the carrying constructors take a `DynAlloc` (`alloc.dyn_heap()`, `rt.dyn_of_rt(...)`, or any
  `dyn_of(...)` vtable) rather than the `a: Allocator` the threaded API takes.

Deciding that for `String` also decides `AVec`: it either becomes the default or disappears.

## Why this is worth the churn

One set of rules instead of two. `cap` means growable everywhere; `View` means borrowed
everywhere; `Fixed` means sized-once-and-writable everywhere. Learn it for `Vec<i64>` and you
already know `String`.

And it makes the dangerous cases unrepresentable rather than merely discouraged: a function taking
`StringView` cannot free its argument, a `StringConst` cannot be written through, and a
`StringFixed` cannot silently reallocate under a view someone else is holding.
