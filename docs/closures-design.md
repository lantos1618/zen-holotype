# First-class function values (closures) — design

Goal: make a lambda / function a real VALUE — storable in a struct field, returnable from a
function, passable and called dynamically — not only inline-spliced. Unblocks callbacks,
`std.store` reducers, event handlers, fn tables.

## Status

This doc covers the feature at two stages, merged here as the single source of truth:

- **M0 / M1 — non-capturing first-class function values (shipped path).** Named-fn values,
  fn-valued struct fields, non-capturing lambda values (lifted, `env = NULL`). The capturing case in
  a value position falls to the clean `error[lambda-value]` diagnostic (M1b/M1c). Covered in
  "[Current state](#current-state-fresh-main-e77d7de)" → "[Milestones & recommendation](#milestones--recommendation)" below.
- **M2 — capturing closures (proposed; NOTHING built).** A lambda that captures an enclosing local,
  used as an escaping value. The mechanics (an env struct) are easy; the env's *lifetime* under
  Zen's "explicit alloc, no hidden heap" rule is the open design decision. Covered in
  "[M2 — Capturing closures](#m2--capturing-closures-proposed-nothing-built)" below (folded in from the former
  `closures-m2-design.md`).

Note: a capturing lambda passed **directly to a HOF / `.loop`** is already inline-spliced today (zero
env, zero heap) — that common case is correct and is NOT what M2 is about. M2 is specifically the
*escaping* capturing closure.

## Current state (fresh main, e77d7de)

What the compiler does with `(args) { body }` / function names today:

| use of a fn/lambda | status | mechanism |
|---|---|---|
| lambda as a direct HOF arg `apply((n){n+1}, x)` | ✅ works | inline-spliced (`inline_lambda`/`xform_body`) — zero overhead |
| lambda in `.loop((h,i,x){…})` | ✅ works | parsed to a `Loop` node, not a Lambda |
| lambda bound to a local `g := (n){…}` then used | ✅ works | LAMBDA-2 alias-substitution: the local is a compile-time alias, spliced at uses |
| **named fn as a local value** `f := add; f(2,3)` | ✅ works | C `__auto_type f = add;` → real fn-ptr, direct `f(2,3)` |
| **named fn stored in a struct field** `Box(op: add)` then `b.op(4,5)` | ❌ | `b.op(4,5)` desugars to `op(b,4,5)` → `error[undefined-name]` (op is a field, not a fn) |
| **lambda stored / returned** | ❌ | `error[lambda-value]` (LAMBDA-2 safety net) — no first-class representation |
| **capturing lambda as a value** | ❌ | no env representation |

So three gaps remain: (1) calling a fn-valued **field/expression**, (2) **lambdas** as values
(lifting), (3) **captures** (env).

Key existing facts:
- `FnT` (a function type) already has a C spelling: `zfn` = `typedef void (*zfn)(void)` (an opaque
  fn-ptr), used by `gen_ty`/`ty_cname`. Trait method fields are `FnT` but traits are compile-time
  (skipped in codegen, dispatched via `impl_cname`), so trait `FnT` never reaches the backend.
- `fn_value_ty` (check.zen) already types a bare top-level fn name as its `FnT` signature, which is
  why `f := add` works.
- Lambdas have **untyped params** (`(n){…}`) — their types come from the expected `FnT` (the field
  type / param type / return type). So a lambda can only be lifted where its expected `FnT` is known.
- There is **no free-variable / capture analysis** anywhere yet — must be built for captures.

## The C representation (validated by docs PoC /tmp/closure_poc.c)

One uniform closure value per `FnT`, regardless of capture:

```c
typedef struct { void* fn; void* env; } zclos;   // {fn_ptr, env_ptr}
```

- **Call** (uniform ABI — the lifted fn always takes `env` as arg 0):
  `((Ret(*)(void*, Args))c.fn)(c.env, args)`  — the cast comes from the call site's known `FnT`.
- **Non-capturing** lambda / named fn → `env = NULL`; the lifted/wrapper fn ignores arg 0.
- **Capturing** lambda → `env` points to a heap struct of the captured free vars (allocator-supplied).

