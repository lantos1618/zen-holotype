# Reference Capabilities as a Third Type Axis

**Status:** design only (no code). 2026-07-09.
**Thesis under test:** "everything is a type" — make memory/aliasing/send safety a third
type axis (Pony-style reference capabilities) so the single `fits()` check enforces them,
retiring the three separate passes.

**Bottom line up front:** the thesis is *half* right, and the half it gets right is the half
already implemented. `fits()` today *already* enforces two capability facets (direction and
nullability). Sendability is *already* a pure type predicate and folds cleanly into a shared
cap vocabulary. But **uniqueness (iso/affine) and escape (lifetime/region) are flow-sensitive
substructural properties that no pure `fits(g, w)` type-pair predicate can express** — they
need either a linear-typing context or regions, both far larger than "a third axis." The right
move is a unified `cap` classification consulted *everywhere*, plus a `cap_fits` rule in `fits`;
**not** a fold of the flow-sensitive passes into `fits`.

---

## 1. CURRENT STATE (grounded)

### 1.1 What axes a `Ty` carries today

`Ty` is a flat sum (`zen/compiler/genc.zen:209`):

```
Ty*: I32 | I64 | U8 | F64 | Bool | Named(string_view) | Void
   | StringView | StringCstr | StringLiteral
   | Ptr(PtrData) | Slice(Ptr<Ty>) | FnT(FnTData) | Generic(GenericData)
```

Two of the proposed capability facets are **already carried**, not as a dedicated axis but
derivable from existing structure:

- **Direction** — `PtrData` (`genc.zen:205-208`) is `{ pointee: Ptr<Ty>, kind: i32 }` with
  `kind ∈ {k_raw_ptr()=0, k_ptr()=1, k_mut_ptr()=2}` (`genc.zen:202-204`). `k_ptr` = read-only
  borrow, `k_mut_ptr` = writable borrow, `k_raw_ptr` = nullable FFI floor.
- **Nullability** — derived from the same kind: `is_nullable_ptr_ty` (`check.zen:4533`) is true
  only for `RawPtr<T>` where `T != u8` (the `u8` byte-buffer floor derefs freely).
- **Ownership / uniqueness** — carried as a **named-type wrapper**, not a Ty field:
  `owner_base(t)` (`check_validate.zen:1372`) reads `Generic.name` / `Named`, and
  `is_owner_base(b)` (`check_validate.zen:1521`) recognizes `Own` / `Rc` / `Arc`. So "iso" is
  spelled `Own<T>`, "shared" is `Arc<T>`, in the ordinary generic-instance machinery.

So a capability does **not** need a new Ty node — every ingredient already exists as a
predicate over `PtrData.kind` + the `Own/Arc/Rc` generic wrapper. (Detail in §2.)

### 1.2 How `fits()` works

`fits` is a **pure binary predicate** `(g: Ty, w: Ty) bool` — "does a value of type `g` fit a
slot of type `w`" (`check.zen:4540-4543`):

```
ptr_kind_fits* = (g: Ty, w: Ty) bool {
    (w.ptr_kind_of() == k_mut_ptr() && g.ptr_kind_of() == k_ptr()).match ({ true => false, false => true }) }
fits* = (g: Ty, w: Ty) bool {
    numeric := g.ty_rank() >= 0 && w.ty_rank() >= 0
    numeric.match ({ true => g.ty_rank() <= w.ty_rank(),
      false => g.is_raw_ptr_ty().match ({ true => w.is_ptr_ty_g(),
        false => (g.is_nullable_ptr_ty() && w.is_nonnull_ptr_ty()).match ({ true => false,
          false => g.ty_eq(w) && g.ptr_kind_fits(w) }) }) }) }
```

`fits` already decides **three** things: numeric rank widening (`ty_rank`), the deliberately
permissive `RawPtr<u8>` floor, and — the point — **two capability facets**:

- **Nullability subtyping**: a nullable `RawPtr<T>` does **not** fit a non-null `Ptr`/`MutPtr`
  slot (`check.zen:4526-4528`, `4542`).
