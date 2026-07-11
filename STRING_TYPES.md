# String types — one family, names that say what they mean

**Rule:** every string *type* starts with `string_`. No more overloaded `str` / `text` / `Cstr`
hiding incompatible lifetimes behind the same spelling.

## The family

| Type | Old name(s) | Owns bytes? | Lifetime | Example |
|------|-------------|-------------|----------|---------|
| **`string_literal`** | `text`, `Text` | no | **immortal** (rodata) | `"hello"`, `op_str` → `"+"` |
| **`string_view`** | `view`, most `str` params | no | **borrowed** — don't outlive owner | token span in source, `fn f(s: string_view)` |
| **`string`** | `String` (struct) | **yes** | until `free_in(a)` | growable buffer via allocator |
| **`string_cstr`** | `Cstr`, `cstr(...)` | no | **borrowed NUL*** — don't outlive buffer | `s.finish_in(a)`, `lexeme`, FFI |

All four are string types. The suffix tells you **provenance**, not the C repr (several lower to
`const char*` or `{ptr,len}`).

### What each name means

- **`string_literal`** — compile-time / rodata. Store forever. `"…"` literals only (plus static
  data). Never heap, never borrow.

- **`string_view`** — read-only slice `(ptr, len)`. No NUL scan for length. Valid while the owner
  lives (source buffer, `[u8]` parent, etc.). Default for “I only need to read bytes.”

- **`string`** — the **owned** growable buffer `{ ptr, len, cap }`. Every mutating op takes an
  `Allocator`. This is the only type you `free`. (Struct may stay spelled `String` in code until
  rename lands; the *type* in signatures is `string`.)

- **`string_cstr`** — borrowed `const char*` that is **NUL-terminated** but **not immortal**.
  Points into a `string` buffer, an arena, or raw heap from `cstr(p)`. Mind the lifetime.

### Retired / migration aliases

| Old | Becomes | Notes |
|-----|---------|-------|
| `str` | `string_view` (params) or context-specific | **stop using as catch-all** |
| `text` | `string_literal` | |
| `Cstr` | `string_cstr` | |
| `view` | `string_view` | |
| `String` (struct) | `string` (type) / struct rename TBD | owned handle |

During migration, checker may treat the old and new names as one **compatible family** for C emission
(all still `const char*` where applicable), but **conversions** enforce lifetime rules.

## Conversions (checker contract)

Legal:

- `"…"`  ⟶ `string_literal`
- `string_literal`  ⟶ `string_view`     (read it; one NUL scan if needed)
- `string.view()`  ⟶ `string_view`
- `string.finish_in(a)`  ⟶ `string_cstr`
- `cstr(rawptr)`  ⟶ `string_cstr`
- `string_cstr`  ⟶ `string_view`        (read via NUL scan)

Illegal (the bugs we reject):

- `string_cstr`  ⟶ `string_literal`   — heap/arena pointer is not rodata
- `string_view`  ⟶ `string_literal`   — borrow is not immortal
- mutate `string_literal`               — rodata
- return `string_view` / `string_cstr` past owner death

## API naming (stdlib)

Prefer `string_*` on ops too, grouped under `std.text`:

```zen
// owned builder (type string, struct String for now)
s := string.new_in(a, 64)?
s = s.append_in(a, "hi")?
fin := s.finish_in(a)?          // → string_cstr

// borrowed read
string_view.len(v)
string_view.eq(a, b)

// literals — type is string_literal, spellings unchanged at use site
x: string_literal = "hello"
```

Legacy `std.text.str` helpers migrate to `string_view.*` (and take `string_view` params).

## Implementation phases

### Phase 1 — rename backend `Ty` + checker (minimal churn)
1. `Ty`: `Text` → `StringLiteral`, `Cstr` → `StringCstr`, keep `Str` as legacy alias → `StringView`
2. Surface spellings: `string_literal`, `string_cstr`, `text`/`Cstr` deprecated aliases
3. `cstr()` / `finish_in()` return **`string_cstr`**, not `str`
4. Reject `string_cstr` / `string_view` where `string_literal` required
5. Compiler sites (~34): `lexeme` → `string_cstr`, literals → `string_literal`

### Phase 2 — params + `string_view` as `(ptr,len)`
6. `string_view` backed by `zslice` / `{u8*, len}` in C
7. Migrate ~946 borrowed `str` params → `string_view`
8. `string` struct always threads allocator; `string_cstr` lifetime = that buffer

### Phase 3 — kill `str`
9. Remove `str` as a type (keep as doc alias only if needed)
10. Struct `String` → align spelling with type `string` if we want one word for owned

## Tests
- `string_cstr` cannot flow to `string_literal`
- `string_view` ops; legal conversions
- `string_literal` immutability
