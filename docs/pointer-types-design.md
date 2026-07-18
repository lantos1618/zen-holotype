# Design: distinct `Ptr` / `MutPtr` / `RawPtr` pointer types (safety-goal-D)

Status: IMPLEMENTED; this is the historical design/staging record.
Date: designed 2026-06-26; implementation status updated 2026-07-12.

Current implementation notes (these supersede historical "today" claims below):

- `PtrData.kind` survives parsing and formatting; diagnostics print the exact kind.
- `Ptr<T>` is read-only, `MutPtr<T>` writable, and typed `RawPtr<T>` nullable.
- `RawPtr<u8>` remains the deliberately permissive allocator/FFI floor; `null_ptr()` infers it.
  This is an explicit unsafe boundary because null and allocation results share one type.
- top-level `MutPtr<T>` can widen to `Ptr<T>`, while recursive pointee, slice, and generic
  positions are invariant and capability-exact.
- `assert_nonnull` preserves Ptr/Mut direction, Ptr cannot launder through RawPtr, all
  mutating intrinsics are direction-checked, and `.addr()` preserves readonly lvalue provenance.
- C declarators still erase every kind to `T*`, but generic/recursive mono names encode
  `rawptr_`, `ptr_`, or `mutptr_` so distinct semantic instances cannot collide.

The problem statement, line references, and staged seed-identity predictions below describe the
pre-implementation snapshot. They are retained as decision history, not as current behavior.

## 0. The one-paragraph problem

Zen's surface has three pointer spellings — `Ptr<T>`, `MutPtr<T>`, `RawPtr<T>` — but
they are a **fiction**. All three parse to a single `Ty.Ptr` AST node
(`zen/compiler/parse_type.zen:320,326-331`), all three lower to bare `T*` in C
(`zen/compiler/genc.zen:457-459`), and the checker treats them identically. The
distinction exists only in the programmer's head and in naming convention. The most
dangerous consequence: **`zenc fmt` silently rewrites every `MutPtr<T>` and `RawPtr<T>`
to `Ptr<T>`** (verified below), because the formatter's `ff_ty` arm has no kind to
preserve (`zen/compiler/pretty.zen:223`). Running the formatter erases mutability and
nullability intent across the whole tree. This doc designs making the three kinds
**distinct, carried through the AST, preserved by the formatter, and (progressively)
enforced by the checker** — a frontend-only change that leaves the emitted C and the
seed byte-identical.

Verified, current `zenc` binary:

```
$ cat probe.zen
f = (p: RawPtr<u8>, q: MutPtr<u8>, r: Ptr<u8>) void { }
$ ./zenc fmt --stdout probe.zen
f = (p: Ptr<u8>, q: Ptr<u8>, r: Ptr<u8>) void { }     # MutPtr/RawPtr ERASED
```

## 1. Target semantics (the user's pick — fixed)

| Kind         | null?       | deref (`load`) | write (`store`) | role                                   |
|--------------|-------------|----------------|-----------------|----------------------------------------|
| `Ptr<T>`     | non-null    | OK             | **REJECTED**    | shared, read-only borrow               |
| `MutPtr<T>`  | non-null    | OK             | OK              | exclusive/writable borrow              |
| `RawPtr<T>`  | **nullable**| needs null-check first | needs null-check first | FFI/allocator floor — the raw `T*` |

## 2. Where the distinction is lost today (cited)

### 2.1 Parser — collapses to one node
`zen/compiler/parse_type.zen`:
- `:320` `is_ptr_kw = (src, t) bool { src.tok_in(t, "Ptr|MutPtr|RawPtr") }` — recognizes
  all three keywords as "a pointer".
- `:143-144` `parse_ty` dispatches any of the three to the SAME `parse_ptr_ty`.
- `:326-331` `parse_ptr_ty` builds `tptr(a.tynode(inner.ty))` — **the keyword is never
  read**; the kind is gone before the node is constructed. The comment at `:318-319`
  states this explicitly ("all three lower to `T*` today … checker-level policy").