- **Direction subtyping**: a read-only `k_ptr` value does **not** fit a writable `k_mut_ptr`
  or writable `k_raw_ptr` slot. `MutPtr→Ptr` and `MutPtr→RawPtr` remain safe.

`fits` is called ~19× across `check_validate.zen` for assignment-fit, return-fit, arg-fit,
struct-field-fit (`check_validate.zen:865,1170,1178,1212,1219,3029,…`). **Crucially it is
position-symmetric-ish: always "value type vs slot type," never a unary "is this type OK
here."** That property is what makes some safety facets fit and others not (§3).

### 1.3 The three separate passes — exact entry points

All three are module-level diagnostics wired into the `cd_or` precedence chain in
`driver.zen:40` (`check_diag_no_main`): first failing channel is the reported root; the main
type channel (`check_module_batch`) is separate. There are **19** such
`_diagnostic_from_source*` channels in `check_validate.zen`.

**(A) Ownership / consume — flow-sensitive, interprocedural.**
- Core: `own_step = (a, env, seen: Ptr<DeadList>, al: Ptr<AliasList>, st: Stmt) Ptr<DeadList>`
  (`check_validate.zen:2121`). Per-function driver `own_check_func` (`:2232`); module entry
  `check_module_ownership_diagnostic_from_source`.
- It **threads a `DeadList`** statement-by-statement: kill on consume
  (`consume_name`, `:2124`), on allocator free (`alloc_free_stmt_name`, `:2130`), on
  interprocedural move (`own_stmt_call_kills`, `:2145`), on struct-field/slice move
  (`own_stmt_struct_kills`, `:2148`), on affine copy `c := o` (`own_move_src`, `:2150`); and
  **revives** on rebind (`rebind_stmt_name`, `:2157`). Interprocedural summary
  `fn_consumes_param(env, fn, pi, depth)` (`:1439`, bounded `consume_depth()=4`, `:1437`).

**(B) Escape — flow-sensitive, lifetime/region.**
- Core: `escape_step = (a, svars: Ptr<DeadList>, derived: Ptr<DeadList>, st: Stmt) Ptr<DeadList>`
  (`check_validate.zen:4989`), driver `escape_check_func` (`:5058`); value-position escape
  `expr_escapes` (`:4929`). Two sibling passes share the shape: addr-of-local escape
  `ae_check_func` (`:5426`) and scratch-escape (`check_module_scratch_*`). Module channels
  `check_module_escape_*` / `check_module_addr_escape_*` / `check_module_scratch_*`.
- Threads `svars`/`derived` dead-lists tracking which scope-owned pointers have flowed where.

**(C) Sendability — ALREADY pure-type.**
- Core classifier: `ty_reaches_mutptr(decls, t, depth)` (`check_validate.zen:1869`) — "does
  type `t` reachably expose a `MutPtr<T>` a receiver could mutate through?" Descends ptr
  pointees, struct fields, enum payloads, slice elems, generic args; **stops** at the opaque
  caps `sm_is_opaque_cap` = `Own/Arc/Rc/ReplyRef/ActorRef` (`:1880`).
- Applied as `ty_reaches_mutptr(infer_expr(e))` at send sites: `sm_msg_mut` (`:5632`),
  `sm_call_pos` (`:5647`), unified walk `sv_expr`/`sv_check_func` (`:5505,5543`), module entry
  `check_module_send_mut_*` (mode 1, `:5654`) and the sibling `check_module_send_rc_*`
  (mode 0, `:5564`). **No `DeadList`, no statement threading** — it is a type predicate
  evaluated at each send-argument position. The comment at `:5578-5616` is explicit: "read off
  the payload's TYPE (Pony reference-capabilities, NOT a verb)… SOUND THROUGH A
  CALL/MEMBER/FIELD… the precision comes from the type predicate, not the syntax."

So of the three, **(C) is already the design the thesis wants**; (A) and (B) are substructural.

---

## 2. THE MODEL — capability as a derived axis

**Recommendation: derive the capability, do NOT add a Ty field.** Every input already exists.
Define a pure function (proposed home: `check_validate.zen`, next to `ty_reaches_mutptr`):

