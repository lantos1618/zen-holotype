# rt M4 — typed actors on the pool + per-actor ambient rt (implementation notes)

Implements docs/rt-scoped-runtime.md **§3** (typed actors routed through the pool scheduler,
healing the typed-vs-parallel split-brain) + the **§2b** M4 injection hook (per-actor rt set as
the ambient during a behavior). Foundation slice: docs/rt-foundation-notes.md.

## Phase 1 — the split, verified

### (a) How a typed send is processed TODAY (inline, on the caller thread)

`std.concurrent.actor`'s typed handles do NOT touch the pool. A send only enqueues:

- `ActorHandle<M, ActorT>.send(m)` (actor.zen:209) / `ActorRef<M>.send` / `ActorCell.send`
  push `m` into a `Ring<M>` mailbox held behind the actor's `RawPtr` state slot. **No scheduling.**
- Draining is **inline on the caller thread**: `ActorHandle.run` (actor.zen:217),
  `ActorSystem.run` (actor.zen:41), `ActorEngine.drain`, `ActorCell.drain` all loop
  `actor.receive(Context<M>(msg))` synchronously. `request`/`ask`/`await_reply` call `.run()`
  right after `send`. Fixture `rt_send_value_msg.zen` is the canonical shape:
  `h.send(.Say(Pk(s:41))); h.run(); got := h.actor().n`.

Meanwhile `std.concurrent.pool` runs **untyped** work in parallel: `pool_spawn(user, cap,
behavior)` where `behavior: (RawPtr<u8>, i64) void`, `pool_send` enqueues + schedules under the
mailbox/run-queue locks, and worker pthreads drain via `run_quantum → drain_batch →
a.behavior(a.user, msg)`. Genuinely N-core, but the message is a bare `i64` and the behavior is
type-erased. **That is the split-brain: typed API drains inline; parallel path is untyped.**

### (b) The trampoline shape — MUST be CONCRETE, not a generic function

Verified language constraint (mono.zen:143 "a generic fn is inlined; skip its T-params"):
**generic functions in Zen are INLINED at each call site — they have NO standalone C symbol, so
their address cannot be taken.** Probe: a generic `trampoline<T>` referenced as a
`(RawPtr<u8>, i64) void` value type-checks but codegen emits the bare unmangled name →
`'trampoline' undeclared` C error. So a *generic* trampoline is impossible.

A **concrete** (non-generic) adapter works perfectly as a fn-ptr (probe exit 41): it decodes the
raw payload and calls the concrete typed receiver:

```zen
// per (M, ActorT): a concrete (RawPtr<u8>, i64) void — the ONLY addressable shape.
room_tramp = (user: RawPtr<u8>, msg: i64) void {
    a: [Room] := user.slice(1)            // actor state = the pool user block
    b: [Msg]  := msg.offset(0).slice(1)   // msg (i64) is a POINTER to a heap-boxed M
    a[0].addr().receive(actor.Context<Msg>(msg: b[0]))   // typed trait dispatch
}
```

Payload boxing: the typed message `M` must outlive the send (a worker consumes it later), so the
generic (inlined) `send` heap-BOXES it — a `[M]` block — and rides the box pointer as the i64 msg
(`to_i64(box)` emits `((int64_t)(box))`; the trampoline recovers it with `msg.offset(0).slice(1)`).
The trampoline frees the box after `receive`.

**Consequence / the honest design:** because the reconstitution step (`sizeof(M)` box decode +
`Context<M>` construction + the trait `receive` resolution) is irreducibly type-specific and must
live in an *addressable* (= concrete) function, the per-(M,ActorT) trampoline is the ONE piece that
cannot be a stdlib generic. Everything else — boxing, pool registration, `send`, the rt wiring — is
stdlib generic (inlined). Plan: stdlib ships `std.concurrent.pool_actor` with generic
`spawn`/`send`/`free` over a `PooledHandle<M, ActorT>`; the small concrete trampoline is passed in
(one short stub per actor type, exactly matching the existing pool surface where users already
write a concrete `behave`). No compiler change, bootstrap untouched.

### (c) rt slot write/restore around receive

Add to `rt.zen` an explicit **save-set-restore** pair (no closure — the pool calls the behavior
through a raw fn-ptr in a hot loop, so `rt.with`'s niladic-callback form doesn't fit):

```zen
enter* = (custom: Rt) Rt { saved := slot; slot = custom; saved }   // set ambient, return prior
leave* = (saved: Rt) void { slot = saved }                          // restore prior
```

`PoolActor` gains an `rt: Rt` field. `run_quantum`/`drain_batch` (and `pool_drain_inline`) wrap the
behavior call: `saved := rt.enter(a.rt); a.behavior(a.user, msg); rt.leave(saved)`. So
`rt.current()` inside a behavior resolves to the actor's own rt (Pony per-actor heap). The `ready==0`
zeroed-worker fallback already makes an unset worker safe, so this is a pure write.

Surface: add `pool_spawn_rt(user, cap, behavior, rt)`; keep `pool_spawn(user, cap, behavior) =
pool_spawn_rt(user, cap, behavior, heap_rt())` so **every existing pool fixture stays
byte-identical** (untyped actors default to `heap_rt()`; setting the slot to the heap default is
observationally a no-op).

For this slice all actors may default to `heap_rt()`; the PROOF that the slot is per-actor uses an
actor spawned with a **counting rt** whose behavior calls `rt.alloc` — the counter bump proves the
worker set the slot to that actor's rt before `receive`.

## Proof plan
- **Parallel + exactly-once:** a fixture spawns N typed actors, blasts typed sends through the pool;
  each `receive` atomically bumps a shared counter; assert total exact + `workers_busy >= 2` (reuse
  the `pool_parallel_actors` / `pool_stress_exactly_once` machinery). Run 10×.
- **Ambient rt:** an actor spawned with a counting rt; its behavior's `rt.alloc` drives that actor's
  counter, proving `rt.current()` == the actor's rt on the worker thread.
- **Regression:** `pool_parallel_actors`, `rt_send_value_msg`, the #367/#399 cases run with identical
  observable results (additive change; inline typed path untouched).
