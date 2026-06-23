# Parallelism Goal (D): a multi-threaded work-stealing scheduler for Zen actors + coroutines

**Status:** design only (read-only task). No code changed.
**Author:** scheduler-design agent, 2026-06-23.
**Scope:** how to run the EXISTING `std.concurrent` actors + ucontext coroutines across N OS
threads, Pony/Tokio style, WITHOUT changing the actor API (`spawn`/`send`) or breaking the
colorless sync/async model.

---

## 0. Executive summary

Today everything in `std.concurrent` runs on **one OS thread**. `sched.run` is a cooperative
round-robin loop over `[Coro]`; actors are not scheduled at all — `handle.run()/drain()` drains a
mailbox **inline** on the caller's thread. The coroutine substrate keeps its swap state in three
**process-global** variables (`cur`/`back`/`flag` in `coroutine.zen`). The only atomic primitive
that exists is `atomic_add_i64` (SEQ_CST fetch-add); there is **no pthread FFI, no mutex, no CAS,
no thread-local storage** in the floor (`zenrt.c` is 40 lines, single-threaded).

The proposed design keeps the **sync path exactly as-is** (single-threaded, inline drain,
`checkpoint` = no-op) and adds a **third backing runtime, `Pool`**, that drives the same actors
across **M worker OS threads**. The runnable unit is an **actor** (Pony model: an actor with
pending messages is runnable); bare coroutines are the *suspension mechanism within an actor turn*,
not the scheduled unit. The hard invariant that makes it race-free: **an actor is runnable on at
most one worker, and runs on at most one thread, at any instant** — enforced by a single atomic
`scheduled` flag transition. Only the thread that flips `not-scheduled → scheduled` may push the
actor to a run queue; the worker that pops it owns it exclusively until it parks.

**Recommended first cut:** a single **mutex-guarded global run queue** + M worker pthreads +
**mutex-per-mailbox**. Simple, correct, genuinely parallel (user behaviors run on N cores), no CAS
needed. Then evolve to **per-worker local deques + work-stealing** (mutex-per-deque), then a
**lock-free Chase–Lev deque** (needs a CAS intrinsic). Each cut is a strict refinement; the actor
API never changes.

Two floor items are non-negotiable before *any* parallel cut:
1. **The coroutine globals `cur`/`back`/`flag` must become per-worker** (thread-local, or — cleaner
   and on-thesis — carried in the `Scope`/coro context). They collide the instant two workers
   `resume()` concurrently.
2. **A pthread FFI floor** (`pthread_create`/`join`/`mutex`/`cond`) + a couple more atomics
   (`atomic_load`/`store`, later `cas`). These are the deliverables of the thread-prim + atomics
   agents; this design names exactly what it consumes from them.

---

## 1. Current state — traced precisely

### 1.1 Coroutine substrate (`coroutine.zen`)
- Stackful fibers over glibc x86-64 `ucontext` (`getcontext`/`makecontext`/`swapcontext`,
  bodyless externs). A `Coro` is a `RawPtr` to a `CoroState { ctx, link, stack }`.