```
Cap: iso | val | mut | box            // (spelled as i32 constants like k_ptr(), or a tiny enum)

cap_of = (decls: [Decl], t: Ty) Cap {
    owner_base(t) == "Own"                 => iso   // unique, movable, sendable
    // Arc/Rc are their own shared caps; keep as today (send-rc pass), not in this lattice
    t is Ptr(kind=k_mut_ptr)               => mut   // Pony ref: aliasable + mutable, NOT sendable
    ty_reaches_mutptr(decls, t, 16) == false => val // deeply immutable (Ptr k_ptr / scalar / str) → sendable
    _                                      => box   // readonly Ptr that reaches a MutPtr → local alias only
}
```

Every predicate here already exists and is battle-tested:
`owner_base` (`:1372`), `ptr_kind_of` (`check.zen:4518`), `ty_reaches_mutptr` (`:1869`).
`cap_of` is a **pure function of `(decls, Ty)`** — and `decls` is already a field of `Env`
(`check.zen:166`). **No Env change, no new Ty node, no threading.** This is the single most
important structural fact in this document: it defuses the 29-Env-sites blast radius (§5).

### 2.1 The `fits` subtyping rule on caps

Aliasing/assignment subtyping (used by `fits`), read as "a `g`-cap value may satisfy a
`w`-cap slot":

