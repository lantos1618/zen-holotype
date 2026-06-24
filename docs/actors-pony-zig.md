# Concurrency model — Pony semantics, Zig-pluggable mechanisms, statically-safe sends

**Status:** canonical design. Supersedes the `checkpoint`/coroutine "colorless via `Runtime.suspend`"
thesis in `scope-runtime-goal.md` (§"What dies", below).
**One line:** *fix the semantics (Pony: actors, `send`, run-to-completion, no color); make every
mechanism a policy the user passes (Zig: mailbox / scheduler / allocator / collector); guarantee safe
sends statically (the move/escape/UAF checker), not with a GC or a capability lattice.*

---

## 1. Semantics — FIXED (Pony)

- **The actor is the unit of concurrency.** It has private state + **named behaviors**.
- A **behavior is asynchronous and runs to completion** — it never blocks, never awaits, never
  suspends mid-body. It mutates its own state, `send`s some messages, and returns.
- **`send` is fire-and-forget.** It enqueues a message on the target's mailbox and returns immediately.
- **Results come back as messages**, not as awaited returns. The "continuation" is the next behavior,
  triggered by the reply. There is **no `await`, no future-`get`, no `request`/`ask`-that-blocks**.
- **Parallelism = many actors × many OS threads** (a work-stealing scheduler). NOT yielding within a
  behavior.
- **No function coloring — by construction.** A behavior never depends on another actor's result
  mid-body, so there is no sync/async split to color. Coloring is *impossible*, not hidden.

### Behaviors are named (the Zig-clean upgrade over `receive` + enum)
Today: `Type.impl(actor.Receiver<Msg>, { receive = (self, ctx) { ctx.msg.match({...}) } })` with a
hand-written message enum. Target: behaviors are **methods**, and the message type is derived from them
at comptime.

```zen
Adder*: actor {
    sum: i64
    add    = (self, n: i64)   { self.sum = self.sum + n }       // async behavior, runs to completion
    report = (self, to: Sink) { to.send.total(self.sum) }       // "reply" is itself a send
}

// call site: `.send` is the async proxy; the call enqueues a message, returns immediately
add.send.add(10)
add.send.add(20)
add.send.report(sink)        // result will arrive at `sink` as a `.total(...)` message
```

`a.send.add(10)` desugars to `enqueue(a.mailbox, Msg.add(10))`; the `Msg` union is generated from the
actor's behaviors. Synchronous direct calls (`a.add(10)` with no `.send`) remain ordinary method calls
for the single-actor / testing case.

---

## 2. Mechanisms — PLUGGABLE (Zig). Four traits, defaults provided.

This is the `Allocator`-trait pattern, generalized. Each is a trait; the current concrete code becomes
the default impl; picking another is comptime-monomorphized (zero-cost) unless you ask for dynamic.

```zen
// memory — ALREADY a trait today (std.mem.alloc)
Allocator: { acquire: (MutPtr<Self>, i64) RawPtr<u8>,
             resize:  (MutPtr<Self>, RawPtr<u8>, i64) RawPtr<u8>,
             release: (MutPtr<Self>, RawPtr<u8>) void }

// mailbox — the message queue data structure (currently a hardcoded ring buffer in actor.zen)
Mailbox<M>: { push: (MutPtr<Self>, M) bool,      // false = full (back-pressure)
              pop:  (MutPtr<Self>) Opt<M>,
              len:  (Self) i64 }

// scheduler — how runnable actors map onto threads (currently the concrete pool)
Scheduler: { enqueue: (MutPtr<Self>, ActorId) void,   // make an actor runnable
             run:     (MutPtr<Self>) void,             // drive workers until quiescent
             workers: (Self) i64 }

// collector — per-actor reclamation strategy (unifies none / RC / ARC / ORC / manual)
Collector: { alloc:   (MutPtr<Self>, i64) RawPtr<u8>,
             retain:  (MutPtr<Self>, RawPtr<u8>) void,   // RC/ARC bump; no-op for arena/none
             release: (MutPtr<Self>, RawPtr<u8>) void,   // RC/ARC drop; no-op for arena (bulk free)
             collect: (MutPtr<Self>) void }              // ORC trace/sweep; no-op for RC/arena
```