Why uniform `{fn,env}` (vs a bare fn-ptr for non-capturing): a field/return typed `FnT` must hold
EITHER kind, so the C type must be uniform. The cost is one indirection word (`env`) always present.

To make every fn-value obey the `(env, args)` ABI:
- a **lambda** lifts to a top-level `static Ret __lambda_N(void* env, Args) { … }` (env read for captures).
- a **named fn** used as a value gets a generated env-ignoring wrapper
  `static Ret __fnval_add(void* env, Args){ return add(args); }`, value = `(zclos){__fnval_add, NULL}`.

(Alternative considered: emit a precise `Ret(*)(Args)` fn-ptr type and skip env for non-capturing.
Rejected: C fn-ptr-in-struct syntax (`Ret(*op)(Args)`) is awkward for the current append-style
`gen_ty`, and it can't hold a capturing closure — breaks uniformity.)

## Changes required

**check.zen**
- *Lifting pass* (new): walk each function; for every `Lambda` in a VALUE position (NOT a direct
  HOF-arg / `.loop` — those stay inline), with its expected `FnT` known, emit a top-level `DFunc`
  `__lambda_N` (params typed from the FnT, `env` prepended) and replace the lambda expr with a
  closure-construction node. Must run where expected types are known (resolve, threading `env.exp`).
- *Calling a fn-valued field/expr*: `b.op(args)` desugars to `op(b,args)`; detect that `op` is an
  `FnT` field of `b`'s type (or that the callee is an `FnT`-typed local/expr) and emit an indirect
  closure call instead of a named call. Touches `dispatch_name`/`resolve_call`.
- Drop/relax the LAMBDA-2 `error[lambda-value]` for the now-supported value positions (keep it only
  for genuinely-unsupported residue, if any).

**genc.zen / genc_emit.zen**
- `FnT` `gen_ty`/`ty_cname` → `zclos` (struct) instead of `zfn`; add the `zclos` typedef to the TU head.
- Emit lifted lambda fns + named-fn wrappers (a new decl stream, like mono).
- Closure construction: `(zclos){ (void*)__lambda_N, env_expr }`.
- Closure call: `((Ret(*)(void*,Args))c.fn)(c.env, args)`.

**check_validate.zen**
- Type a closure value as its `FnT`; type a closure call against the `FnT`'s params/ret.

## Captures (M2) — the hard part

The brief version: for a capturing lambda we must (1) collect the free vars, (2) build an env struct,
(3) **allocate** the env — and the env, when the closure escapes, outlives the stack, so it must be
heap-allocated **and freed by someone** under Zen's "explicit alloc, no hidden heap" rule. That is a
real ownership/lifetime design, not a mechanical change. The full design is in
"[M2 — Capturing closures](#m2--capturing-closures-proposed-nothing-built)" at the end of this doc.

## Byte-exact risk

- Changing `FnT`'s C type (`zfn`→`zclos`) and the fn-value call path changes codegen for any existing
  true fn-VALUE. The compiler/stdlib use `FnT` heavily as **params** (HOFs/traits) but those are
  inline-spliced / compile-time, not values — so few/no true fn-values exist today (they didn't
  work). Expect little/no seed drift; the fixpoint is the gate. Inline-splice and `.loop` paths are
  untouched (zero-overhead path preserved).

## Milestones & recommendation

- **M1 — non-capturing first-class fn values** (env always NULL): fn-valued struct fields + calling
  them, named-fn values, non-capturing lambda values (lift). This already unblocks the motivating
  case: a `Store{ reducer: (S,A) S }` holding a top-level reducer fn, and callback tables. Tractable
  as one focused change. **Recommend doing M1 first, reporting, then designing M2.**
- **M2 — capturing closures**: free-var env + the allocation/lifetime model above. Bigger; its
  ownership story needs its own design pass before any code.

If M1's "call a fn-valued field" + uniform `zclos` proves to ripple too far in genc, fall back to a
narrower first step: support only **named** fns as field values (no lambda lifting) — that alone
unblocks `std.store` reducers — then add lambda lifting.

---

## M2 — Capturing closures (proposed; NOTHING built)

*Folded in from the former `closures-m2-design.md` (report-first; no code).*

Goal: a lambda that **captures** an enclosing local — `k := 10; … (n) { n + k }` — usable as a
first-class VALUE (stored in a field, returned, passed around), not only inline-spliced. Today such a
lambda in a value position falls to the clean `error[lambda-value]` (M1b/M1c). M2 makes it a value.

This is the hard one. The mechanics (an env struct) are easy; the **lifetime** of the env under
Zen's "explicit alloc, no hidden heap" rule is the real design decision. This section lays out the
options and recommends one; no code until greenlit.

### What already works (and why most captures need NOTHING new)

A capturing lambda passed **directly to a HOF** (`xs.fold(0, (acc, x) { acc + x + k })`) is
INLINE-SPLICED today: its body is pasted into the caller's frame, where `k` is a normal in-scope
local. Zero env, zero heap, zero overhead. `.loop` is the same. **This is the common case and it is
already correct.** So M2 is NOT "implement captures" broadly — it is specifically **escaping
capturing closures**: a capturing lambda that becomes a value outliving the frame that created it —
i.e. stored in a field that outlives, or returned. Those are exactly the M1b/M1c lift positions.

So the M2 scope is narrow but deep: the escaping capturing closure, where the captured values must
survive on the heap and someone must free them.

### 1. Env representation

Adopt the M0 uniform closure value (replacing M1's bare function pointer):

```c
typedef struct { void* fn; void* env; } zclos;   // every FnT value
```

- **free-var collection**: the M1b capture analysis (`lift_*_cap`, scope-threaded) already *detects*
  captures; M2 extends it to *collect* the free vars' names + types.
- **env struct**: synthesize one `StructDecl` per capturing lambda — `__env_N { k: i32, … }` — and
  populate it at the creation site from the current values of the free vars.
- **lifted fn**: `static Ret __lam_N(void* env, Args) { __env_N* e = env; … e->k … }` — reads captures
  from env; the uniform ABI passes env as arg 0.
- **closure value**: `(zclos){ (void*)__lam_N, env_ptr }`.
- **call**: `((Ret(*)(void*,Args))c.fn)(c.env, args)`.

Consequence — a **representation migration**: every FnT value (named fn, non-capturing lambda,
capturing lambda) must be a `zclos`, so the call ABI is uniform. Named fns and non-capturing lambdas
get `env = NULL` and a leading-ignored-`env` lifted fn (or a generated `__fnval_<name>` wrapper for a
named fn). This reworks M1's bare-fn-ptr field declarators / FnT-return typedefs into `zclos`. The
fast inline-splice / `.loop` paths are untouched (they never build a value).

### 2. The lifetime problem (the crux)

An escaping closure's `env` outlives the creating stack frame. Under "explicit alloc, no hidden heap",
**who allocates it and who frees it?** Options:

#### (a) Thread an allocator into closure creation
Creating a capturing closure needs an allocator in scope: `c := a.closure((n){ n + k })` →
`env = a.acquire(sizeof(__env_N))`. Freeing: the closure carries the env ptr; the holder frees it.
- **+** explicit, maximally Zen-idiomatic (allocators are threaded everywhere already).
- **−** viral: every escaping-capturing-lambda site needs an allocator param; and free still needs an
  ownership story (who calls free, and when).

#### (b) Tie env to an arena / Own
The env is allocated in an arena (or as an `Own<__env_N>`); lifetime = the arena's reset / the Own's
drop.
- **+** clean, deterministic lifetime; matches the existing std.mem arena/Own/Drop machinery (Goal Z).
- **−** the closure may not outlive its arena — a closure stored past the arena dangles; the closure
  type effectively borrows the arena's lifetime (which the type system doesn't track yet).

#### (c) Escape analysis: stack env for non-escaping, heap for escaping
Most capturing closures don't escape → env is a stack local struct (no heap, auto-freed). Only
escaping ones heap-allocate.
- **+** zero-cost for the common case (mirrors inline-splice's philosophy).
- **−** but non-escaping capturing lambdas are ALREADY inline-spliced (no value, no env) — so this
  buys little beyond what we have; the escaping case still needs (a)/(b) for its heap env+free.

#### (d) Hybrid (recommended)
- **Non-escaping** capturing lambdas → keep INLINE-SPLICE (already done; zero env/heap). No change.
- **Escaping** capturing closures → heap env via a **threaded allocator** (a), with the env lifetime
  managed by the **existing memory model** (b): in an arena, freed on arena reset (the natural,
  ergonomic usage); on `Heap`, the caller frees explicitly (or it leaks — explicitly, the user's
  choice, consistent with the rest of Zen). The closure value is a plain `zclos`; ownership of its env
  is the holder's, exactly like any other allocator-produced pointer.

Recommendation rationale: (d) keeps the zero-cost path we already have, confines heap+lifetime to the
genuinely-escaping case, and reuses Zen's allocator/arena/Own model rather than inventing a closure-
specific GC. A first cut can support **arena-scoped escaping closures only** (env = arena alloc, freed
with the arena) and reject `Heap`-allocated escaping closures that have no owner — tightening the
unsafe case to a clear error until Drop-integration lands.

### 3. Escape analysis

What "escapes" needs to be detected so only escaping closures pay the heap/alloc cost:
- a capturing lambda in a **field init** whose struct outlives the frame, or in a **return** /
  tail position → escapes (these are exactly the M1b/M1c lift positions);
- a capturing lambda **passed to a fn that stores it** → escapes (hard to see locally; conservative:
  treat any capturing lambda NOT in a direct-HOF-arg/`.loop` position as escaping);
- a capturing lambda as a **direct HOF arg / `.loop`** → does NOT escape (inline-spliced).

Practical proxy (no whole-program analysis): **lift position ⇒ escapes**. The capture analysis says
"captures"; the position says "escapes". A capturing lambda in a lift position is an escaping closure
(heap env); everywhere else it is inline-spliced or already rejected. This avoids a real escape
analysis for the first cut.

### 4. Changes + byte-exact risk

**check.zen**
- extend the capture walk to COLLECT free vars (name+type), not just detect.
- synthesize the `__env_N` struct decl + populate-expr; lift the body reading env fields; build the
  `zclos` value; thread the allocator to the creation site.
- escape proxy = lift position.

**genc.zen / genc_emit.zen**
- FnT value C-type → `zclos` (migrate from M1's bare fn-ptr field declarators + FnT-return typedefs).
- closure construction `(zclos){ … }`; closure call `c.fn(c.env, args)`; named-fn wrappers.

**check_validate.zen**
- type a `zclos` value/call; the capturing-lambda `error[lambda-value]` becomes "ok when an allocator
  is in scope / arena-scoped", else a clear diagnostic.

**Byte-exact risk: moderate.** The representation migration (bare fn-ptr → `zclos`) touches all of
M1/M1b/M1c's codegen, but the compiler itself uses few true fn-VALUES, so seed drift should be small;
the fixpoint is the gate. The inline-splice/`.loop`/alias fast paths are untouched.

### Phasing (suggested)

- **M2a — representation migration**: move FnT values from bare fn-ptr → uniform `zclos {fn, env=NULL}`
  (named fns + non-capturing lambdas), no captures yet. Validates the representation + call-ABI change
  in isolation, byte-exact. (If we decide the bare-fn-ptr M1 representation is fine to keep for
  non-capturing and only capturing closures use a different path, M2a can be skipped — but then a
  field typed FnT can't uniformly hold both, so a uniform zclos is cleaner.)
- **M2b — escaping capturing closures**: env synthesis + threaded-allocator alloc + arena lifetime;
  escape = lift position. Start arena-scoped only; reject owner-less Heap-escaping closures clearly.
- **M2c (later)** — Drop-integration so a closure stored in a struct frees its env on the struct's
  drop (removes the arena-only restriction); real escape analysis to stack-alloc more.

### Open questions for review (before greenlight)

1. Is the **arena-scoped-first** escaping-closure model acceptable as the first cut (Heap-escaping
   without an owner → clear error), or do we want Drop-integration (M2c) up front?
2. Do we migrate non-capturing FnT values to `zclos` (uniform, M2a) or keep M1's bare fn-ptr for them
   and only capturing closures carry env (needs a way for an FnT field to hold either — likely still
   uniform zclos)?
3. Acceptable that creating an escaping capturing closure **requires an allocator in scope** (viral on
   the signature), consistent with the rest of Zen's explicit-allocator model?
