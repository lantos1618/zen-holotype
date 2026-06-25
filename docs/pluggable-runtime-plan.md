# Build plan — the pluggable actor runtime (Pony×Zig)

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