### 2.2 AST — one variant for all three
`zen/compiler/genc.zen:84`:
```
Ty*: I32 | I64 | U8 | F64 | Bool | Named(string_view) | Void
   | StringView | StringCstr | StringLiteral
   | Ptr(Ptr<Ty>) | Slice(Ptr<Ty>) | FnT(FnTData) | Generic(GenericData)
```
`Ptr(Ptr<Ty>)` carries only the pointee. Constructor `tptr* = (t: Ptr<Ty>) Ty { .Ptr(t) }`
(`:385`).

### 2.3 Formatter — always prints `Ptr`
`zen/compiler/pretty.zen:223`:
```
.Ptr(p) => s.ff_append(a, "Ptr<").ff_ty(a, load(p)).ff_append(a, ">"),
```
No kind available → always emits `Ptr<`. **This is the dangerous rewrite.**

### 2.4 Codegen — frontend-only, all lower to `T*` (CONFIRMED)
Every `Ty.Ptr` consumer in genc is kind-agnostic and emits `*`:
- `gen_ty` `:457-459` → `inner*`
- `mangle_ty` `:278`, `mangle_ty_len` `:289`, `mangle_write_ty` `:305` → `"ptr_"`
- `cname_len` `:474` / `cname_write` `:485` → `+ "*"`
- mono substitution `:508` → `tptr(...)`

**Therefore the kind tag is purely a frontend concept. genc never reads it. The emitted
C is unchanged and the regenerated seed is byte-identical through Stages 1–3.** (Stage 4
migrates source spellings; those re-format but still emit identical C.)

### 2.5 Checker — pointers compared/coerced by pointee only
`zen/compiler/check.zen`:
- `ty_eq` `:2583` `.Ptr(pa) => w.match({ .Ptr(pb) => load(pa).ty_eq(load(pb)), … })` —
  pointee-only equality.
- `unify_ty` `:1591` — pointee-only.
- `fits` `:2593-2599` + `is_raw_ptr_ty` `:2591` + `is_ptr_ty_g` `:2592`: the **current
  coercion floor**: `is_raw_ptr_ty(t)` is literally "`Ptr` whose pointee is `U8`", and a
  `Ptr<u8>` fits ANY pointer slot. This is how `null_ptr()` initializes any pointer field.
  This existing rule is exactly the `RawPtr<u8>`→anything coercion we want to keep, just
  re-expressed against the new kind tag.
- Intrinsic result types in `infer_call` (`:420-459`):
  - `load` → `arg0.pointee_of()` (`:427-428`)
  - `addr` → `tptr(env.a.tnode(arg0))` (`:449-450`)  ← currently kind-less
  - `null_ptr` → `tptr(tu8())` (`:445-446`)  ← this IS today's `RawPtr<u8>`
- Intrinsic arities/recognition for `load`/`store`/`addr`/`offset` live in
  `zen/compiler/check_validate.zen:235-270`.

`Ty.Ptr` is matched in ~25–30 arms across genc / pretty / check / check_validate /
resolve / ast. (Full grep list: genc.zen 278/289/305/457/474/485/508; pretty.zen 223;
check.zen 158/162/163/186/333/398/1591/2583/2591/2592/568; check_validate.zen 33/61/186;
plus std/internal/ast.zen, resolve.zen mirror copies.) This count drives the AST-shape
decision in §4.

## 3. Usage survey (quantified — `zen/` + `driver.zen`)

Type-position spellings:

| spelling            | count | dominant pattern                                            |
|---------------------|-------|-------------------------------------------------------------|
| `MutPtr<…>`         | 1385  | allocator threading                                         |
| └ `MutPtr<Malloc>`  | 967   | the pervasive `a: MutPtr<Malloc>` allocator param           |
| └ `MutPtr<A>` (gen) | 330   | bounded-generic allocator `f<A: Allocator>(a: MutPtr<A>)`   |
| └ `MutPtr<Self>`    | 8     | allocator trait method receivers                            |
| `Ptr<…>`            | 535   | read-mostly AST node borrows                                |
| └ `Ptr<Expr>`       | 284   | AST child pointers (read in match arms)                     |
| └ `Ptr<Ty>`         | 16    | heap-owned `Ty` nodes                                        |
| `RawPtr<…>`         | 319   | the byte-buffer / FFI floor                                 |
| └ `RawPtr<u8>`      | 318   | output buffers, `acquire` results, `null_ptr`               |

