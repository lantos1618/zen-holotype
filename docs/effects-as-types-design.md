# Effects Attached to Types — the uniform "everything is a type" model

**Status:** design only (no code). 2026-07-09.
**Supersedes/absorbs:** `docs/refcap-type-axis-design.md` (reference capabilities are now
*one effect family* inside this model — the ref-cap grounding is retained verbatim in §3–§4).

**The vision (user, category-theory framing).** One uniform shape for the whole language:

1. **define a type/structure** = an **object**
2. **attach effects to it** = **morphisms** / equipping the object with structure
   (today spelled `impl(Trait, {…})`)
3. **instantiate values tied to it** = **elements**
4. **chaining** = **composition** — UFCS `x.f().g()`, first-class fns, and `.or_return()`
   which is **already monadic bind**

The general primitive: *a type carries its attached **effects** (alloc / io / mut / send /
own), and those effects compose categorically the same way `Result`/`Opt` already compose via
`or_return`.* Reference capabilities (iso/val/mut/box) are then just the **aliasing effect
family** — one column of a wider table that also holds allocation (the Sys/allocator epic #47),
sendability, and ownership.

**Bottom line up front.** The categorical framing has *one genuinely real anchor* —
`or_return` is a true monadic bind (§5, `check.zen:1718`). Around that anchor the unification is
**partly real, partly decorative**: sequencing/short-circuit effects (Result/Opt, and a future
IO/alloc-threading) *do* compose as morphisms; aliasing/lifetime constraints (ref-caps, escape)
are **predicates on objects, not morphisms between them** — they don't "compose," they're
*discharged*. Treating both as "effects attached to types" is a useful *notation* but a
misleading *mechanism*. The buildable core is: **(a) name the effect a type carries explicitly,
(b) let `fits()` + `or_return` compose the ones that are genuinely compositional, (c) keep the
substructural ones (alias/lifetime/uniqueness) as flow-sensitive checks that *query* the effect,
not fold into it.** Smallest first step in §7.

---

## 1. CURRENT STATE (grounded)

### 1.1 What a `Ty` carries today

`Ty` is a flat sum (`zen/compiler/genc.zen:209`):

```
Ty*: I32 | I64 | U8 | F64 | Bool | Named(string_view) | Void
   | StringView | StringCstr | StringLiteral
   | Ptr(PtrData) | Slice(Ptr<Ty>) | FnT(FnTData) | Generic(GenericData)
```

Facets already present and derivable (no dedicated axis field):

- **Direction** — `PtrData = { pointee: Ptr<Ty>, kind: i32 }` (`genc.zen:205-208`),
  `kind ∈ {k_raw_ptr()=0, k_ptr()=1, k_mut_ptr()=2}` (`genc.zen:202-204`).
- **Nullability** — `is_nullable_ptr_ty` (`check.zen:4533`): only `RawPtr<T>` (T≠u8) is nullable.
- **Ownership/uniqueness** — a *named-type wrapper*: `owner_base(t)` (`check_validate.zen:1372`)
  reads `Generic.name`; `is_owner_base` recognizes `Own`/`Rc`/`Arc` (`check_validate.zen:1521`).
- **Result/Opt "effect"** — an ordinary `Generic("Result", [Ok, Err])` enum, given sequencing
  by the `or_return` desugar (§5).

So "effects" are today spread across three encodings — a `PtrData.kind` int, a `Generic` name
wrapper, and a desugaring pass. The vision asks: *can they be one thing?*

### 1.2 `fits()` — the composition engine that already exists

`fits(g: Ty, w: Ty) bool` (`check.zen:4540-4543`) is a **pure type-pair predicate**. It already
decides numeric rank widening, the `RawPtr<u8>` floor, and **two capability facets**:

```
ptr_kind_fits* = (g, w) bool { (w.ptr_kind_of()==k_mut_ptr() && g.ptr_kind_of()==k_ptr()).match({true=>false,false=>true}) }
fits* = (g, w) bool {
  numeric := g.ty_rank()>=0 && w.ty_rank()>=0
  numeric.match({ true => g.ty_rank()<=w.ty_rank(),
    false => g.is_raw_ptr_ty().match({ true => w.is_ptr_ty_g(),
      false => (g.is_nullable_ptr_ty() && w.is_nonnull_ptr_ty()).match({ true=>false,
        false => g.ty_eq(w) && g.ptr_kind_fits(w) }) }) }) }
```

- **Direction subtyping**: read-only `k_ptr` value ⊄ writable `k_mut_ptr` slot (`ptr_kind_fits`,
  `check.zen:4539`).
- **Nullability subtyping**: nullable `RawPtr<T>` ⊄ non-null slot (`check.zen:4526-4528`).

`fits` is called ~19× for assign/return/arg/field fit (`check_validate.zen:865,1170,1178,1212,
1219,3029,…`). It is **position-symmetric**: always "value type vs slot type," never a unary
"is this type OK in this position." That property is exactly what separates the effects that
fold into it from those that can't (§6).

### 1.3 The three separate safety passes (entry points)

Wired into the `cd_or` precedence chain in `driver.zen:40` (first failing channel = reported
root; 19 `_diagnostic_from_source*` channels total).

- **(A) Ownership/consume — flow-sensitive, interprocedural.** Core
  `own_step = (a, env, seen: Ptr<DeadList>, al: Ptr<AliasList>, st) Ptr<DeadList>`
  (`check_validate.zen:2121`); driver `own_check_func` (`:2232`); kills on consume
  (`:2124`), free (`:2130`), interproc move (`own_stmt_call_kills`, `:2145`), struct/slice move
  (`:2148`), affine copy (`:2150`); **revives** on rebind (`:2157`). Interproc summary
  `fn_consumes_param` (`:1439`, bounded `consume_depth()=4`).
- **(B) Escape — flow-sensitive, lifetime/region.** `escape_step` (`:4989`),
  `escape_check_func` (`:5058`), value-escape `expr_escapes` (`:4929`); siblings addr-escape
  `ae_check_func` (`:5426`) and scratch-escape. Threads `svars`/`derived` dead-lists.
- **(C) Sendability — ALREADY pure-type.** `ty_reaches_mutptr(decls, t, depth)` (`:1869`) ∘
  `infer_expr`, applied at send sites `sm_msg_mut` (`:5632`) / `sm_call_pos` (`:5647`), module
  entry `check_module_send_mut_*` (`:5654`). No `DeadList`. The comment at `:5578-5616` is
  explicit: "read off the payload's TYPE (Pony reference-capabilities, NOT a verb)."

---

## 2. THE MODE MODEL — one effect family, derived not stored

> **NAMING (locked 2026-07-09).** The umbrella is **`mode`**, not "cap"/"capability" — `cap`
> misreads as *capacity* and "capability" is already taken by the Sys/allocator epic (#47). The
> four modes are spelled in plain Zen: **`owned`** (Pony iso) · **`frozen`** (val) · **`mut`**
> (ref) · **`read`** (box). Functions: **`mode_of`**, **`mode_fits`**, **`mode_sendable`**.

**Recommendation: derive the mode; do NOT add a Ty field.** Every input already exists.

```
Mode: owned | frozen | mut | read                       // spelled as i32 consts, like k_ptr()
mode_of = (decls: [Decl], t: Ty) Mode {
    owner_base(t) == "Own"                   => owned    // unique, movable, sendable
    t is Ptr(kind=k_mut_ptr)                 => mut      // aliasable+mutable, NOT sendable
    ty_reaches_mutptr(decls, t, 16) == false => frozen   // deeply immutable → sendable, aliasable
    _                                        => read     // readonly Ptr reaching a MutPtr → local alias only
}
```

`mode_of` is a **pure function of `(decls, Ty)`**, and `decls` is already a field of `Env`
(`check.zen:166`). **No Env change, no new Ty node, no threading** — this single fact defuses the
29-Env-sites blast radius (§ risk). `Arc`/`Rc` keep their own shared treatment (the existing
send-rc pass, `:5564`).

### 2.1 The `fits` subtyping rule on modes

| from \ to | owned | frozen | mut | read | note |
|-----------|-------|--------|-----|------|------|
| **owned** | ✓ | ✓ | ✓ | ✓ | unique can be frozen/borrowed |
| **frozen**| ✗ | ✓ | ✗ | ✓ | immutable can't become unique/mutable |
| **mut**   | ✗ | ✗ | ✓ | ✓ | **= `ptr_kind_fits` today** (mut→read ✓) |
| **read**  | ✗ | ✗ | ✗ | ✓ | |

The `mut→read ✓` / `frozen→mut ✗` cells are *exactly* `ptr_kind_fits` (`check.zen:4539`); "can't
fabricate `owned` from a borrow" mirrors reality. So a `mode_fits(from, to)` rule **subsumes
`ptr_kind_fits` inside `fits` with zero behavior change**.

---

## 3. FOLD-IN MAP — what collapses, adversarially

| Pass | Fold into `fits`? | Why |
|------|-------------------|-----|
| **(C) Sendability** | **Partially — into the shared `mode_of`, not the `fits` call.** | Already pure-type. Re-express its leaf as `mode_sendable(mode_of(t)) = mode ∈ {owned,frozen}`. Checked at *send-argument position*, not assignment position, so it shares `mode_of` with `fits` but keeps its own walk (`sv_expr`, `:5505`). Genuine win: one lattice, three consumers. |
| **(A) Ownership** | **NO.** | **Affine + flow-sensitive.** `o: Own<T>` is legal *before* `release(o)` and illegal *after* — same type, different program point. `fits(g,w)` has no program point; `own_step` exists precisely to thread the `DeadList` (`:2124-2160`). Folds only the *classification* (`mode_of==owned`), never the use-once *enforcement*. |
| **(B) Escape** | **NO.** | **Region/lifetime.** "Does this pointer outlive its frame?" (`expr_escapes`, `:4929`). Zen types carry no region; expressing it means Rust-style lifetime params — far larger than a cap axis. |

**Sharp truth:** of the three, only sendability is a pure type predicate, and it is already one.
The other two are substructural (affine + region). No capability annotation turns a
flow-sensitive property into a `fits(g,w)` cell — the same reason Rust needs `borrowck` +
lifetimes *in addition to* trait subtyping.

---

## 4. MINIMAL PoC (Brick 1) — `frozen`-sendability through the shared mode

Re-express the shipped, sound send-MutPtr classifier in terms of `mode_of`, proving the derived
mode reproduces the current acceptance set byte-for-byte.

**Touch (all `check_validate.zen`):** add `Mode` consts + `mode_of` next to `ty_reaches_mutptr`
(~15 LOC); add `mode_sendable` (~1 LOC); swap the classifier leaf in `sm_msg_mut` (`:5636`) and
`sm_variant_decl_mut` (`:5630`) to `mode_sendable(mode_of(decls, ty)) == false`. Behavior-identical
(`owned`=`Own` opaque-stopped at `:1880`; `frozen`=reaches-no-MutPtr; `mut`/`read`=reject).
**~30–40 LOC, one file, no Env/Ty change.**

**Proof:** existing oracle sendability cases stay green (`send(.Poke(mutptr))` rejected;
`send(.Ro(ptr→immutable))` ok; `send(own)` ok; `send(value)` ok; launder/forwarder `:5613-5627`
unchanged) + one discriminating case (a `frozen` struct sends OK, a `mut`-reaching struct
rejects — proving `mode_of` drives the verdict). Fixpoint byte-exact; regen+commit seed *after*
final regen (MEMORY seed-commit-order).

**Follow-on (Brick 2, 1 PR):** `mode_fits(from, to)` replacing `ptr_kind_fits` inside `fits`
(`check.zen:4539,4542`) — pure refactor, acceptance-preserving. This is the step that literally
puts a mode axis *inside* `fits`.

---

## 5. EFFECTS-AS-STRUCTURE — how an effect attaches to a type in Zen

Three candidate mechanisms already live in the codebase. Grounding each:

### 5.1 The `Generic` wrapper (structural effect) — REAL, in use
`Own<T>` / `Rc<T>` / `Arc<T>` / `Result<T,E>` / `Opt<T>` are all `Generic(name, args)` nodes.
The "effect" is *the wrapper name*, read by `owner_base` (`:1372`) / `sm_is_opaque_cap` (`:1880`).
This is the **object equipped with structure**: `T` is the object, `Own<·>` is the equipping
functor. It is already how ownership and error-carrying are attached.

### 5.2 `impl(Trait, {…})` (behavioral effect) — REAL, in use
`ImplData` (`genc.zen:266`) records `Type.impl(Trait, {methods})`. This is the **morphism-set**:
equipping an object with named operations. The `Allocator` trait is exactly this — the free
surface (`release`/`resize`) is fixed by conformance (`check_validate.zen:1902`). So "attach an
effect" = "impl a trait" is not aspirational; the allocator/actor machinery already works this
way.

### 5.3 `or_return` (the sequencing effect) — REAL monadic bind
**This is the one genuinely categorical anchor.** `lower_or_return_let` (`check.zen:1718-1728`)
desugars `x := recv.or_return()` into:

```
_tmp := recv                               // bind M a
if _tmp.tag == Err { return _tmp.Err }     // fail / short-circuit  (:1726)
x := _tmp.Ok                               // extract a, continue with (a -> M b)  (:1727)
```

That is exactly `bind : M a → (a → M b) → M b` for the `Result`/`Opt` monad, with the function
tail as the continuation and `return Err` as `fail`. `or_return` is legal in *any* expression
position and hoists innermost-first, left-to-right (`:1740-1762`) — i.e. it sequences effects in
evaluation order. **So Zen already has do-notation for one effect monad.** The categorical claim
"effects compose like `Result` does via `or_return`" is *literally true for effects that are
monads*.

### 5.4 Is the categorical claim real or decorative? — SPLIT
- **Real** for *sequencing/short-circuit* effects: `Result` (errors), `Opt` (absence), and a
  *future* IO/alloc-threading effect could all be `M<T>` enums with an `or_return`-style bind.
  These genuinely compose associatively with a unit — they are monads, and `or_return` is their
  bind. Adding a new one of this shape is a *real, uniform* extension.
- **Decorative** for *aliasing/lifetime/uniqueness* effects (ref-caps, escape, ownership use-
  once). These are **predicates on an object** (or on a *pair* of program points), not morphisms
  `A → B`. "`o` is iso" does not *compose* with "`p` is val" the way `bind` composes `M a` with
  `a → M b`; there is no unit, no associative `∘`. Calling them "effects that compose" borrows
  monad vocabulary for something that is really *constraint discharge*. The honest category-
  theory reading: ref-caps are a **refinement/subtype lattice** (a poset, discharged by `fits`),
  Result is a **monad** (composed by `or_return`), and *those are different structures.* One
  notation ("effect attached to a type") can *spell* both, but the mechanisms don't merge.

---

## 6. THE CENTRAL DIAL — visibility of the effect algebra

Prior art on the declared-vs-inferred axis:
- **Pony**: caps are *sigils* on every type (`String iso`, `String val`) — declared, terse,
  ever-present. High ceremony, fully visible.
- **Koka**: effect *rows* inferred and propagated automatically — invisible until a signature
  forces them. Low ceremony, low visibility.
- **Haskell**: `IO`/monad in the *type signature*, `do` composes silently — declared at
  boundaries, composed invisibly inside.

**Zen's ethos is fixed by precedent, not open:** the team *killed* ambient-rt in favor of an
explicit `Sys` capability (#47), and *rejected* `share`/`view` sendability verbs in favor of a
type-read capability (task #4). The standing rule is **"ceremony you can see > magic you can't."**
That rules out Koka-style full inference. It also rules out Pony-style sigil-on-every-binding
(too much ceremony on locals).

**Proposed split (the recommendation):**

> **DECLARE the effect on the type boundary; COMPOSE it silently via `fits` + `or_return`.**

This is the *Haskell* point on the dial, adapted to Zen's spelling:

- **Declared, visible** — at the two boundaries that already exist:
  - **Type definitions**: the wrapper *is* the effect. `Own<T>` (owns), `Ptr<T>`/`MutPtr<T>`
    (borrow direction), `Result<T,E>` (can-fail), and — the extension — a future `IO<T>` /
    threading a `Sys`/allocator param. No new syntax; the effect is the type you already wrote.
  - **Function signatures**: an effect a function *requires* shows up as a *parameter* (the
    `Sys`/allocator capability, #47) or as its *return wrapper* (`Result<T,E>`). Effects are
    thus visible exactly where a caller must care — the signature — and nowhere else.
- **Composed, silent** — inside a body:
  - Aliasing/direction/sendability compose through `fits`/`cap_of` (no annotation on locals —
    `cap_of` *derives* the cap; you never write `x val`).
  - Sequencing composes through `or_return` (`x := f().or_return()` — the `.or_return()` is the
    *visible* bind marker; the Err-threading is silent).

**Syntax sketch (all existing surface — the point is that no new syntax is needed):**

```
// (1) OBJECT: a plain type
Config: { retries: i32, host: str }

// (2) EFFECTS attached, all at the boundary, all visible:
//   - `Own<Config>`  : the ownership effect (unique, must be released)
//   - `s: Sys`       : the ambient/IO+alloc effect, an explicit parameter (#47)
//   - `Result<…,E>`  : the failure effect, the return wrapper
load = (s: Sys, path: Ptr<Config>) Result<Own<Config>, IoError> {
    raw := s.read_file(path).or_return()        // (4) COMPOSITION: bind, Err threads silently
    cfg := s.alloc(parse(raw)).or_return()      //     alloc effect flows through `s`, error via or_return
    ok(cfg)                                      //     `cfg: Own<Config>` — ownership effect visible in the type
}

// caller sees EVERY effect in the signature: needs a Sys, gets back an owned Config-or-error.
// inside, cap_of derives that `cfg` is `iso`; send/assign/return checks compose it via fits — no local annotation.
```

The dial setting: **effects are declared on types and signatures (visible where a caller
decides), and composed by `fits` + `or_return` (silent where only the compiler decides).** That
is the maximum "everything is a type" uniformity Zen's no-magic ethos actually permits.

---

## 7. HONEST VERDICT

**Is "effects attached to types, composing like morphisms" one coherent buildable primitive?**

**No — it is two coherent primitives wearing one name, plus a genuine notational win from
unifying their *declaration*.** Be adversarial about it:

1. **A heap allocation is not the same kind of thing as an aliasing constraint.** Allocation/IO/
   error are *sequenced, world-threading* effects — they are monads, they compose with `bind`,
   `or_return` already *is* their composition (`check.zen:1718`). Aliasing/uniqueness/lifetime
   are *refinement constraints on a value* — a subtype lattice discharged by `fits`
   (`check.zen:4540`) and by two flow-sensitive passes. These are **different mathematical
   structures** (monad vs poset + substructural context). Forcing them under one "effect algebra"
   is wishful where it claims a shared *mechanism*.

2. **What IS uniformly real:** the *declaration* surface. Every effect — ownership (`Own`),
   direction (`Ptr`/`MutPtr`), failure (`Result`), the alloc/IO capability (`Sys`, #47) — can be
   spelled the *same way*: **a type wrapper or a signature parameter, visible at the boundary.**
   And the two *compositional* effects (error/absence, and any future IO monad) genuinely share
   one bind (`or_return`). That much is one coherent story and it is already 70% built.

3. **What is NOT real:** a single `fits()` (or a single monad) that enforces alloc + io + mut +
   send + own together. Sendability folds (it's already type-based); direction+nullability are
   already *in* `fits`; but ownership use-once (affine) and escape (region) are flow-sensitive and
   will **always** need a pass. Any claim that one check subsumes all five is the wishful part.

**Recommendation — smallest real first step (no multi-month rewrite):**

> **Ship the §4 PoC: `cap_of` + re-express sendability through it (1 PR, ~40 LOC), then the
> `cap_fits`-inside-`fits` refactor (1 PR).**

This is the smallest change that *proves the uniform-declaration thesis on real code*: one
`cap_of` lattice becomes the single source of truth for the aliasing effect, consulted by
`fits` (direction), the send pass (sendability), and — as *classification only* —
`own_step`/`escape`. It restores "everything is a type" for the effect family that is *actually*
a type property, with zero behavior change and zero new syntax, and it leaves a clean seam to
later add an `IO`/`Sys` monad on the *`or_return` side* of the split (the genuinely
compositional side) when #47 lands. It commits to **nothing** that would require an effect-row
inference engine or a lifetime system — the two things Zen's ethos and budget both reject.

Do **not** attempt a unified effect-row system. The categorical framing is a good *design
compass* (declare effects on types; compose the monadic ones with `or_return`; discharge the
substructural ones with `fits` + a flow pass) but a bad *implementation blueprint* if read as
"one algebra enforces everything." Build the compass-true version: uniform *declaration*, honest
*two-mechanism* composition.
