# Two-memory model — scratch vs shared

**Status:** DESIGN ONLY (2026-07). Concept is load-bearing; runtime verbs are **unbuilt**.
**Parent:** [runtime-design.md](runtime-design.md) § "Two memories".
**Ruling:** [history/three-things-ruling-2026-07.md](history/three-things-ruling-2026-07.md) item 5–6.

---

## BLUF

Zen splits process memory into two **regions** delivered as explicit capabilities, not ambient
thread-local state:

| Region | Lifetime | Crosses send? | Backing (planned) |
|---|---|---|---|
| **scratch** | One behavior / scope; bulk-freed | **Never** | bump/arena `Allocator` handed in |
| **shared** | Process/Arc lifetime | **Yes** (Arc-tracked) | `Arc<T>` / heap |

Default allocation is scratch. When scratch data would escape (return, send, actor state),
the checker rejects with a **one-token fix** naming a promotion verb.

---

## Promotion verbs (planned API)

Two blessed promotions — visible in source, grep-able:

```zen
v.share(alloc)   // freeze deep-immutable → Arc<T>  (Pony `val` path)
v.give(alloc)    // iso move → owned block; sender binding killed
```

- **`.share(rt)`** — value becomes deeply immutable and refcounted; aliases freely after freeze.
- **`.give(rt)`** — unique ownership moves into shared heap; sender cannot use `v` after (same
  machinery as `Own<T>` move-on-send).

These replace today's generic hint ("wrap in Arc (`new_in(alloc, v)`)") once the stdlib surface
lands. Until then, manual `new_in` / `Arc` construction is the honest workaround.

---

## Delivery model (explicit capabilities)

Rejected: ambient `rt.current()` scratch as thread-local default (see runtime-design reversal).

Accepted:

```zen
main = (sys: Sys) i32 {
    h := sys.heap()           // shared-capable process heap
    // scratch: a narrow Allocator passed into a scope/behavior — NOT ambient
    run_behavior(h, |scratch| {
        buf := scratch.acquire(64)
        // ...
    })
}
```

Actor state is constructed **inside** the actor at spawn (spawner scratch never seeds actor
fields). This kills cross-actor UAF by construction — the shipped `scratch-escape` pass enforces
the send/state embedding cases today.

---

## Checker teaching surface (shipped partial, verbs unbuilt)

The `scratch-escape` pass (`check_validate.zen`, kind `"scratch-escape"`) fires when
spawner-local scratch appears in:

1. A **send** payload (`KSCRATCHSEND`), or
2. **Initial actor state** embedded from spawner scratch.

Diagnostics name the subject and hint promotion. Target end-state hint shape:

```
error[scratch-escape]: `buf` is spawner-local scratch …
hint: promote with `.share(alloc)` or `.give(alloc)` — see docs/two-memory-design.md
```

Today's hints mention Arc/`new_in` as the interim spelling until `.share`/`.give` ship.

---

## Non-actor scratch (open design)

**Problem:** CLI / pure functions also need scratch; leak-by-default is unacceptable.

**Candidates** (decide before users invent five conventions):

| Approach | Pros | Cons |
|---|---|---|
| `rt.region((scratch) { ... })` | Explicit scope, grep-able | Ceremony at every block |
| Attenuated `self.scratch` in behaviors | Ergonomic nested spawn | Actor-only |
| Parameter threading only | Matches Sys model | Verbose in non-actor code |

**Decision:** deferred to a follow-up ergonomics doc; this file locks the **two-region semantics**
and **promotion verbs**, not the non-actor entry syntax.

---

## Library convention (to decide)

Functions needing shared memory should take `MutPtr<Heap>` or `DynAlloc` explicitly — never
assume ambient scratch. Functions needing only scratch take a narrow scratch `Allocator`.
Functions needing neither take neither (pure leaf).

---

## Ship list (ordered)

1. **[M] Prescriptive hints** — scratch-escape errors cite `.share`/`.give` + this doc (checker-only).
2. **[L] `.share` / `.give` stdlib** — freeze + iso promotion on supported types.
3. **[L] Scratch capability type** — explicit bump allocator, bulk-free at scope exit.
4. **[L] Non-actor `region` syntax** — pick one entry from the table above.
5. **[L] Retire ambient `std.rt` scratch** — only after explicit path covers corpus.

---

## Relationship to sendability

Sendability (`mode_of` lattice: `value` | `owned` | `frozen`) is **orthogonal** to region:

- `.share` produces `frozen` (Arc-backed) — sendable by copy.
- `.give` produces `owned` — sendable by move.
- Scratch-resident borrows are never sendable regardless of mode.

See [effects-as-types-design.md](effects-as-types-design.md) § sendability.