Pointer intrinsic call sites: `load(` 243, `offset(` 142, `.addr()` 126, `store(` 56.

**Key migration insight:** the codebase *already* uses the three kinds by human
convention and the convention is largely correct — `MutPtr<Malloc>` for the threaded
allocator (it is mutated via `acquire`), `Ptr<Expr>` for read-only AST children,
`RawPtr<u8>` for raw buffers. Enforcement mostly **ratifies existing spellings** rather
than forcing a rewrite. The audit in Stage 2/3 is to find the *exceptions* (writes through
a `Ptr<T>`, deref of a `RawPtr` without a check), which are expected to be a small set.

## 4. AST change: KIND TAG, not three variants

Two options:

**(A) Three variants** — `Ty: … | Ptr(Ptr<Ty>) | MutPtr(Ptr<Ty>) | RawPtr(Ptr<Ty>) | …`.
Rejected: every one of the ~25–30 `.Ptr(p)` match arms becomes three arms (or risks
non-exhaustive match → checker error), across genc mangling, cname, gen_ty, pretty,
unify, ty_eq, pointee_of, etc. Maximally invasive; touches codegen we want to leave inert.

**(B) Kind tag on the existing variant — RECOMMENDED.**
```
PtrKind constants:  kRawPtr = 0   kPtr = 1   kMutPtr = 2     (i32, mirrors tag_const style)
Ty:  … | Ptr(PtrData) | …
PtrData*: { pointee: Ptr<Ty>, kind: i32 }
```
Constructors:
```
tptr*    = (t: Ptr<Ty>) Ty { .Ptr(PtrData(pointee: t, kind: kMutPtr)) }   // default — see §7 default-kind
tptr_k*  = (t: Ptr<Ty>, k: i32) Ty { .Ptr(PtrData(pointee: t, kind: k)) }
ptr_pointee* = (pd: PtrData) Ptr<Ty> { pd.pointee }
```
Then every existing `.Ptr(p) => … load(p) …` arm becomes `.Ptr(pd) => … load(pd.pointee) …`
— a **mechanical, structure-preserving rename** at each site, the match shape is
unchanged, and codegen ignores `pd.kind` entirely. Only `pretty` and the new checker
rules read `pd.kind`.

Parser change (`parse_ptr_ty`, `parse_type.zen:326-331`): pass the keyword through.
`parse_ty` already matched the keyword token; thread its kind:
```
is_ptr_kw stays, but parse_ptr_ty learns which keyword fired:
  kind := src.tok_in(kw, "MutPtr").match({ true => kMutPtr, false =>
          src.tok_in(kw, "RawPtr").match({ true => kRawPtr, false => kPtr }) })
  TyEnd( ty: tptr_k(a.tynode(inner.ty), kind), next: … )
```
(Mechanically: `parse_ty` at `:143-144` currently discards `tt.tok` for the ptr case; it
must hand the head token to `parse_ptr_ty` so the keyword is classifiable.)

Formatter change (`pretty.zen:223`):
```
.Ptr(pd) => s.ff_append(a, ptr_kw(pd.kind)).ff_append(a,"<").ff_ty(a, load(pd.pointee)).ff_append(a,">"),
where ptr_kw(kRawPtr)="RawPtr"  ptr_kw(kPtr)="Ptr"  ptr_kw(kMutPtr)="MutPtr"
```

Note: `std/internal/ast.zen` and `resolve.zen` carry mirror `Ty`/`.Ptr` handling — they
must move in lockstep with genc's `Ty` definition (single source of truth is
`compiler.genc`). This is the one cross-file coupling to watch.

## 5. Coercion lattice (assignability / `fits`)

```
        MutPtr<T>   (deref+write, non-null)
           │  widen: drop write capability  (SAFE)
           ▼
         Ptr<T>     (deref only, non-null)
           ▲
           │  needs a null-check (Stage 3)
        RawPtr<T>   (nullable floor)
```

Rules for `fits(g, w)` (g = source/given, w = target/wanted), pointer cases:

