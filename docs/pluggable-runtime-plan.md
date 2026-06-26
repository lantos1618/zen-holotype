# Build plan — the pluggable actor runtime (Pony×Zig)

> **Companion docs:** the design/spec this plan executes is [`actors-pony-zig.md`](actors-pony-zig.md);
> the multi-threaded work-stealing scheduler that backs `Scheduler`/`WorkStealing` is detailed in
> "[Future work: work-stealing scheduler](#future-work-work-stealing-scheduler-multi-threaded)" below
> (full design archived at [`archive/parallel-scheduler-design.md`](archive/parallel-scheduler-design.md)).

Goal: deliver `docs/actors-pony-zig.md` — a runtime the user assembles from policies (Mailbox /
Scheduler / Collector), Pony semantics, safe sends. **Binding acceptance constraint: ERGONOMICS.**
The user-facing surface (`actor`, `send`, `receive`, the chat demo) must get *cleaner*, never clunkier;
the existing actor fixtures + `actor_demo.zen` must keep compiling and running unchanged at every step.
Each increment: `make oracle` green + fixpoint byte-exact + adversarial.

## Current state (traced)
- `actor.zen`: a low-level i64 `Mailbox` (ring: buf/head/tail/cap, send/recv/pending) AND a generic
  `ActorState<M>` whose ring ops are **open-coded** in `ActorRef.send` and `ActorSystem.next_message`.
  Typed `Receiver<M>`, `Context<M>`, `ReplyRef<T>`, `ActorCell`/`ActorEngine`/`ActorHandle`.
- `pool.zen`: concrete work-stealing pool + raw `pool_*` free functions (audit: should be `Pool` methods;
  `pool_actor_ref/unref` → `retain/release`; verb sprawl `post/flush/query/perform/destroy`).
- `runtime.zen`: `Runtime` trait (`checkpoint -> Signal`), `Sync/AsyncArena`. **`checkpoint` to be removed.**
- Sendability checker rules (move-on-send, Rc-not-sendable, no-local-ptr-in-msg) — DONE.

## Increments (ordered: low-risk → high; each oracle-gated)

1. **`Mailbox<M>` trait + `Ring<M>` default impl.** Define `Mailbox<M>: { push(self,M) bool, pop(self) M,
   len(self) i64 }`. Make the existing ring a `Ring<M>` impl. Rewire `ActorState`/`ActorRef`/`ActorSystem`
   to go through the trait. ERGONOMICS: internal plumbing only — no user-facing change. Then `Unbounded<M>`
   as a second impl proves pluggability.
   - **GOTCHA (attempt 1, reverted):** extracting the open-coded ring into generic METHODS on `ActorState<M>`
     (`push`/`pop` mutating `s.tail`/`s.head` via `MutPtr<ActorState<M>>`) passed `actor_demo` + the pool, but
     BROKE the `ActorCell.request` path (oracle: build-result-paths #5, modules-value #23 — `out` came back
     wrong). `actor_demo` uses `ActorHandle`; the failing cases use `ActorCell` — a DIFFERENT monomorphization
     path for the generic mailbox methods. Suspect: generic-method-on-`<M>` interacting with the OOB-guarded
     `[M]` index or in-place field-mutation vs whole-struct-replace under that instantiation.
   - **ROOT CAUSE (diagnosed):** a generic-pointer-receiver arrow field-access feeding `.slice()` —
     `b: MutPtr<Box<M>> { … b.buf.slice(b.cap) … }` — emits BAD C ("invalid use of void expression").
     Confirmed with a minimal repro; it is NOT slice-element inference (direct `ms: [M] := buf.slice(n)`
     in a flat scope works fine — prints 111/222). The OLD actor ring AVOIDS this: state lives behind a
     `RawPtr`; methods take a **value** receiver, grab a `[ActorState<M>]` slice view, load `cur := state[0]`
     (a VALUE), and slice `cur.buf` (DOT, not arrow), writing back `state[0] = ActorState(…)`. My refactor
     broke it by introducing `MutPtr<ActorState<M>>` arrow access in push/pop.
   - **RETRY RULE:** keep the RawPtr-backed slice-view + value-load idiom (no generic `MutPtr<Struct<M>>`
     arrow → `.slice()`); OR first fix that codegen path in genc. Verify the `ActorCell` path explicitly
     (not just `actor_demo`) at each step.
   - **EXACT ROOT CAUSE (fully traced):** `inline_template` (check.zen:1677) inlines a generic fn body
     substituting only VALUE params (`tf.params`→`cargs`) — it never computes the type-arg binding
     (`M`→`i64`). So `xform_expr` (check.zen:1752) rebuilds `Index` passing `ix.elem` RAW, and `.Loop`
     passes `l.elemTy` raw, `.SliceLit` passes `sd.elem` raw, and a `ms: [M] :=` let keeps `[M]`. genc
     then emits `*(void*)zen__idx(ms,i,sizeof(void))` (M erased → void) = "invalid use of void expression".
     The ACTOR path works only because its element type flows through a MONOMORPHIZED struct
     (`ActorState_Msg`, a concrete `dstruct` from mono.zen) rather than a raw `[M]` local in an inlined body.
     **THE FIX:** `inline_template` must compute the tparam→arg map (from the generic fn's `tparams` and the
     concrete arg/receiver types) and thread it through `xform_*`, applying `subst_ty_in` to `ix.elem`,
     `l.elemTy`, `sd.elem`, and `[M]` let-annotations. Real inliner change — do it fresh, oracle-gated,
     with /tmp/m.zen (Box<M>.at) as the adversarial test. NOT attempted (deferred, not a tail-end rush).
