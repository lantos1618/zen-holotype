# DESIGN — static UAF / double-free / escaping-pointer checker (goal part A)

Status: **Part 1 (allocator UAF / double-free + revival) and Part 2 (escaping local pointer) both
IMPLEMENTED & verified** — adversarial reject/accept pass, 0 over-rejection across all 54 zen sources,
`make oracle` green, fixpoint byte-exact. Extends the lexical `DeadList` passes in `check_validate.zen`.

Part 2 (`check_module_addr_escape*`): a SEPARATE pass (cannot reuse the scope walker — a general
allocator's `a.acquire(n)` returns heap that legitimately outlives the call). Collects the function's
Let-locals, taints `<local>.addr()`, forwards it through `slice(...)`/struct/match/cond/block, and flags
it in return/trailing position with a precise `error[escape]` diagnostic. Wired into `driver.check_diag`
after the scope-escape step. v1 does NOT track let-aliasing of an addr, heap-store aliasing, or
inter-procedural escape (documented; the over-rejection sweep showed the stdlib never returns addr-of-local).

Implemented (Part 1): `alloc_free_call_name` recognises `a.release(p)` / `a.resize(p,n)` (old ptr) /
raw `free(p)` and marks the freed bare-local dead; `dead_remove` revives a local on rebind; `own_step`
threads both; assign-target rebinds are not counted as uses. Adversarially verified — UAF, double-free,
and allocator-release-then-use are REJECTED with positions; `p = a.resize(p,n)` and free-rebind-reuse are
ACCEPTED. Polish TODO: the diagnostic still reads "use of an owner after release/drop" (ownership kind) —
fine in spirit, but a dedicated "use after free" message would read better for the raw-pointer case.

## What already exists (don't rebuild)
- `check_module_ownership` — threads a `DeadList` of consumed names through a function body and flags
  use-after-`release`/`drop`/`release_in`/`drop_in` on **Own / Rc / Arc** (use-after-move + double-free
  for the *ownership types*). Hint: "bind a fresh owner instead of reusing the consumed local."
- `check_module_escape` (M5) — taints values derived from a **`Scope` param** (`s.acquire(...)`, `s.alloc`)
  and flags returning them. Narrow to `Scope`.

Both are **lexical, conservative, straight-line** (branches/loops thread the kill-set forward; no merge/
dataflow). They run on raw pre-inline decls. This design keeps that philosophy.

## The gaps to close
1. **Raw-pointer UAF / double-free** — `a.free(p)` / `free(p)` then later `load(p)` / `p.offset(..)` /
   pass `p` / `free(p)` again. Not caught today (only Own/Rc/Arc are).
2. **Escaping pointer/slice to a local** — `return local.addr()`, `return slice(local.addr(), n)`, or
   storing such into an out-param / escaping aggregate. Not caught today (only `Scope` is).

## Proposed design

### Part 1 — allocator-centric free → UAF / double-free (reuses `own_*`)
Zen's memory model is **explicit allocator threading**, NOT raw malloc/free. The free surface is the
`Allocator` trait (`std.mem.alloc`):

    Allocator: { acquire: (MutPtr<Self>, i64) RawPtr<u8>,    // allocate
                 resize:  (MutPtr<Self>, RawPtr<u8>, i64) RawPtr<u8>,  // realloc — FREES the old ptr
                 release: (MutPtr<Self>, RawPtr<u8>) void }   // free

Because trait conformance fixes the method *names*, keying on `release` / `resize` (when the receiver is
an allocator) is automatically **generic over every allocator** — built-in `Heap`/`Malloc` and any
user-defined one. We do NOT hardcode libc `free`.

- **`a.release(p)`** → the pointer arg `p` is dead afterwards (UFCS: receiver=arg[0], freed ptr=arg[1]).
- **`a.resize(p, n)`** → the *old* `p` is dead afterwards (resize returns a NEW pointer). This is the
  realloc-UAF, and exactly the "ALWAYS USE THE RETURNED handle — the old one dangles" contract on
  `Map`/`Vec`. With revival (Q1), the idiomatic `p = a.resize(p, n)` rebinds `p` → not flagged;
  `q := a.resize(p, n); use(p)` IS flagged.
- raw **`free(p)`** (the FFI/bootstrap floor in `std.mem.alloc` + `std.c.libc`) → arg[0] dead. Rare in
  user code, tracked for completeness.
- Owner verbs (`release_in`/`drop_in` on Own/Rc/Arc) already handled by the existing pass.

**Detecting "receiver is an allocator" generically.** Two options:
  (a) trait-impl lookup — the receiver's type has an `impl(Allocator)` (DeclIndex knows types-with-impls;
      refine to Allocator specifically). Precise, handles user allocators by construction.
  (b) shape heuristic — method named `release`/`resize` with the allocator arity + `MutPtr<_>` receiver.
      Simpler, but a stray same-named method could false-positive.
