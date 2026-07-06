# rt M3 — process-wide default runtime

**Status: SHIPPED (option a).** Implements docs/rt-scoped-runtime.md **§2b** ("`build.zen`
`exe.runtime(...)` sets the process-wide DEFAULT (M3)") — but see THE MURK: the literal
`exe.runtime → main(rt)` spelling cannot be built as-is, so this note establishes what "set the
default rt" realistically means, picks the smallest real surface, and records what shipped. The
phase-1 investigation that led here is preserved below.

## What shipped

- `zen/std/rt.zen`: process global `default_rt := heap_rt()` + guard `spawned := 0`;
  `default()` (accessor), `set_default(custom)` (writes global + main slot; **PANICS if called after
  the first spawn**), `mark_spawned()` (latched by the pool).
- Repointed the two hardcoded `heap_rt()` defaults to `default()`: `current()`'s unset fallback
  (rt.zen), `pool_spawn` (pool.zen), `spawn_actor_heap` (pool_actor.zen). `pool_spawn_rt` calls
  `mark_spawned()` (the single spawn choke point).
- Proofs: `tests/fixtures/zen/rt_m3_default_reaches_worker.zen` (exit 40 — the process default set via
  `set_default` reaches a POOL WORKER via `spawn_actor_heap`, which `with`/`enter` cannot do) +
  `rt_m3_set_default_after_spawn_panics.zen` (exit 134 + the teaching message; oracle_build.zen "build
  shell" suite). `default()==heap_rt()` when unset → every existing fixture byte-identical.
- Deferred exactly as recommended: build.zen `exe.runtime`, `Rt` sched/gc fields, `arena_rt`.

## The murk, confirmed against the tree

- **`build.zen` DOES exist** (`zen/std/build.zen`) and the driver runs it (`driver.zen:702
  build_zen_spec`) — but it is a **plain-data Target spec** (name/root/main/out/links, emitted as 5
  text lines the driver reads back). It carries no runtime value and no `exe.runtime(...)` setter.
- **`main` takes NO params** (#384 rejects parameterized main). The driver appends
  `main = () i32 { ... }` for the build program itself (`BUILD_TAIL`), and a user program's `main`
  is compiled straight to `zen_main`. So the spec's `main(rt)` is not expressible.
- **The foundation `Rt` is alloc-vtable ONLY** (`zen/std/rt.zen`: `mem_acquire/resize/release`,
  `state`, `ready`). **No sched/gc fields** — deferred per the foundation note.

So "exe.runtime → main(rt)" as literally spec'd is not buildable. Do NOT force it.

## What "set the default rt" realistically means here

The load-bearing gap the foundation left: **the process default is hardcoded `heap_rt()` in two
places, so a whole program cannot be run under a non-heap allocator** —

1. `current()`'s unset/zeroed-slot fallback returns `heap_rt()` (rt.zen:67).
2. The trivial spawn paths bake `heap_rt()` as the actor's `art` at spawn time
   (`pool.zen:108 pool_spawn`, `pool_actor.zen:74 spawn_actor_heap`), and the worker sets THAT as
   the ambient around each behavior (`pool.zen:239 enter(a.art)`).

Because of (2), even `rt.with(arena, ...)` at the top of `main` does **not** reach pool actors:
`with`/`enter` only rebind the CURRENT thread's slot, whereas each actor's rt is captured at spawn
from the hardcoded `heap_rt()`. **There is today no way to make a whole parallel program allocate
under an arena.** That is exactly the M3 win.

### Recommendation: option (a) — a program-side `rt.set_default(custom)` + repoint the two hardcodes

Add a **process-wide (non-thread-local) global** default, written once at the top of `main` before
any actor spawns, read-only after. Module-level non-TLS globals are already legal in the stdlib
(`internal/resolve.zen:478 ns_depth := 0`, `mem/trace.zen roots`), so this needs no compiler change.

```
default_rt := heap_rt()                 // process global; heap until a program opts in
set_default* = (custom: Rt) void { default_rt = custom; slot = custom }  // write global + main-thread slot
default*     = () Rt { default_rt }      // the configurable "trivial default" accessor
```

Then **repoint the two hardcodes to `default()`** (the ONLY behavioral change):
- `current()` fallback: `heap_rt()` → `default()`  (covers main thread + worker non-behavior allocs)
- `pool_spawn`'s default art + `spawn_actor_heap`: `heap_rt()` → `default()`  (so spawned actors
  inherit the process default; workers `enter` it → `rt.current()` inside `receive` sees it)

Safety: `set_default` runs on the main thread before `pool` spawns any worker; `pthread_create` is a
full barrier, so workers observe the written value with no race. Constraint (documented): call
`set_default` once, at the top of `main`, before spawning — it is startup configuration, not a
runtime knob. Per-actor override is unchanged: `spawn_actor(cap, actor, tramp, my_rt)` still pins a
specific rt regardless of the process default.

**Why (a) over (b)/(c):**
- **(b) build.zen `exe.runtime`** — would need the driver to inject a `set_default(...)` prologue
  around the user's `main` AND a fixed symbolic menu of policies in the data spec (arena|heap|...),
  since a runtime rt VALUE can't be a build-spec string. Real coupling, little extra power over (a).
  Defer until there's an actual policy menu worth naming declaratively.
- **(c) `--rt-sched=` CLI flag** — sched has no consumer yet (see below); a flag for a field that
  does nothing would be fake. Defer with sched.

(a) is the smallest thing that delivers "runtime configured once at the top, swappable without
touching source logic": one line at the top of `main`, and every ambient allocation + every
default-spawned actor across the whole program (including pool workers) honors it.

## Does the default need sched/gc yet? — No. Scope to alloc.

- **gc:** scratch never has gc; shared's rc/arc is already a per-alloc choice (`std.mem.arc`). No
  process-default gc field has a consumer. Defer.
- **sched (Inline vs Pool):** there is **no single runtime switch** for this today — Inline =
  `std.concurrent.actor` (inline drain), Pool = `std.concurrent.pool_actor` (workers); the choice is
  made by *which module you spawn through*, at the call site, not by an `rt.sched` field. Adding a
  sched field with no dispatcher reading it would be fake. Defer until a spawn path actually branches
  on it.

So M3's real, honest deliverable is **(i) the process default allocator is configurable** (arena vs
heap for a whole program, pool actors included). (ii) program-wide Inline-vs-Pool is **deferred** —
called out here so it isn't silently dropped, but not built.

## User-facing example (how a program chooses its runtime)

```zen
{ set_default, mem_rt } = std.rt
// ... build `arena` + its acquire/resize/release vtable ...
main = () i32 {
    set_default(mem_rt(arena_acq, arena_rsz, arena_rel, arena.raw()))  // configure ONCE, at the top
    h := pa.spawn_actor_heap(64, Worker(...), worker_tramp)            // inherits the arena default
    // ... sends ...; every ambient rt.alloc + this actor's receive now draws the arena, not heap.
    0
}
```

Existing programs that never call `set_default` are byte-identical: `default() == heap_rt()`.

## Proof plan (phase 2)

- **Distinguishing proof (the M3 win):** `set_default(counting_rt)`, then `spawn_actor_heap` a pool
  actor whose `receive` calls `rt.alloc`; assert the counter bumps — proves the process default
  reached a **pool worker thread** (which `with`/`enter` alone cannot do). Uses the foundation's
  counting_rt; no arena_rt needed.
- **Restore/default-unset regression:** a program with no `set_default` still allocates via heap;
  all existing pool + rt fixtures byte-identical.

## Defer list
- build.zen `exe.runtime(...)` declarative surface + driver prologue injection (option b).
- `Rt` sched/gc fields + program-wide Inline-vs-Pool + `--rt-sched` flag (option c).
- `arena_rt` (still the foundation's deferred `MutPtr<Arena>`↔`RawPtr<u8>` cast idiom).

## Phase-2 gotchas (from M4)
- Import as `{ set_default, ... } = std.rt` (brace-head), not `x = std.rt` alias-head (mis-resolves).
- Formatter can't do `mod.Type<T>(...)` explicit-arg qualified ctors — use the inferred form.
