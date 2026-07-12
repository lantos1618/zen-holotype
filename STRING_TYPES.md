# String provenance types

Status: Phase 1. The compiler has three canonical non-owning spellings—`string_literal`,
`string_cstr`, and `string_view`—plus the allocator-backed `String` owner. The old `text`, `Cstr`,
and `str` spellings remain parser aliases during migration.

The names describe where bytes came from. They are not Rust-style move types, and Phase 1 does not
try to infer an owner's lexical lifetime.

## What exists today

| Type | Migration alias | Owns bytes? | Contract today | Phase-1 C representation |
|---|---|---:|---|---|
| `string_literal` | `text` | no | points at immutable static storage | `const char *` |
| `string_cstr` | `Cstr` | no | borrowed, NUL-terminated pointer | `const char *` |
| `string_view` | `str` | no | borrowed readable string | `const char *` |
| `String` | none | yes | allocator-backed `{ptr, len, cap}` header | struct |

`string_view` is deliberately a semantic name before it is a new ABI. In Phase 1 it is still a
NUL-terminated pointer and `len` scans for NUL. Converting it to a real `(ptr, len)` value is Phase 2.
There is no lowercase owned `string` type yet.

## Checker contract

Outer-value conversions form this one-way lattice:

```text
string_literal  ->  string_cstr  ->  string_view
        \----------------------------^
```

Therefore:

- a literal can satisfy any of the three non-owning slots;
- a `string_cstr` can be read as a `string_view`;
- a `string_view` or `string_cstr` cannot satisfy `string_literal`;
- a mixed match result uses the broader safe type, independent of arm order;
- pointers, slices, and generic storage are invariant, so `Box<string_view>` cannot masquerade as
  `Box<string_literal>` and a mutable pointer cannot overwrite a literal-typed slot;
- semantic monomorphization keys keep the three provenances distinct even though their C payload is
  currently identical;
- read-only trait lookup is the deliberate exception: `string_literal`, `string_cstr`, and
  `string_view` dispatch through one canonical `string_view.impl(...)`. This shares behavior, not
  storage identity or conversion rights.

These rules document and enforce provenance at signatures. They do **not** yet prove that a borrow
cannot outlive its owner. They also do not yet make every `[u8]` view read-only; APIs that expose raw
byte slices remain part of the Phase-2 capability audit.

## Actual APIs

```zen
{ new_in } = std.text.string
{ expect } = std.core.result

use_then_free<A> = (a: MutPtr<A>) void {
    s := a.new_in().expect("new")
    s = s.append_in(a, "hello").expect("append")
    text := s.finish_in(a).expect("finish")
    // use text while s owns the allocation
    s.free_in(a)
}
```

The owned builder remains `String`; mutating operations return the updated small header and take the
allocator explicitly. `finish_in` writes a trailing NUL and returns a borrowed `string_cstr` into the
builder's allocation. The caller still owns the `String` and frees it with the same allocator.
`String.cap` is the physical allocation size, including the spare NUL byte; `init(n)` guarantees at
least `n` bytes of content capacity and therefore returns a header whose `cap` is at least `n + 1`.

An API may deliberately promise only `string_view` even when its current implementation builds a
NUL-terminated buffer. Because generic containers are invariant, widening
`Result<string_cstr, E>` to `Result<string_view, E>` is explicit: unwrap or match the result, widen
its successful payload, then construct the outer result again. This preserves provenance through
generic storage while allowing a public API to expose only the guarantee it intends callers to use.

Read operations remain exported from `std.text.str` during migration:

```zen
{ len, eq } = std.text.str

same = (a: string_view, b: string_view) bool {
    a.len() == b.len() && a.eq(b)
}
```

## Migration aliases

| Old spelling | Canonical spelling |
|---|---|
| `text` | `string_literal` |
| `Cstr` | `string_cstr` |
| `str` | `string_view` |

The formatter writes canonical spellings. Source inputs may keep aliases temporarily, but formatted
output and diagnostics use the `string_*` vocabulary.

## Phases

### Phase 1 — canonical provenance names

1. Rename backend variants to `StringLiteral`, `StringCstr`, and `StringView`.
2. Parse and format the canonical surface spellings while retaining the three aliases.
3. Infer literals as `string_literal`; return `string_cstr` from `cstr()` and `String.finish_in()`.
4. Enforce one-way value conversions, safe joins, invariant aggregate storage, and distinct semantic
   generic identities.
5. Migrate the repository's formatted type spellings atomically and keep the bootstrap at fixpoint.

### Phase 2 — representation and capability audit

1. Represent `string_view` as `(ptr, len)` and remove implicit `strlen` from view operations.
2. Classify stdlib parameters by actual need: view, NUL-terminated FFI input, or owned `String`.
3. Make raw byte views read-only where the API promises read-only access.
4. Express allocator/region relationships in signatures without implicit move semantics.
5. Decide whether the owned `String` spelling should change.

### Phase 3 — remove aliases

Remove `str`, `text`, `Cstr`, and the internal `tstr`/`ttext`/`tcstr` constructor aliases after user
code and the standard library have migrated.

## Required regressions

- canonical names parse, format, and appear in diagnostics;
- both branch orders reject borrowed-to-literal laundering;
- literals safely join with cstr/view as the broader provenance;
- mutable pointers and generic wrappers preserve exact provenance;
- unrelated imports cannot change a generic call's inferred string type;
- aliases remain accepted until Phase 3;
- full harness, whole-tree formatter gate, and byte-exact bootstrap fixpoint pass.
