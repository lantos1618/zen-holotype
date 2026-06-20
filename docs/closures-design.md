# First-class function values (closures) — design (M0)

Goal: make a lambda / function a real VALUE — storable in a struct field, returnable from a
function, passable and called dynamically — not only inline-spliced. Unblocks callbacks,
`std.store` reducers, event handlers, fn tables.

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

## Captures (M2) — the hard part, separate design round

For a capturing lambda we must:
1. **free-var analysis**: collect names used in the body that aren't params/globals/top-level fns.
2. build an **env struct** of those vars (by value), populate it at creation.
3. **allocate** the env — and here is the open question: Zen's model is *explicit allocation, no
   hidden heap*. A closure that escapes its creating frame outlives the stack, so the env must be
   heap-allocated **and freed by someone**. Options:
   - require an allocator in scope at lambda creation (thread it in, like the rest of std);
   - tie the env lifetime to an `Own`/arena (closure owns its env, dropped with it);
   - stack-allocate the env when the closure provably does NOT escape (non-escaping analysis) and
     only heap-allocate escaping ones.
   This is a real ownership/lifetime design, not a mechanical change — **needs its own M0**.

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