2. **Canonical verb set (ergonomics cleanup).** Remove the actor synonym sprawl (`post`≡`send`,
   `flush`≡`run`, `query`≡`request`, `perform`≡`ask`, `destroy`≡`free`) — keep ONE verb each. Update call
   sites. This is the "settle the verbs" the design calls for; do it now so later steps don't churn names.
3. **`Scheduler` trait.** Extract the pool as `WorkStealing` (default); add `Single` (inline). `pool_*`
   free fns → `Pool` methods (audit finding). `actor_system` picks the scheduler.
4. **`Collector` trait.** Unify none/Rc/Arc; wire `Orc` (color word + `trace.zen`). Per-actor `mem:` policy.
5. **`actor_system(mailbox, sched, mem)` assembly** + per-actor override. The headline ergonomic API.
6. **Named behaviors.** comptime-derive the `Msg` union from an `actor { … }` body; `a.send.beh(args)`.
   The big ergonomic upgrade over `receive` + hand-written enum.
7. **Remove `checkpoint`/coroutines/cooperative sched/`request`-blocking.** Cancellation → `.cancel` message.

## Ergonomics guardrails (checked every increment)
- `actor_demo.zen` + every `tests/fixtures/zen/{actor,pool,*}` builds & runs unchanged.
- No new annotations forced on user code; defaults make the common case one line.
- The trait plumbing stays *under* the surface — users see `actor`/`send`/`receive`, not Mailbox/Ring.

---

## Future work: work-stealing scheduler (multi-threaded)

*Folded in from the former `parallel-scheduler-design.md` (design-only, 2026-06-23). The full
detailed design — current-state trace, complete race-hazard list, and open questions — is archived at
[`archive/parallel-scheduler-design.md`](archive/parallel-scheduler-design.md). This section is the
working summary that belongs with the `Scheduler` trait (increment 3 of the plan above).*

**Status update:** the first cut of this scheduler has since SHIPPED — Zen actors run on N OS cores via
`std.concurrent.pool` (real pthreads + atomics + thread-local coroutine state + `std.sync`
Mutex/CondVar + Arc-backed actor lifetime; race-free under stress). What remains future work here is
the *evolution* (Cut 2 per-worker deques, Cut 3 lock-free) and the channels refinement.

### Model
- **Unit of work = an actor** (Pony): runnable iff its mailbox has ≥1 pending message and it is not
  already scheduled/running. A worker pops a runnable actor, runs its behavior over a bounded batch
  (a *quantum*), then reschedules (messages remain) or deschedules (mailbox empty). Coroutines are the
  *intra-turn suspension* mechanism, NOT the scheduled unit — an actor turn is run-to-completion, so an
  actor can migrate between workers between turns (no live stack), which is what makes work-stealing
  cheap and safe.