| given \ wanted | `MutPtr<T>` | `Ptr<T>` | `RawPtr<T>` |
|----------------|-------------|----------|-------------|
| `MutPtr<T>`    | ✓           | ✓ widen  | ✓ (narrow to floor — always safe) |
| `Ptr<T>`       | ✗ (gain write) | ✓     | ✗ (RawPtr is writable) |
| `RawPtr<T>`    | needs check (S3) | needs check (S3) | ✓ |
| `RawPtr<u8>` (= `null_ptr()`) | ✓ unsafe floor | ✓ unsafe floor | ✓ |

- **Pointee must still match** (`load(pa).ty_eq(load(pb))`), unchanged.
- **`MutPtr→Ptr` is the workhorse coercion.** It legalizes the single most common
  pattern: `.addr()` yields `MutPtr<T>` (you took the address of a writable slot), and it
  flows into a `Ptr<Expr>`/`Ptr<Ty>` field (`tnode`, `cenode`, `buf[0].addr()`). Because
  `MutPtr` widens to `Ptr`, all ~126 `.addr()`→`Ptr<…>`-field sites stay legal with NO
  source change.
- **`null_ptr()` keeps the historical unsafe-floor behavior.** `kind==kRawPtr &&
  pointee==U8` fits any pointer slot because it is also the allocator result type. This is
  deliberately called out as a trust boundary rather than claimed as sound nullability.
- **Calling a `Ptr`-param fn with a `MutPtr` arg: YES** (widening). Calling a
  `MutPtr`-param fn with a `Ptr` arg: NO.

### `.addr()` preserves the lvalue's direction
`x.addr()` yields `MutPtr<T>` for writable local/field/index storage. Storage reached
through a read-only `Ptr<U>` yields `Ptr<T>` instead, so `p.field.addr()` cannot launder
read-only access into a writable pointer. The checker walks the lvalue chain to its first
pointer indirection.

### Allocator flow: `acquire` returns `RawPtr<u8>`
`Allocator.acquire : (MutPtr<Self>, i64) RawPtr<u8>` (`alloc.zen:15`). Two sinks:
1. `slice(a.acquire(n*sizeof(T)), n)` → `[T]` (the dominant path; `slice()` consumes the
   raw pointer and produces a fat slice — unaffected by pointer kinds).
2. `buf: RawPtr<u8> := a.acquire(...)` then `store`/`offset` on it (the `write_str`/buffer
   path, e.g. `genc.zen:362-370`). Here `buf` stays `RawPtr<u8>`. Under Stage 3, deref of
   `buf` would require a null-check; see §7 for why these stay lenient (pointee `u8` floor).

## 6. Null-check flow — how the checker learns a `RawPtr` is non-null

Zen is match-only and has no `?`/`!` sugar. Two complementary idioms; ship **both**:

### 6a. Explicit guard intrinsic (primary, ergonomic) — `assert_nonnull`
A new recognized intrinsic, sibling to the existing `zen__divz` / `zen__idx` runtime
guards (the trustworthy-safety preamble already PANICs on div-zero and OOB index):
```
p2 := assert_nonnull(p)        // p: RawPtr<T>  →  p2: MutPtr<T>  (PANICs if p == null)
```
- Checker: `RawPtr<T>` → `MutPtr<T>`; an already non-null `Ptr<T>`/`MutPtr<T>` keeps
  its existing direction capability. Arity is 1.
  (register in `check_validate.zen`).
- Codegen: lower to a stmt-expr guard mirroring `zen__idx`, e.g.
  `({ T* _p = (p); if(!_p) zen__panic("zen: panic: null pointer deref\n"); _p; })`.
  This is the ONLY place this design adds emitted C, and only when `assert_nonnull` is
  actually called — so the seed stays byte-identical until/unless we use it.
- Cost: one branch; consistent with the existing guard philosophy.

### 6b. Flow narrowing on a null comparison (zero-cost path)
The checker already special-cases match subjects. Extend the binding/narrowing so that
inside the arms of a null comparison, the `RawPtr` is re-typed:
```
(p == null_ptr()).match({
    true  => { /* p is null here — handle */ },
    false => { /* p NARROWED to MutPtr<T> — load/store OK, no panic */ }
})
```
(Symmetrically `p != null_ptr()` narrows in the `true` arm.) This is an ordinary,
exhaustive boolean `.match`, so it keeps the match-only ergonomics without relying on
match-arm guard syntax. It is strictly an optimization over 6a; implement 6a first.

