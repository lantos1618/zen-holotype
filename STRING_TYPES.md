# Explicit string types — `text` / `view` / `String` / `Cstr`

Status: Phase 1 DONE (Cstr + text + enforcement + tests). Phase 2 (view + migration) pending. Motivation: today `str` (= C `const char*`) is overloaded across three
roles with **incompatible lifetimes**, and the type can't tell them apart — so a pointer into a
heap `String` can escape and dangle with no diagnostic. The fix is to make the bytes' *provenance*
a type, so a signature documents the lifetime contract (enforceable even without a borrow checker).

## The four types

| Type | Owns? | Storage / lifetime | Mutable | Length | C repr |
|------|-------|--------------------|---------|--------|--------|
| `text` | no | **static** (rodata) — **immortal** | no | NUL-scan | `const char*` |
| `view` | no | **borrowed** — = the owner's lifetime | no | carried `(ptr,len)` | `zslice` / `{u8* ptr; i64 len}` |
| `String` | **yes** | **heap**, via an explicit `Allocator` | yes (grows) | carried `(ptr,len,cap)` | `{u8* ptr; i64 len; i64 cap}` |
| `Cstr` | no | **borrowed from a `String`** — valid until that buffer is freed/realloc'd | no | NUL-scan | `const char*` |

- **`text`** is what a string literal `"…"` is. Safe to return/store forever.
- **`view`** is the right default for *reading* a string (substring, a token slice of source, a
  param that only reads). No NUL scan; length is free. Lives as long as whoever owns the bytes.
- **`String`** is the only owner of heap string bytes and the only thing you `free`. Every op takes
  the allocator explicitly (`s.gstr_push(a, b)`), so the bytes' fate is never implicit.
- **`Cstr`** is the FFI bridge: a `const char*` pointing **into a `String`'s buffer** (what `finish`
  hands back). The name screams "borrowed C pointer — mind my lifetime." Its lifetime IS the
  allocator that owns the String's buffer.

## Conversions (the contract the checker enforces)

Legal:
- `"…"` literal  ⟶ `text`
- `text`  ⟶ `view`            (a literal is trivially a borrowed view; length via NUL scan once)
- `String.view()`  ⟶ `view`   (borrow the live buffer)
- `String.finish(a)`  ⟶ `Cstr` (NUL-terminate + reinterpret the buffer pointer)
- `cstr(rawptr)`  ⟶ `Cstr`     (assert NUL-terminated bytes at a raw pointer)
- `Cstr`  ⟶ `view`             (read it; pays one NUL scan for the length)

ILLEGAL (these are the dangle/mutate bugs):
- `Cstr`  ⟶ `text`   — a finished/heap pointer is NOT immortal. **This is the bug to reject.**
- `view`  ⟶ `text`   — a borrowed view is not immortal.
- mutating a `text`  — it's in rodata.
- returning a `view`/`Cstr` that outlives its owner — best-effort flag; not fully checkable without
  a borrow checker, but the type at least documents the obligation.

## Audit (seed sources, for sizing)

- `str` in type positions: **946** — the vast majority are **borrowed source-views** (`view`): tokens
  and names read out of the source buffer, which lives the whole compile.
- string literals: **671** ⟶ `text`.
- `view`/slice reads: **45**.
- **`cstr`/`finish` sites (the `Cstr` surface): ~34** — localized in `resolve.zen` (~23, module
  ids/bodies/symbol keys), `genc.zen` (mangled names), `parse_expr.zen` (interned AST names),
  `io/file.zen` (file contents). These are the dangle-risk surface and the minimum that must split.

## Implementation plan

### Phase 1 — minimal split (kills the footgun, least churn)
1. AST/`Ty` (genc.zen): add a `Cstr` variant (and `Text` if literals get their own type); emit both as `const char*`.
2. Lexer/parser: string literals get type `text` (or keep `str` meaning "borrowed view" and literals as `text`).
3. Ops: `cstr()` and `String.finish(a)`/`gstr_finish` return **`Cstr`**, not `str`/`text`.
4. Checker (check_validate): reject `Cstr` (and `view`) where a `text`/immortal is required; reject `text` mutation.
5. Re-reach byte-exact fixpoint; the ~34 `Cstr` sites now carry an honest type.

### Phase 2 — full taxonomy
6. `view` as the length-carrying `(ptr,len)` borrowed type (back it with `zslice`); retype `str.len/at/eq/slice` and `String.view()` to `view` (no `strlen`).
7. Migrate the 946 borrowed `str` params ⟶ `view`.
8. `String` always-takes/carries its `Allocator` so `Cstr` lifetime = that allocator's buffer.

### Tests
9. `Cstr` cannot be returned where `text` is required; a finished-`String`-as-`text` is a check error.
10. `view` ops (len/at/eq/slice); the legal conversions; `text` immutability.