- **Three module-level globals**: `cur` (the running coro's ctx), `back` (where to swap on yield),
  `flag` (0 = finished this turn / 1 = yielded).
- `c.resume()`: sets `cur = state.ctx`, `back = state.link`, `flag = 0`, `swapcontext(link, ctx)`
  (jump INTO the coro), and on return reads `flag` (1 = still alive/yielded, 0 = ran to completion).
- `checkpoint_current()` (called from deep inside user code): if `cur` non-null, sets `flag = 1`
  and `swapcontext(cur, back)` — jump BACK to whoever resumed us.
- **These globals are the #1 multi-thread blocker.** Two workers calling `resume()`/`checkpoint`
  concurrently stomp each other's `cur`/`back`/`flag`. They are *implicitly* "the current thread's
  coroutine state" — so they must become per-thread.

### 1.2 Scheduler (`sched.zen`)
- `run<A>(alloc, coros: [Coro])` → `run_in` → `drive`. `drive` repeatedly does a `pass`: a
  recursive walk `tick`-ing each still-alive coro (`coros[i].resume()`), summing how many are still
  alive; loops until a full pass yields 0 live coros. An `alloc`-backed `flags` byte array tracks
  per-coro aliveness.
- **Pure cooperative round-robin on ONE thread.** No deque, no stealing, no actors. `try_run` is
  the same with `Result`-returning allocation.

### 1.3 Actors (`actor.zen`)
- `Mailbox` / `ActorState<M>`: a fixed-cap **ring buffer** in raw memory — `buf`, `head` (consumer),
  `tail` (producer), `cap`. `send` checks `tail - head >= cap` (full → refuse), else writes
  `buf[tail % cap]` and `tail += 1`. `recv`/`next_message` reads `buf[head % cap]`, `head += 1`.
  **All plain (non-atomic) i64 load/store — correct only for single-thread.**
- `spawn<A, M, ActorT>(alloc, cap, actor) → ActorHandle` (line 405): allocates a state block holding
  the actor value, plus an `ActorCell`/`ActorEngine`/`ActorSystem` carrying the mailbox ring. **No
  thread, no scheduler** — `spawn` just builds the data.
- The actor is **driven inline** by the caller: `handle.run()/flush()/drain()` loops the mailbox,
  calling `actor.receive(Context(msg))` then `runtime_checkpoint()` per message, until empty.
  `request`/`ask`/`query` = send-then-drain-then-await-reply, all synchronous on the caller thread.
- `ActorRef<M>`/`ActorHandle` **share the actor state via a raw pointer with no refcount** → today
  fine (single owner, single thread); a hazard the moment a sender on another thread can outlive the
  actor (§5, §7).

### 1.4 Runtime / colorless switch (`runtime.zen`)
- `Runtime` trait: `checkpoint(MutPtr<Self>) Signal`, `Signal: Go | Stop(CancelReason)`.
- `SyncArena.checkpoint = .Go` (no-op). `Heap.checkpoint = .Go`. `AsyncArena.checkpoint =
  checkpoint_current()  sig_go()` (yields the coroutine, returns `.Go`). `runtime_checkpoint() =
  checkpoint_current()`.
- The async path "yields to the scheduler" = swaps back to whoever `resume()`d this coro (i.e. the
  driver loop). Today that driver is `sched.run` on one thread. **The backing's checkpoint semantics
  do not need to change for multi-thread** — what changes is WHO resumes the coro (one thread vs M
  workers).

### 1.5 Scope capstone (`scope.zen`)
- `Scope<A>` wraps a backing `A` that is BOTH allocator AND runtime. `with_sync` opens a
  `Scope<SyncArena>` (no-op checkpoint), `with_async` opens a `Scope<AsyncArena>` (yielding
  checkpoint), freeing the arena on exit. The SAME generic body `(MutPtr<Scope<A>>) R` runs under
  either — the colorless capstone. `checkpoint` is cancellation-aware via a `budget` countdown
  (`.Stop(.Deadline)` when exhausted).

### 1.6 The floor (`zenrt.c`, `genc_emit.zen`)
- Only atomic: `atomic_add_i64(p, d)` → `__atomic_add_fetch((int64_t*)p, d, 5)` (SEQ_CST).
- `Arc<T>` (`std.mem.arc`) exists — atomic-refcounted — but is **unused** because no threads exist.
- **No pthread, no mutex, no CAS, no atomic load/store, no TLS** anywhere.

---

## 2. The model

### 2.1 Unit of work — an **actor** (Pony), coroutines are intra-turn suspension

**Decision: schedule actors, not coroutines.** An actor is *runnable* iff its mailbox has ≥1
pending message and it is not already scheduled/running. A worker pops a runnable actor, runs its
behavior over a **bounded batch** of messages (a *quantum* — e.g. up to K messages or until the
mailbox empties), then:
- if messages remain → **reschedule** (push back to a run queue), giving other actors a turn
  (fairness, no single-actor starvation);
- if empty → **deschedule** (clear the `scheduled` flag), and re-check pending to close the
  lost-wakeup window (§3.3).

**Why actors, not coroutines:**
- The mailbox already encodes "runnable" (`pending > 0`); the actor is the natural granule of
  message-passing concurrency and the unit Pony/Akka schedule.
- An actor turn is **run-to-completion per behavior** — no actor stack is parked mid-behavior — so
  an actor can freely **migrate between workers between turns** with no stack to move. That is what
  makes work-stealing of actors cheap and safe.

**Where coroutines fit:** the ucontext coro is the mechanism by which an actor *turn* suspends — e.g.
`await_reply` / `s.checkpoint()` inside a behavior yields the OS thread back to the worker loop so
the worker can run other actors while this one waits. So each actor that can suspend owns a coro
(its behavior runs inside it); `checkpoint_current()` swaps back to the worker. Bare `[Coro]`
scheduling (today's `sched.run`) becomes a thin special case: a coro with no mailbox is just a
"runnable once, reschedule while alive" task on the same deques. (First cut may keep `sched.run`
untouched and only pool actors; unify later.)

> Alternative considered: schedule raw `Coro`s and model an actor as "a coro that loops on its
> mailbox and checkpoints when empty." Cleaner reuse of `sched`, but it conflates *parked-on-empty*
> (deschedule) with *yielded-mid-turn* (reschedule) and makes the lost-wakeup race harder to reason
> about. Schedule actors; let the actor own its coro.

### 2.2 Workers + deques
- **M worker OS threads** (default M = online CPUs, overridable). Each worker owns a **local work
  deque** of runnable tasks. The owner pushes/pops its **own** end (LIFO — recently-made-runnable
  actors are hot in cache, Tokio/Pony style); thieves steal from the **other** end (FIFO — oldest,
  least likely to be the owner's next pop, minimizing contention).
- **Empty deque → steal**: a worker with an empty deque picks a **random victim** and steals a task
  from the victim's steal-end. Random victim selection avoids convoying. (Pseudo-randomness without
  `Math.random`: a per-worker xorshift seeded from the worker index — the floor forbids
  `Math.random()`/`Date.now()`, so seed deterministically from `worker_id`.)
- **All deques empty and all workers idle → quiescent** → workers park on a condvar / exit on
  shutdown (§4).

This is the standard work-stealing shape (Chase–Lev / Tokio multi-thread / Pony). The deque is the
only structure that needs careful concurrency; everything else composes around it.

---

## 3. Actor ↔ thread: placement, send, and the central race

### 3.1 Placement: **migratable**, not pinned
`spawn` places the new actor on the **spawning worker's local deque** (locality: producer and its
freshly-spawned children stay hot together). Thereafter the actor is **migratable** — any idle
worker may steal it. Recommendation: **migratable by default**, no hard affinity.
- Migration is safe because of run-to-completion: an actor never runs on two threads at once
  (§3.3), and between turns it has no live stack, so "which worker owns it next" is free to change.
- Optional soft affinity (a hint to prefer the last worker that ran it, for cache reuse) can be
  layered later; not needed for correctness.

(If `spawn` is called from a non-worker thread — e.g. the main thread before the pool starts — the
actor goes onto a shared/initial queue, or worker 0's deque.)

### 3.2 `send` from any thread — enqueue + mark-runnable, race-free
This is the hard part. `send` (called from ANY thread) must:
1. **Enqueue the message** into the target actor's mailbox (MPSC: many senders, one consumer = the
   worker currently running, or about to run, the actor).
2. **Mark the actor runnable** and, *iff it was not already scheduled*, **push it to a run deque**
   and **wake a sleeping worker**.

**Mutex-first cut (recommended):** guard each mailbox with its own mutex. `send` =
`lock(mb); push msg; was = scheduled; scheduled = true; unlock(mb); if !was { enqueue(actor); wake_one() }`.
Trivially correct MPSC; the only subtlety is the `scheduled` transition (§3.3). The push target is
the *global* queue (cut 1) or a chosen worker deque (cut 2).

**Lock-free cut (later):** the mailbox becomes a lock-free MPSC queue (Pony's intrusive linked list:
producers `atomic_exchange` the tail, consumer walks the list) and `scheduled` is an atomic flag
flipped with CAS. Needs `atomic_xchg` + `cas` intrinsics. Defer.

### 3.3 The mutual-exclusion invariant (why no actor-state lock is needed)
**Invariant: each actor is (a) present in at most one run queue and (b) executing on at most one
worker, at any time.** Enforced entirely by the `scheduled` flag:
- Only the thread that observes `scheduled: false → true` is allowed to push the actor to a queue.
  Concurrent senders all see `true` and just enqueue their message (no double-push).
- A worker that pops the actor holds it exclusively for the turn. On finishing a turn with the
  mailbox empty, it sets `scheduled: true → false`, then **re-reads `pending`**; if a message
  arrived in the gap (a sender saw `scheduled == true` and skipped the push, but the worker has
  since cleared it), the worker re-pushes itself. This re-check closes the **lost-wakeup** race —
  the canonical actor-runtime bug.

Because of this invariant, the actor's *own fields* need **no lock**: only one thread ever touches
them per turn. Only the **mailbox** (genuinely concurrent: producers on many threads, one consumer)
and the **run queue/deque** need synchronization. This is the key simplification that makes actor
schedulers tractable.

### 3.4 Lifetime of shared actor state — needs ARC
Today `ActorRef`/`ActorHandle` share the actor's state block via a **raw pointer, no refcount**.
Under threads, a sender on worker A may hold a ref to an actor whose owner (worker B) finishes and
frees it → **use-after-free**. Fix: back the shared actor state (state block + mailbox) with
`Arc<…>` (the `atomic_add_i64` floor already supports it). `send`/`ref` clone the Arc; the last
drop frees. This is the safe-lifetime story for cross-thread handles and is why `std.mem.arc`
exists. (First cut can sidestep by requiring all actors to outlive the pool — i.e. the body owns
them and frees after `pool.shutdown()` joins — but Arc is the real answer.)

---

## 4. Colorless integration — sync stays single-threaded, async/pool fans out

**Principle preserved: the backing allocator/runtime decides the execution mode; the body is
identical.** Three backings, all satisfying `Runtime` + `Allocator`:

| Backing      | `checkpoint`                | Driver                         | Threads |
|--------------|-----------------------------|--------------------------------|---------|
| `SyncArena`  | `.Go` (no-op)               | inline `handle.run()`/`drain`  | 1 (caller) |
| `AsyncArena` | `checkpoint_current()`+`.Go`| `sched.run([Coro])` cooperative| 1       |
| **`Pool`** (new) | `checkpoint_current()`+`.Go` | M-worker work-stealing pool | M       |

- **SYNC** is **unchanged**: `with_sync` → `Scope<SyncArena>`, checkpoint is a no-op, actors drain
  inline on the caller's thread. The pool is not involved. This is exactly today's behavior.
- **ASYNC (single-thread cooperative)** is unchanged: `with_async` → `Scope<AsyncArena>`.
- **POOL (new, the parallel path):** a new `with_pool(backing, cap, nworkers, body)` combinator
  opens M workers, runs the SAME `(MutPtr<Scope<A>>) R` body (where `A` is the pool-backed runtime),
  drains to quiescence, shuts the pool down, frees the arena. The body still only calls `s.acquire`
  / `s.checkpoint` / `spawn` / `send` — **no source change, no function coloring.**

**Does the capstone still hold?** Yes. The capstone is "one body compiles and runs sync AND async."
Pool is a *third* backing over the same surface; the body that runs under `SyncArena` and
`AsyncArena` also runs under `Pool`. The only semantic difference the body can observe is *whether
checkpoint yields* (it does under async/pool) — which is exactly the existing colorless contract.
`checkpoint`'s **return value** (`Signal`, with cancellation) is unchanged and is how a body
cooperates with shutdown/deadline under the pool too.

**One honest caveat.** The *inline* drivers (`handle.run()/drain/ask`) are the SYNC driver — they
drain on the calling thread. Under the pool the actor is driven by a worker, so a body that calls
`handle.run()` directly is a sync-driver call, not a pool operation. The colorless surface that the
pool fans out is **`spawn` + `send`** (build actors, post messages); the *draining* is the driver's
job (inline for sync, workers for pool). So: the **data + `spawn`/`send` API are colorless and
shared**; "drain inline" vs "drain on workers" is the backing-selected driver. This boundary is
clean and must be documented so users don't call `handle.run()` from inside a pool body expecting
parallelism.

---

## 5. Lifecycle

### 5.1 Startup
`pool_start(alloc, nworkers)`:
1. Allocate the pool struct: M worker slots (each: a deque + its lock, an xorshift seed = index),
   the global queue + lock + condvar (cut 1) or just the per-deque locks (cut 2), and an atomic
   `live_work` counter + a `stopping` flag.
2. **Spawn M − 1 pthreads** running `worker_loop(pool, id)`; the **calling (main) thread becomes
   worker 0** and also runs `worker_loop` (Pony runs the scheduler on all threads incl. the
   initiator — no idle main thread). Alternatively spawn all M and have main block on quiescence;
   recommend "main = worker 0" to use all cores.
3. Initialize **per-worker thread-local coroutine state** (`cur`/`back`/`flag`) — see §6.

### 5.2 The worker loop
```
worker_loop(pool, id):
  loop:
    task = pop_local(id)            // LIFO own end
        or steal_random(pool, id)   // FIFO victim's steal end
        or park_until_work_or_stop(pool)   // condvar wait; exit if stopping & globally idle
    if task is shutdown-sentinel: break
    still_runnable = run_quantum(task)      // resume coro; run up to K messages
    if still_runnable: push_local(id, task) // reschedule (fairness)
    // else: deschedule happened inside run_quantum via the scheduled-flag re-check (§3.3)
```
`run_quantum` for an actor = resume its coro; the coro drains up to K messages calling
`receive` + `checkpoint`; on empty-mailbox it does the `scheduled → false` + pending re-check and
either reschedules or parks (returns).

### 5.3 Quiescence + shutdown
- **Quiescence** = global `live_work == 0` AND every worker idle (all deques empty, none running a
  task). Track with an atomic `live_work` counter: `+1` when an actor transitions to scheduled,
  `−1` when it deschedules with an empty mailbox. When a worker that fails to find/steal work
  observes `live_work == 0`, the pool is quiescent.
- **Shutdown**: when `with_pool`'s body returns (or quiescence is reached and the body opted into
  "run until quiescent"), set `stopping = true`, **broadcast the condvar** so parked workers wake,
  see "no work + stopping", and exit their loop. Then `pthread_join` workers 1..M−1 (worker 0 = the
  returning main thread). Finally free actor state (Arc drops / arena free) and free the arena.