Recommendation: **Stage 3 ships 6a (assert_nonnull) as the required idiom; 6b is a
follow-up** so we don't block on flow-analysis plumbing.

## 7. Checker rules + diagnostics (per stage)

New predicates (in `check.zen`, beside `is_raw_ptr_ty`):
```
ptr_kind(t: Ty) i32         // kRawPtr/kPtr/kMutPtr, or -1 if not a pointer
is_writable_ptr(t) bool     // kind == kMutPtr
is_nullable_ptr(t) bool     // kind == kRawPtr
```

- **Mutability (Stage 2):** a `store(p, v)` / `*p = …` where `ptr_kind(typeof p) == kPtr`
  is an error: `cannot write through a read-only Ptr<T> (use MutPtr<T>)`, carrying the
  `store` call's source position (positions already plumbed per the error-positions work).
  `store` through `RawPtr` is allowed in Stage 2 (nullability is Stage 3's job).
- **Nullability (Stage 3):** `load(p)`/`store(p,…)`/`offset(p,…)` where
  `is_nullable_ptr(typeof p)` AND `p` is not narrowed (6b) and not the result of
  `assert_nonnull` (6a) → error `RawPtr<T> may be null; null-check or assert_nonnull before
  deref`. **Exception:** the `u8` byte-buffer floor (`RawPtr<u8>`) is the FFI/allocator
  primitive and is used as a raw cursor everywhere (`write_str`, `pf_write`); these stay
  lenient (see §9 OQ-3 — do we exempt `RawPtr<u8>` entirely, or migrate buffers to a
  `Buf`/slice abstraction?).
- **`fits` / coercion:** update `fits` (`:2593`) with the §5 table; keep the `RawPtr<u8>`
  (null_ptr) wildcard.
- **`ty_eq` / `unify_ty`:** stay **kind-agnostic** (compare pointee only). Kind is a
  *coercion/capability* property, not an *identity* property — two `Ptr<T>` and `MutPtr<T>`
  are "the same type up to capability". This prevents over-rejection in generic unification
  (`MutPtr<A>` param unifying against a `MutPtr<Malloc>` arg, etc.).

## 8. STAGING (each stage ships independently green)

### Stage 0 — AST + constructors (no behavior change)
Add `PtrData{pointee,kind}`, `kRawPtr/kPtr/kMutPtr`, `tptr`/`tptr_k`; mechanically rename
~25–30 `.Ptr(p)` arms to `.Ptr(pd) … pd.pointee`. Parser still tags everything `kMutPtr`
(or whatever `tptr` defaults to). pretty still prints `Ptr<`. **Seed byte-identical;
oracle green.** Pure refactor.

### Stage 1 — preserve the kinds (THE high-value fix)
Parser reads the keyword → correct `kind`. pretty prints `ptr_kw(kind)`. **No checking yet
— kinds remain fully interchangeable in `fits`/`ty_eq`.** Plus: fix the formatter
comment-relocation bug (see §10 / OQ-2 — repro needed) in the same formatter pass.
Result: **`zenc fmt` stops erasing `MutPtr`/`RawPtr`.** Re-format the whole tree once; the
diff is exactly the restored `MutPtr`/`RawPtr` spellings; **emitted C and seed unchanged.**
This alone closes the dangerous bug and is independently shippable.

### Stage 2 — mutability checking
Reject `store`/write through `kPtr`. Audit + fix the (expected small) set of real
write-through-`Ptr` sites by re-spelling them `MutPtr`. Diagnostics with positions.
Seed identical (source re-spellings only re-format; C unchanged).

### Stage 3 — nullability checking
Require null-check / `assert_nonnull` before deref of `RawPtr<T>` (modulo the `RawPtr<u8>`
floor decision, OQ-3). Ship `assert_nonnull` intrinsic (6a). This is the **riskiest** stage
(most over-rejection potential); gate behind the audit and the floor exemption.

### Stage 4 — migrate the ~2200 sites to the right kinds
Mostly already correct (§3). Sweep for: `Ptr<…>` that are actually mutated (→ `MutPtr`),
`MutPtr<…>` never mutated and read-only (→ `Ptr`), `RawPtr` that are provably non-null
(→ keep or promote). The compiler's own `a: MutPtr<Malloc>` **stays `MutPtr`** (the
allocator is mutated through `acquire`). Driven by Stage 2/3 diagnostics, not a flag day.