Proposal: **(a)**, falling back to skip if trait info is unavailable (conservative = no false positive).

- After marking `p` dead, the existing `own_expr_err` `.Var` arm errors on ANY later use of a dead name →
  use-after-free AND double-free fall out uniformly.

**Subtlety — revival on rebind (review Q1).** Raw pointers are legitimately reused:
`p := malloc(); free(p); p = malloc(); use(p)`. The current cons-list never revives a name, so this
would be a FALSE POSITIVE. Proposal: a `Let`/`Assign` that rebinds a dead name to a fresh value
**removes** it from the kill-set (the standard moved-then-reinitialized rule). Needs kill-set removal
(cons-list has none today) — add a small "revived" overlay or rebuild the list without the name.

### Part 2 — escaping local pointer / slice
- Seed a `derived` taint set with **`X.addr()` where `X` is a non-pointer stack local** (a `Let`-bound
  value). That is a pointer INTO the current frame.
- Propagate through: simple aliases `q := p` (have: `expr_is_derived`), `.offset(...)`, `slice(<derived>, n)`,
  struct-literal field forwarding, match/cond/block value position (have: `expr_escapes` machinery).
- Flag `return <derived>` / trailing-yield `<derived>` / store of `<derived>` into a `MutPtr<T>` out-param.
- **Heap is fine to return**: `malloc()` / `a.acquire()` results and `Ptr<T>`/`MutPtr<T>` *params* point to
  caller/heap memory, NOT this frame → never tainted. Slice literals `[...]` are already heap-promoted
  (`gen_slicelit`) → never tainted.

### Explicit v1 non-goals (conservative boundary — review Q2)
- No alias-through-heap (`g.field = p; return g`). No inter-procedural escape (callee stashes a pointer).
- Branch/loop = straight-line thread (a free in one branch kills for the rest of the body — may
  over-reject; proper merge is future work). Ship conservative, widen behind the over-rejection sweep.

### Diagnostics
- New kinds `use-after-free`, `double-free`; extend `scope-escape` → `escape` naming the variable +
  file:line:col via the existing `kv_*` position walkers.

## Verification (adversarial, both directions)
REJECT: `free(p); load(p)` · `free(p); free(p)` · `return local.addr()` · `return slice(local.addr(), n)`.
ACCEPT (no over-rejection): `p:=malloc(); free(p); p=malloc(); use(p)` (revival) · `return <Ptr param>` ·
`return malloc()`-derived · **the whole stdlib + `make oracle` still check clean** · fixpoint byte-exact.

## Review decisions
1. **Revival** — YES, rebinding a freed/moved local revives it (avoids over-rejecting realloc/reuse). ✓
2. **Escape taint scope** — conservative v1 (direct `local.addr()` + simple aliases + struct forwarding;
   no heap-store-alias / inter-procedural). Widen later behind the over-rejection sweep. ✓
3. **Free surface** — the `Allocator` TRAIT, not raw libc names: `release` frees its ptr arg, `resize`
   frees the old ptr arg; generic over user allocators via trait conformance. Raw `free` tracked at the
   FFI floor. Owner `release_in`/`drop_in` already covered. ✓ (revised per review)

## Open implementation choice
- Allocator-receiver detection: (a) trait-impl lookup [precise, proposed] vs (b) name+arity shape
  heuristic [simpler, false-positive risk]. Default to (a), skip when trait info absent (no false pos).