- **Drain semantics:** recommend **drain-to-quiescence** (finish all already-enqueued messages
  before exit) as the default — it matches structured-concurrency "the scope owns its work." An
  abrupt-cancel variant rides the existing `checkpoint → .Stop(.Deadline/.User)` Signal: set the
  scope's budget/cancel, and cooperating behaviors bail at their next checkpoint.

---

## 6. What is needed from the floor (atomics + thread prims + TLS)

This design **consumes** the following from the thread-prim + atomics agents. Listed exactly so the
work composes.

### 6.1 Already present
- `atomic_add_i64(p, d)` → `__atomic_add_fetch(.., 5)` SEQ_CST — used for `live_work`, Arc refcounts,
  and (lock-free cut) flag increments.
- `Arc<T>` (`std.mem.arc`) — for cross-thread actor-state lifetime (§3.4).

### 6.2 Required for the **mutex-first cut** (cut 1)
- **pthread FFI** (bodyless externs + link `-lpthread`):
  `pthread_create`, `pthread_join`, `pthread_mutex_init/lock/unlock/destroy`,
  `pthread_cond_init/wait/signal/broadcast/destroy`. Opaque sizes handled like the ucontext offsets
  (named constants now; `gen_opaque`/translate-c later — same pattern as `coroutine.zen`).