## 9. Migration strategy — no flag day

- **Default kind for an un-migrated / ambiguous pointer = the most permissive for the
  operation in question.** Because all sites are *explicitly* spelled (there is no
  inferred/anonymous pointer type in source), the lever is the *checker*, not a default
  spelling: Stages 0–1 keep `fits`/`ty_eq` kind-blind, so **nothing is rejected** and all
  2200 sites keep compiling untouched. Checking is then turned on one capability at a time
  (mutability in S2, nullability in S3), each gated by an audit.
- **`null_ptr()` / `RawPtr<u8>` stays the permissive wildcard** to avoid a compiler-wide
  migration of optional AST pointers and raw allocator results; it remains a known unsafe boundary.
- **`.addr()` → `MutPtr` + `MutPtr→Ptr` widening** is what keeps the ~126 `.addr()` sites
  and the AST-node-pointer code legal with zero edits.
- The compiler's `MutPtr<Malloc>` allocator threading (967 sites) is **correct as-is and
  unchanged**.
- No `--strict-ptr` flag needed: the enforcement *is* the new checker rule; we land S2 only
  once the tree is clean under S2, etc. (the audit precedes the rule, not vice-versa).

## 10. Risks & over-rejection concerns

1. **`RawPtr<u8>` cursors (Stage 3).** `write_str`/`pf_write`/buffer code dereferences raw
   `u8*` cursors without an explicit null-check. Requiring `assert_nonnull` on all of them
   is churn and arguably noise (these are freshly-`acquire`d, non-null by construction).
   Mitigation: exempt the `RawPtr<u8>` floor from the null-check rule (OQ-3), or thread
   `acquire` results as `[u8]` slices.
2. **Mirror `Ty` copies** in `std/internal/ast.zen` and `resolve.zen` must track the genc
   `Ty` shape change exactly, or the resolver/light-checker desyncs. One-time coordinated
   edit; low risk but must be in the same commit as Stage 0.
3. **Generic unification** must stay kind-blind (§7) or `MutPtr<A>` params over-reject.
   Explicitly designed for; flag for review.
4. **`.addr()`-as-`MutPtr` of an immutable binding.** `.addr()` of a `let`-bound (non-`mut`)
   value yields `MutPtr`, which then permits a write — a soundness gap vs. Zen's
   mutability story. Tolerable now (Zen doesn't track `let` vs `mut` immutability for
   pointers yet); note it as a known limitation, not a Stage-1–3 blocker.
5. **Seed/regen discipline** (per the seed-commit-order rule): re-format the tree only
   AFTER the new pretty is in the seed, then regen + commit the seed last. A commit-then-
   regen ships a stale seed that still erases kinds.

## 11. OPEN QUESTIONS for the user

- **OQ-1 (null-check idiom).** Ship `assert_nonnull` (panic-on-null intrinsic, 6a) as the
  Stage-3 required idiom, with match-narrowing (6b) as a later zero-cost path? Or hold
  Stage 3 until 6b flow-narrowing is built so deref needs no runtime guard? (Recommend:
  6a now, 6b later.)
- **OQ-2 (scope of Stage 1).** Confirm the "comment-relocation bug" to fold into Stage 1 —
  I could not produce a standalone repro in this pass; is it a known case (e.g. a comment
  attached to a pointer-typed decl/param being moved by the formatter)? A repro lets me
  scope it; otherwise Stage 1 ships the pointer-preservation fix alone and the comment bug
  is tracked separately.
- **OQ-3 (RawPtr<u8> floor).** Should `RawPtr<u8>` be **exempt** from the Stage-3
  null-check rule (treat the raw byte buffer as the trusted primitive), or do we want even
  byte cursors to be null-checked — pushing buffer code toward `[u8]` slices over time?
  This decides how invasive Stage 3 is (318 `RawPtr<u8>` sites).

(Secondary, lower-stakes: should `.addr()` be `MutPtr` always, or `Ptr` for receivers
that only read? — §5 recommends always-`MutPtr`+widen for simplicity.)
