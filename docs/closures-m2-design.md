# Capturing closures — M2 design (report-first; NOTHING built)

Goal: a lambda that **captures** an enclosing local — `k := 10; … (n) { n + k }` — usable as a
first-class VALUE (stored in a field, returned, passed around), not only inline-spliced. Today such a
lambda in a value position falls to the clean `error[lambda-value]` (M1b/M1c). M2 makes it a value.

This is the hard one. The mechanics (an env struct) are easy; the **lifetime** of the env under
Zen's "explicit alloc, no hidden heap" rule is the real design decision. This doc lays out the options
and recommends one; no code until greenlit.

## What already works (and why most captures need NOTHING new)

A capturing lambda passed **directly to a HOF** (`xs.fold(0, (acc, x) { acc + x + k })`) is
INLINE-SPLICED today: its body is pasted into the caller's frame, where `k` is a normal in-scope
local. Zero env, zero heap, zero overhead. `.loop` is the same. **This is the common case and it is
already correct.** So M2 is NOT "implement captures" broadly — it is specifically **escaping
capturing closures**: a capturing lambda that becomes a value outliving the frame that created it —
i.e. stored in a field that outlives, or returned. Those are exactly the M1b/M1c lift positions.

So the M2 scope is narrow but deep: the escaping capturing closure, where the captured values must
survive on the heap and someone must free them.

## 1. Env representation

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

## 2. The lifetime problem (the crux)

An escaping closure's `env` outlives the creating stack frame. Under "explicit alloc, no hidden heap",
**who allocates it and who frees it?** Options:

### (a) Thread an allocator into closure creation
Creating a capturing closure needs an allocator in scope: `c := a.closure((n){ n + k })` →
`env = a.acquire(sizeof(__env_N))`. Freeing: the closure carries the env ptr; the holder frees it.
- **+** explicit, maximally Zen-idiomatic (allocators are threaded everywhere already).
- **−** viral: every escaping-capturing-lambda site needs an allocator param; and free still needs an
  ownership story (who calls free, and when).

### (b) Tie env to an arena / Own
The env is allocated in an arena (or as an `Own<__env_N>`); lifetime = the arena's reset / the Own's
drop.
- **+** clean, deterministic lifetime; matches the existing std.mem arena/Own/Drop machinery (Goal Z).
- **−** the closure may not outlive its arena — a closure stored past the arena dangles; the closure
  type effectively borrows the arena's lifetime (which the type system doesn't track yet).

### (c) Escape analysis: stack env for non-escaping, heap for escaping
Most capturing closures don't escape → env is a stack local struct (no heap, auto-freed). Only
escaping ones heap-allocate.
- **+** zero-cost for the common case (mirrors inline-splice's philosophy).
- **−** but non-escaping capturing lambdas are ALREADY inline-spliced (no value, no env) — so this
  buys little beyond what we have; the escaping case still needs (a)/(b) for its heap env+free.

### (d) Hybrid (recommended)
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

## 3. Escape analysis

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

## 4. Changes + byte-exact risk

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

## Phasing (suggested)

- **M2a — representation migration**: move FnT values from bare fn-ptr → uniform `zclos {fn, env=NULL}`
  (named fns + non-capturing lambdas), no captures yet. Validates the representation + call-ABI change
  in isolation, byte-exact. (If we decide the bare-fn-ptr M1 representation is fine to keep for
  non-capturing and only capturing closures use a different path, M2a can be skipped — but then a
  field typed FnT can't uniformly hold both, so a uniform zclos is cleaner.)
- **M2b — escaping capturing closures**: env synthesis + threaded-allocator alloc + arena lifetime;
  escape = lift position. Start arena-scoped only; reject owner-less Heap-escaping closures clearly.
- **M2c (later)** — Drop-integration so a closure stored in a struct frees its env on the struct's
  drop (removes the arena-only restriction); real escape analysis to stack-alloc more.

## Open questions for review (before greenlight)

1. Is the **arena-scoped-first** escaping-closure model acceptable as the first cut (Heap-escaping
   without an owner → clear error), or do we want Drop-integration (M2c) up front?
2. Do we migrate non-capturing FnT values to `zclos` (uniform, M2a) or keep M1's bare fn-ptr for them
   and only capturing closures carry env (needs a way for an FnT field to hold either — likely still
   uniform zclos)?
3. Acceptable that creating an escaping capturing closure **requires an allocator in scope** (viral on
   the signature), consistent with the rest of Zen's explicit-allocator model?