- **Thread-local coroutine state**: `cur`/`back`/`flag` must be **per-worker**. Two options:
  - (a) **TLS** — emit `__thread`/`_Thread_local` for those three globals (smallest change, needs a
    `@thread_local`-ish codegen path or a TLS intrinsic). Lowest blast radius.
  - (b) **Scope-carried context** — move `cur`/`back` into the coro/`Scope` and have `checkpoint`
    swap via the threaded `Scope` instead of a global. No TLS needed; on-thesis ("capabilities are
    passed, never ambient"); larger refactor of `coroutine.zen` + `runtime.zen`. **Preferred
    long-term**, but TLS (a) is the pragmatic first step.
- **`atomic_load_i64` / `atomic_store_i64`** (acquire/release) — for the `scheduled` flag and a
  clean memory model on `head`/`tail` even under a mutex (avoids relying on the mutex's fences for
  every field). Strictly, with a full mutex around the mailbox these can be plain, but having
  acquire/release loads makes the deque/flag paths correct and is cheap to add next to
  `atomic_add_i64`.

### 6.3 Required for the **lock-free cut** (cut 3)
- **`atomic_cas_i64`** (compare-exchange) → `__atomic_compare_exchange_n(.., SEQ_CST/ACQ_REL)` —
  the Chase–Lev deque's `steal`/`pop` bottom/top updates and the lock-free `scheduled` flip.
- **`atomic_xchg_i64`** → `__atomic_exchange_n` — for Pony's lock-free MPSC mailbox tail swap.
- A **release/acquire fence** intrinsic if we want to drop SEQ_CST for performance (optional).

### 6.4 Locks required (mutex-first cut)
- **1 mutex per mailbox** (MPSC correctness). Later removed by the lock-free MPSC queue.
- **1 mutex + 1 condvar for the global run queue** (cut 1). In cut 2 this becomes **1 mutex per
  worker deque** + a shared **condvar** (or per-worker condvars) for parking idle workers; in cut 3
  the deque mutexes vanish (Chase–Lev), leaving only the park/wake condvar.

---

## 7. Staged plan (refinements; actor API constant throughout)

**Cut 0 — floor (prereq, other agents):** pthread FFI + `atomic_load/store` + per-worker coroutine
state (TLS first). Nothing parallel yet; verify a single pthread can `resume` a coro with its own
`cur`/`back`/`flag`.

**Cut 1 — mutex-guarded GLOBAL run queue + M workers + mutex-per-mailbox. ← RECOMMENDED FIRST.**
- One global FIFO of runnable actors behind one mutex + condvar; M worker pthreads pop/park.
- `send` = lock mailbox, push, flip `scheduled`, push-to-global + signal if it was unscheduled.
- The `scheduled`-flag invariant (§3.3) + `live_work` quiescence (§5.3).
- **Genuinely parallel** (behaviors run on N cores), **correct**, **no CAS**, easy to reason about
  and test. Contended global lock is the known limitation — acceptable for v1. **Build this first.**

**Cut 2 — per-worker local deques + work-stealing (mutex-per-deque, FIFO steal).**
- Replace the global queue with M deques. `spawn`/reschedule push local (LIFO); idle workers steal
  random victim (FIFO). Park on a shared condvar when no work found and `live_work > 0`.
- Removes global-lock contention; still uses a short-held lock per deque op. Big scalability win for
  little extra complexity.

**Cut 3 — lock-free Chase–Lev deque + lock-free MPSC mailbox.**
- CAS-based deque (`atomic_cas_i64`), lock-free mailbox (`atomic_xchg`), lock-free `scheduled`.
- Maximal scalability; the hardest to get right (ABA, memory ordering). Do last, behind the same
  API, gated by a differential/stress test against cut-1 semantics.

Throughout: `spawn`/`send`/`receive` signatures are **untouched**; only the driver under them
changes. Each cut lands with a green byte-exact `--build-self` fixpoint + a stress test
(N producers × M workers, assert no lost/duplicated messages, no UAF under ASan/TSan).

---

## 8. Race hazards — honest list

1. **Coroutine globals (`cur`/`back`/`flag`) are process-global.** *The* blocker. Concurrent
   `resume`/`checkpoint` corrupt each other. Fix = per-worker (TLS or scope-carried) — cut 0.
2. **Lost wakeup on deschedule.** Worker clears `scheduled` while a sender, having seen
   `scheduled == true`, skips the push → message stuck, actor never re-runs. Fix = re-check
   `pending` after clearing the flag (§3.3); the flip + recheck must be correctly ordered
   (release on clear, acquire on the recheck).
3. **Mailbox MPSC data race.** Plain `head`/`tail` load/store races with concurrent producers. Fix =
   mutex-per-mailbox (cut 1) → lock-free MPSC (cut 3). Note the current ring is single-producer; for
   multi-producer the `tail` bump must be serialized (mutex) or atomic-xchg (lock-free).
4. **Use-after-free of shared actor state.** Sender on another thread outlives the actor's owner →
   UAF on the raw shared pointer. Fix = Arc-back the actor state (§3.4).
5. **Double-schedule.** Two senders both push the actor → it runs on two workers → state race. Fix =
   only the `false→true` flag winner pushes (§3.3).
6. **`send` to a full mailbox** currently returns `false` (drop). Under threads this is still a
   policy choice (drop vs block vs grow). Recommend: keep `false` (back-pressure signal) for cut 1;
   a blocking/growing variant later. Must not silently corrupt.
7. **Drop on migration.** An actor owning a `Drop`/`Own` value (cown.zen) migrates between workers;
   `drop` fires on whichever worker runs its final turn. Safe *as long as* single-owner holds (it
   does, §3.3), but `drop` bodies must not assume a fixed thread / thread-local resource. Document.
8. **`ask`/`await_reply` under the pool.** The inline `await` busy-drains on the caller; under the
   pool a blocking ask from a worker thread could deadlock if it waits on an actor that needs the
   same worker. Resolve by making cross-actor `ask` suspend (checkpoint) rather than inline-drain
   when running under the pool backing — i.e. `ReplyRef.await` checkpoints until `ready`. Flagged as
   a follow-up; cut 1 can restrict `ask` to the sync/async backings.

---

## 9. Open questions for lead + user

1. **Unit of work: actor vs coroutine.** This doc recommends **scheduling actors** (Pony) with
   coroutines as intra-turn suspension. Confirm — or do we want raw `Coro` as the scheduled unit
   (cleaner reuse of `sched.run`, muddier lost-wakeup story)?
2. **Affinity vs migration.** Recommend **migratable** (spawn-local placement + random steal, no
   pin). Any actors that must stay on one thread (e.g. owning a thread-bound C handle) would need an
   opt-in pin. Is pinning a needed feature or a future nicety?
3. **First cut: mutex-global-queue vs jump straight to local-deque stealing.** Recommend the
   **mutex-guarded global queue first** (correct, simple, parallel) then evolve. Acceptable, or do
   you want local deques in v1 even at higher complexity?
4. **Per-worker coroutine state: TLS vs Scope-carried.** TLS (`__thread`) is the smaller change;
   Scope-carried context is on-thesis ("no ambient capability") but a bigger `coroutine.zen`/
   `runtime.zen` refactor. Recommend **TLS first, Scope-carried later.** Agree?
5. **Pool as a third backing (`with_pool`) vs overloading `AsyncArena`.** Recommend a **distinct
   `Pool` backing/combinator** so single-thread cooperative async stays available and the capstone
   stays a clean 3-way. OK, or should "async" simply *mean* "pooled" once the pool lands?
6. **Shutdown policy.** Recommend **drain-to-quiescence** by default, with cooperative cancel via the
   existing `checkpoint → .Stop` Signal. Is abrupt cancellation also required for v1?
7. **Lifetime: require Arc for cross-thread handles, or restrict v1 to "body owns all actors,
   freed after join"?** Arc is the right answer but adds churn to the actor types; the restriction
   is simpler for cut 1. Which for v1?