- **M worker OS threads**, each owning a local deque: push/pop own end (LIFO, cache-hot), thieves steal
  the other end (FIFO). Empty deque → steal from a random victim (xorshift seeded from worker id; the
  floor forbids `Math.random`/`Date.now`). All deques empty + all idle → quiescent → park on condvar.

### The central invariant (why no actor-state lock is needed)
**Each actor is present in at most one run queue AND executing on at most one worker at any time** —
enforced entirely by an atomic `scheduled` flag. Only the thread that observes `scheduled: false→true`
pushes the actor to a queue; concurrent senders just enqueue their message. A worker finishing a turn
with an empty mailbox sets `scheduled: true→false` then **re-reads `pending`** to close the lost-wakeup
race. Because of this, the actor's own fields need no lock — only the **mailbox** (MPSC) and the
**run queue/deque** need synchronization.

### `send` from any thread (race-free)
1. Enqueue the message into the target mailbox (MPSC). 2. Mark runnable and, *iff it was not already
scheduled*, push it to a run deque and wake a sleeping worker. Mutex-first cut:
`lock(mb); push; was=scheduled; scheduled=true; unlock(mb); if !was { enqueue(actor); wake_one() }`.

### Lifetime — needs ARC
A sender on worker A may outlive the actor's owner (worker B) that frees it → UAF on the raw shared
pointer. Fix: back shared actor state with `Arc<…>`; `send`/`ref` clone the Arc, last drop frees. (This
is why `std.mem.arc` exists, and is the shipped answer.)

### Colorless integration — sync stays single-threaded, the pool fans out
Three backings, all satisfying `Runtime` + `Allocator`; the body is identical:

| Backing      | `checkpoint`                | Driver                          | Threads     |
|--------------|-----------------------------|---------------------------------|-------------|
| `SyncArena`  | `.Go` (no-op)               | inline `handle.run()`/`drain`   | 1 (caller)  |
| `AsyncArena` | `checkpoint_current()`+`.Go`| `sched.run([Coro])` cooperative | 1           |
| **`Pool`**   | `checkpoint_current()`+`.Go`| M-worker work-stealing pool     | M           |

The capstone ("one body compiles and runs sync AND async") holds: Pool is a third backing over the same
`spawn` + `send` surface. One honest caveat: the inline drivers (`handle.run()/drain/ask`) are the SYNC
driver; the colorless surface the pool fans out is `spawn` + `send` (draining is the backing-selected
driver — inline for sync, workers for pool). Users must not call `handle.run()` from inside a pool body
expecting parallelism.

### What the floor must provide
- Already present: `atomic_add_i64` (SEQ_CST), `Arc<T>`.
- Mutex-first cut: pthread FFI (`pthread_create`/`join`/`mutex_*`/`cond_*`, link `-lpthread`);
  **per-worker coroutine state** (`cur`/`back`/`flag` must be thread-local — TLS first, scope-carried
  later); `atomic_load`/`store` (acquire/release).
- Lock-free cut: `atomic_cas_i64` (Chase–Lev deque + lock-free `scheduled`), `atomic_xchg_i64`
  (Pony lock-free MPSC mailbox tail swap), optional fence intrinsic.

### Staged plan (refinements; actor API constant throughout)
- **Cut 0 — floor (prereq):** pthread FFI + `atomic_load/store` + per-worker coroutine state. *(shipped)*
- **Cut 1 — mutex-guarded GLOBAL run queue + M workers + mutex-per-mailbox.** Genuinely parallel,
  correct, no CAS; contended global lock is the known v1 limitation. *(shipped — #289-293)*
- **Cut 2 — per-worker local deques + work-stealing** (mutex-per-deque, FIFO steal). Removes global-lock
  contention. *(future)*
- **Cut 3 — lock-free Chase–Lev deque + lock-free MPSC mailbox** (CAS/xchg). Maximal scalability,
  hardest to get right (ABA, ordering). *(future)*

Throughout: `spawn`/`send`/`receive` signatures are untouched; only the driver under them changes. Each
cut lands with a green byte-exact `--build-self` fixpoint + a producer×worker stress test (no
lost/duplicated messages, no UAF under ASan/TSan).