### Default impls (the existing concrete code, demoted to defaults)
| Trait | Default | Other impls |
|---|---|---|
| `Allocator` | `Heap` (malloc-backed) | `Arena`, … |
| `Mailbox<M>` | `Ring(cap)` (today's ring buffer) | `Unbounded`, `Priority` |
| `Scheduler` | `WorkStealing(n)` (today's pool) | `Single`, `Fifo` |
| `Collector` | `Arena` (bump + bulk free) | `Rc`, `Arc`, `Orc` (tracing), `Manual`, `None` |

---

## 3. Assembly — the user composes the runtime

```zen
// clean common case — all defaults
sys := a.actor_system()                  // Ring mailbox · WorkStealing pool · per-actor Arena

// or choose every part, explicitly (Zig-style)
sys := a.actor_system(
    mailbox: mailbox.ring(256),          // ↔ mailbox.unbounded() / mailbox.priority()
    sched:   sched.work_stealing(8),     // ↔ sched.single() / sched.fifo()
    mem:     mem.arena(1 << 20),         // ↔ mem.rc / mem.orc / mem.manual
)

add := sys.spawn(Adder(sum: 0))          // spawn returns a handle
add.send.add(10)
sys.run()                                // drive to quiescence; behaviors run on N cores
```

### Per-actor policy override
Policy is per-actor, so one actor can differ without touching the rest — this is where RC/ARC/ORC live
(not a global `--mm:` flag):

```zen
graph := sys.spawn(SceneGraph(...), mem: mem.orc)    // cyclic data → tracing collector
ticker:= sys.spawn(Ticker(...),     mem: mem.arena)   // hot path → bump + bulk free, zero GC
shared:= sys.spawn(Registry(...),   mem: mem.arc)     // shared across actors → atomic RC
```

`mem.rc` / `mem.arc` / `mem.orc` are three `Collector` impls; `Rc`/`Arc` are already API-identical and
`Orc` = `Rc` + a color word + decrement registration (the deferred cycle collector, `std.mem.trace`).

---

## 4. Safe sends — statically, via the checker (not GC, not a cap lattice)

Pony makes zero-copy sends data-race-free with its reference-capability lattice (`iso`/`val`/`ref`/…).
The Zig-married answer reuses the **move/escape/UAF checker built in the safety work**:

- **Move-on-send.** A value passed to `send` is **moved**; using it afterward is **use-after-move** — a
  `zenc check` error (same machinery as use-after-free: the sent local is marked dead).
- **No aliasing actor-local state.** A message may not carry a pointer into the sender's actor-local
  region — that's an **escape** — a `zenc check` error (the addr-of-local escape pass).
- **Sendable data only.** A message is either a value (copied) or an owned `iso`-style block (moved).
  Borrowed pointers into another actor are rejected.

So data-race freedom is a *static property of the type checker*, independent of which `Mailbox`/
`Collector` is plugged in. **This is why the safety work this session is load-bearing** — it is the
substrate that makes message passing safe without a runtime barrier.

---

## 5. What dies (the `checkpoint`/coroutine removal)

`checkpoint` is a cooperative-yield point that only exists to support the ucontext coroutine substrate
and the old "one body runs sync or async via no-op-able yields" thesis. Run-to-completion behaviors on
real threads make it unnecessary, and message-passing makes the colorless property fall out for free.

| Remove ❌ | Keep ✅ |
|---|---|
| `Runtime.checkpoint` / `Signal`-as-suspension | the work-stealing pool (real pthreads) |
| ucontext coroutine substrate (`coroutine.zen`) | actor mailboxes (now behind `Mailbox`) |
| cooperative `sched.run` round-robin loop | atomics / `Mutex` / `CondVar` floor |
| `request`/`ask` (the hidden blocking wait) | typed messages + `send` |
| colorless-via-yield `Scope` mode (`with_async`) | the move/escape/UAF checker (now load-bearing) |

Cancellation (the one legit use of `checkpoint -> Signal`) becomes a **message**: send a `.cancel`
message; the actor handles it in a behavior. Deadlines become a timer actor that sends `.cancel`.

---

## 6. Real vs. to-build, and the build order

**Real today:** `Allocator` trait + `Heap`/`Arena`; `Rc`/`Arc`; the concrete work-stealing pool; the
concrete ring-buffer mailbox; typed `Receiver<Msg>` + `send`; atomics/`Mutex`/`CondVar`; the
move/escape/UAF checker.

**Build order:**
1. **Sendability rules** in the checker — move-on-send + no-actor-local-escape. (Extends this session's
   passes; makes sends safe before anything else changes.)
2. **`Mailbox<M>` trait** — extract the current ring buffer as `Ring`, the default impl. Add `Unbounded`.
3. **`Scheduler` trait** — extract the current pool as `WorkStealing`, the default. Add `Single`.
4. **`Collector` trait** — unify `none`/`Rc`/`Arc`; wire `Orc` (the color word + `trace.zen`).
5. **`actor_system(mailbox, sched, mem)` assembly** + per-actor `mem:` override.
6. **Named behaviors** — comptime-derive the `Msg` union from an `actor { … }` body; `a.send.beh(args)`.
7. **Remove** `checkpoint` / coroutines / cooperative `sched` / `request`-blocking; cancellation → message.

**Keystone dependency:** safe sends (1) gate the rest; capturing closures are *not* required (behaviors
are named methods, not closures), so this path sidesteps the closure blocker.

---

## 7. Why this is the end-state

- **One idea, applied everywhere:** the `Allocator` pattern (pass the mechanism explicitly) extended to
  mailbox, scheduler, collector. Nothing new to learn.
- **Pony's model, no GC tax you didn't ask for:** memory policy is per-actor and chosen; arena/RC/none
  cost nothing, ORC only where you opt in.
- **No coloring, no `await`, no `checkpoint`:** run-to-completion + messages.
- **Safe by construction:** the static checker guarantees race-free sends regardless of plugged policy.