| g \ w  | iso | val | mut | box |
|--------|-----|-----|-----|-----|
| **iso**| ✓   | ✓   | ✓   | ✓   | (unique can be frozen to val, borrowed mut/box)
| **val**| ✗   | ✓   | ✗   | ✓   | (immutable can't become unique or mutable; can be read-borrowed)
| **mut**| ✗   | ✗   | ✓   | ✓   | (writable borrow fits a readonly borrow — this IS `ptr_kind_fits` today)
| **box**| ✗   | ✗   | ✗   | ✓   |

Note the `mut→box` ✓ and `val→mut` ✗ cells are **exactly** what `ptr_kind_fits`
(`check.zen:4539`) already encodes (`k_ptr` value ⊄ `k_mut_ptr` slot; everything else ✓). And
`val`/`box` never fitting `iso` mirrors "you can't fabricate an `Own` from a borrow." So a
`cap_fits(g_cap, w_cap)` rule **subsumes `ptr_kind_fits` and would live inside `fits`
verbatim**, restoring the thesis at the *direction* axis with zero behavior change.

**But sendability is not an assignment-subtyping cell.** It is a *unary position requirement*
("this expression sits in a send-argument slot; its cap must be `∈ {iso, val}`"). `fits(g, w)`
has no `w` to name here — there is no "sendable type" to compare against. You can *model* it as
`fits(payloadTy, SendableBound)` only by inventing a `SendableBound` pseudo-type, which is
isomorphic to just calling `cap_sendable(cap_of(payloadTy))`. **The unification is in the
shared `cap_of` vocabulary, not in literally routing sends through `fits`.**

---

## 3. FOLD-IN MAP — what actually collapses, adversarially

| Pass | Can it fold into `fits`? | Why / why not |
|------|--------------------------|---------------|
| **(C) Sendability** | **Partially — into the cap vocabulary, not the `fits` call.** | Already pure-type (`ty_reaches_mutptr ∘ infer_expr`). Re-express its leaf as `cap_sendable(cap_of(t))`. It is checked at **send-argument position**, not at assignment position, so it shares `cap_of` with `fits` but keeps its own call site (the send-pass walk `sv_expr`). This is a genuine win: one cap lattice, three consumers. |
| **(A) Ownership / consume** | **NO — cannot become pure `fits`.** | It is **affine/linear and flow-sensitive**. `o: Own<T>` is legal to use *before* `release(o)` and illegal *after* — same variable, same type, different program point. `fits(g, w)` has no notion of program point; `own_step` exists *precisely* to thread the `DeadList` kill/revive state (`:2124-2160`). Linear typing needs a per-point substructural context, which `fits` is not and cannot be without becoming a dataflow pass. **What folds:** the *classification* "is this an iso?" is `cap_of(t)==iso`. **What doesn't:** the *enforcement* of use-once. |
| **(B) Escape** | **NO — cannot become pure `fits`.** | It is a **region/lifetime** property: "does this stack/scratch pointer outlive its frame?" (`expr_escapes`, `:4929`; `escape_step`, `:4989`). Types don't carry regions in Zen; `fits` compares shapes, not lifetimes. Expressing this in the type system means Rust-style lifetime parameters `Ptr<'a, T>` — a vastly larger change than "a third cap axis," and one the user has not asked for. **What folds:** nothing structural; escape stays a flow+region pass. |

**The sharp truth:** *of the three passes, only sendability is a pure type predicate, and it is
already implemented as one.* The other two are substructural (affine + region). No amount of
capability annotation turns a flow-sensitive property into a `fits(g,w)` cell — the same reason
Rust needs `borrowck` and lifetimes *in addition to* trait-`impl` subtyping. That is not a
defect in this design; it is the nature of uniqueness and lifetime.

**What the thesis genuinely buys:** a single `cap_of` that replaces the scattered
`owner_base` / `ptr_kind_of` / `ty_reaches_mutptr` / `is_nullable_ptr_ty` predicates with one
lattice consulted by (i) `fits` (direction + nullability + the `val→mut` guard), (ii) the send
pass (sendability = `iso|val`), and (iii) `own_step`/`escape` for *classification* (which
locals are iso and thus tracked). The passes keep their flow engines; they stop hand-rolling
"what kind of reference is this."

---

## 4. MINIMAL PoC — `val`-sendability through the shared cap

**Slice:** re-express the existing (sound, shipped) send-MutPtr classifier in terms of
`cap_of`, proving the derived cap reproduces the current acceptance set **byte-for-byte**. This
is the smallest change that demonstrates "cap is the single source of truth" without touching a
flow-sensitive pass.

**Touch (all in `zen/compiler/check_validate.zen`):**
1. Add `Cap` constants + `cap_of(decls, t)` next to `ty_reaches_mutptr` (~15 LOC), reusing
   `owner_base` / `ptr_kind_of` / `ty_reaches_mutptr`.
2. Add `cap_sendable(c) bool = c == iso || c == val` (~1 LOC).
3. Swap the classifier leaf in `sm_msg_mut` (`:5636`) and `sm_variant_decl_mut` (`:5630`) from
   `decls.ty_reaches_mutptr(ty, 16)` to `cap_of(decls, ty) not-in {iso,val}` — i.e.
   `cap_sendable` is false. (Behavior-identical: `iso` = `Own` was already opaque-cap-stopped
   at `:1880`, `val` = "reaches no MutPtr", `mut`/`box` = rejected.)

**~30–40 LOC net, one file, no Env change, no Ty change, no seed-structural change.**

**Proof / test (oracle):**
- All existing sendability cases stay green: `send(h, .Poke(mutptr))` rejected;
  `send(h, .Ro(ptr_to_immutable))` accepted; `send(h, own)` accepted; `send(h, value)`
  accepted; the launder/forwarder cases (`:5613-5627`) unchanged.
- Add one discriminating case proving the *derivation*: a struct `Frozen{x:i32,p:Ptr<i32>}`
  whose fields reach no MutPtr classifies `val` → send OK; a struct `Live{m:MutPtr<i32>}`
  classifies `mut` → send rejected. This shows `cap_of` — not the old bespoke predicate — is
  now driving the verdict.
- **Fixpoint byte-exact** (`make` self-rebuild) + full oracle green. Regenerate + commit the
  seed *after* final regen (MEMORY seed-commit-order rule).

**Follow-on PoC (optional, still 1 PR):** introduce `cap_fits(g_cap, w_cap)` and have `fits`
call it in place of `ptr_kind_fits` (`check.zen:4539,4542`). Pure refactor — must preserve the
`fits` acceptance set exactly (the `mut→box`/`val→mut` cells already match). This is the step
that literally puts the cap axis *inside* `fits`.

---

## 5. RISK / BLAST-RADIUS

- **Over-rejection.** `ty_reaches_mutptr` is already tuned (depth 16, opaque-cap stop at
  `:1880`, generic-arg-not-representation descent). Re-expressing must preserve the exact
  acceptance set; a coarser cap lattice would newly reject legitimate `Vec<i32>`-whose-buffer-
  is-`MutPtr` sends. Mitigation: `cap_of`'s `val` branch **is** `ty_reaches_mutptr == false`,
  so it is the same predicate — zero drift by construction. Guard with the discriminating test.
- **The Env / 29-sites concern is a non-issue for derivation.** There are 29 `Env(` construction
  sites (15 in `check.zen`, 14 in `check_validate.zen`) and 86 `infer_expr` call sites. If caps
  had to be *threaded* through `Env`, every one would churn. **They don't:** `cap_of(decls, t)`
  reads `decls` (already in `Env`, `check.zen:166`) + a `Ty` — no new Env field, no new
  parameter. This is the whole reason to *derive* rather than add a Ty node: it keeps the change
  local to the classification helpers.
- **Seed regen.** Any `check_validate.zen` edit changes the compiler → regenerate the bootstrap
  seed and commit it *after* the final regen, before push (MEMORY: two prior hotfixes #277/#281
  from getting this backwards).
- **Phased rollout.**
  1. **PoC** — `cap_of` + sendability re-expression (1 PR, ~40 LOC, §4).
  2. **`cap_fits` in `fits`** — subsume `ptr_kind_fits` + the nullability guard under the cap
     lattice (1 PR, pure refactor, acceptance-preserving). *This is where the thesis lands in
     `fits`.*
  3. **Shared vocabulary** — point `own_step`/`escape` classification helpers at `cap_of`
     (delete the ad-hoc `owner_base==Own` scatter), passes keep their flow engines (1 PR,
     de-slop, no behavior change).
  4. **(Not recommended now)** region/lifetime axis for escape, linear-context for ownership —
     multi-week, needs a real design of its own.

**1 PR or multi-week epic?** The *achievable, valuable* core (steps 1–3: unified cap vocabulary
+ `cap_fits` + sendability through caps) is **~2–3 PRs**. The PoC alone is **1 PR / ~40 LOC**.
The *literal* thesis — "one `fits()` enforces all memory safety, delete own_step + escape" — is
**not achievable at any PR count** without adding linear-typing contexts and regions, which is a
multi-week language-design epic and arguably the wrong trade.

---

## 6. VERDICT

**Folding-into-`fits` is the right call for exactly the facets that are already type-pair
relations, and the wrong call for the two that are substructural.**

- **Direction and nullability** are *already inside `fits`* (`ptr_kind_fits` + the nullable/
  non-null guard). Naming them caps and routing them through `cap_fits` is pure upside: it
  restores the "everything is a type" thesis at that axis with **zero behavior change**.
- **Sendability** is *already a pure type predicate* (`ty_reaches_mutptr ∘ infer_expr`). It
  cannot literally join a `fits(g,w)` call (it's a unary position requirement, not a type-pair),
  but it *should* share the one `cap_of` lattice. This is the highest-value, lowest-risk win and
  the correct PoC.
- **Uniqueness (iso/affine) and escape (lifetime/region) are inherently flow-sensitive and
  belong in a pass.** `o` before `release(o)` and `o` after are the same type at different
  program points; a stack pointer's escape is about lifetime, not shape. `fits` is a pure
  type-pair predicate and *must not* grow a program-point or region parameter — that would make
  it a dataflow engine, not a type check. The honest recommendation is: **let caps unify the
  classification, keep the flow-sensitive enforcement as passes that query the cap lattice.**

This is not a concession that the thesis fails — it is the same architecture every
capability-safe language converges on: Pony has reference capabilities *and* a separate
consume/aliasing analysis; Rust has trait subtyping *and* borrowck *and* lifetimes. Types
classify; a flow analysis enforces the substructural rules. Adopt the cap axis for the
classification unification and the `fits` facets it genuinely owns; do not chase folding the
flow-sensitive passes into `fits`.

**Recommended next action:** ship the §4 PoC (1 PR, ~40 LOC) — it proves `cap_of` reproduces the
shipped sendability check exactly, and lands the shared vocabulary the rest of the plan builds
on.
