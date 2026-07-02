# North-star assessment (4 pillars) — 2026-07

## Overall verdict (4.5/10)

Zen has a real, load-bearing spine — genuine N-core parallel actors (measured ~7x speedup, exactly-once under 50x contention), four working pluggable allocators, and an AST-as-values codegen path that actually emits and runs C — which is far ahead of the "fake concurrency / aspirational metaprogramming" norm. But against a *first-class four-pillar north-star* it is held down by a recurring structural fault: **the ergonomic, typed, safe surface is not the one that actually delivers the pillar.** Typed actors don't schedule themselves (send only enqueues; you must manually `.run()`); the parallel path that does schedule is untyped raw-pointer/i64 plumbing. The "sound static UAF checker" is a name-only intraprocedural linter that a two-line alias or a free-in-a-loop walks straight past and crashes at runtime. Metaprogramming has no reflection of real types and no splice-back, so it's compiler-as-library, not integrated meta. Three of four pillars sit at 3.5–5 with *blocker*-severity gaps, and the split-brain typed-vs-parallel actor divide is the same wound in two pillars. Weighting blockers heavily, that's a 4.5: impressive engine, not yet a first-class delivery of the vision.

## Scoreboard

| Pillar | Score | One-line status | Biggest gap |
|---|---|---|---|
| Pony-style actors | 5/10 | Real parallel scheduler exists, but not Pony: one `receive`+enum, no named behaviors; typed API isn't autonomous | Typed `send` only enqueues — no scheduler backing (`grep pool actor.zen` = 0); autonomous path is type-erased |
| Async concurrency (N cores) | 6/10 | Genuinely multicore + race-free, but the *typed* API is single-threaded and the parallel one is raw i64 | Ergonomic API never touches the pool; queue is one global mutex (not the claimed work-stealing); overflow aborts; no channels/futures/select |
| First-class memory | 5/10 | Pluggable allocators are truly first-class; the "sound" UAF checker is an intraprocedural name-only linter | Aliasing (`q:=p; free(p); use(q)`) and free-in-loop pass `check` then crash; null-deref hole on exactly the `load_i64`/`RawPtr<u8>` that rc/arc use |
| Metaprogramming-as-values | 3.5/10 | AST→genModule→C runs end-to-end, but no reflection and no splice | No `comptime`/splice back into the current program; no `reflect(T)` — derive means retyping fields by hand; types aren't values |

## What to build next (ranked)

**Weakest pillar: metaprogramming (3.5).** **Highest-leverage single item: unify the typed actor onto the pool** — because it is a *blocker in two pillars at once* (actors + async) and the parallel engine already exists, so it's a wiring/monomorphization job, not a from-scratch build. That beats chasing the lowest score, per the "low-effort high-value" exception.

**The single most impactful next thing:** make `std.concurrent.actor.spawn` route through `std.concurrent.pool` — monomorphize a per-`(M, ActorT)` trampoline `(RawPtr<u8>, i64) void` that reconstitutes the typed message and calls `receive`, and back `ActorHandle.send` with `pool_send`. This makes typed `send` autonomous *and* gives typed actors real N-core parallelism in one move — collapsing the split-brain that costs both concurrency pillars.

Ranked milestones:

1. **Unify typed actor ⟶ pool (M1, highest leverage, moderate effort).** Kills the actors "send isn't autonomous" blocker and the async "typed API is single-threaded" major in one change. Add `ctx.send(peer, msg)` via a thread-local current-scheduler so actor-to-actor sends stop smuggling pointers through raw u8 state. Fixes actor-pillar's #1 and #3–4 gaps.
2. **Close the two UAF *blockers* (M2, cheap, high trust value).** (a) Alias set: when `q := p` binds a pointer-typed local, join q into p's alias-class and kill both on consume. (b) Add a `.Loop` case to `own_step`/`own_dead` so a free of an outer local inside a loop body flags. Also fold `load_i64`/`store_i64`/`atomic_*` and null-derived `RawPtr<u8>` into `derefs_nullable`. These are small, surgical, and remove the "silently crashes at runtime" footguns that most undermine the safety claim.
3. **Named behaviors (M3, medium).** Add a `be`/behavior declaration form that desugars `counter.inc(x)` into an async send of a synthesized message variant + `receive` dispatch. This is what makes actors *Pony* rather than Erlang-single-mailbox; do it after M1 so behaviors ride the unified scheduler.
4. **Comptime reflection + splice (M4, larger, the metaprogramming lever).** Introduce a `comptime` stage that (a) exposes `reflect(T) -> StructDecl` from the compiler's own type table and (b) splices a returned `[Decl]` back into the module before check/genc. This is the one change that turns metaprogramming from 3.5 toward first-class — `derive_eq(MyStruct)` on a *real* type in the *same* program.
5. **Scheduler hardening (M5, ongoing).** Grow the run-queue on overflow instead of aborting; either implement the promised per-worker deques (Cut 2) or drop the "work-stealing" wording; add a blocking `pool_send_blocking` and a pool-aware future/ReplyRef that parks on a CondVar. Lower priority — refinement, not pillar-defining.

## Risks / reality-checks

**Claimed-done that the probes show is actually broken:**
- **"Sound static UAF/double-free checker" is overclaimed.** It's intraprocedural + name-only. Three textbook cases pass `check` then crash: alias (`p:=acquire; q:=p; release(p); load_i64(q)` → `check` ok, run exit 71, reads freed block), free-in-loop (`[1,2,3].loop(_ => release(p))` → double-free abort), and interprocedural free-summary (`freeit(a,p); load_i64(p)` → ok). Treat the safety pillar's "verified" status as *straight-line only*.
- **Null-deref check has a hole exactly under its own smart pointers.** `derefs_nullable` covers `load`/`store`/`offset` but not `load_i64`/`store_i64`/`atomic_*`, and `RawPtr<u8>` is blanket-exempt — which is precisely what rc/arc/own and `malloc` use. `p:RawPtr<u8>:=null_ptr(); load(p)` → `check` ok, segfaults.
- **"Work-stealing scheduler" (pool.zen line 1) is not work-stealing.** It's a single global run-queue behind one mutex; per-worker deques are unbuilt. Will contend before 16 cores. Either build Cut 2 or fix the wording.
- **Run-queue overflow is a hard abort** (`Aborted (core dumped)`, exit 134) when concurrently-runnable actors exceed static `rqcap` — a latent crash, not backpressure.

**Cheap wins vs risky builds:**
- **Cheap, high-value:** M2 (alias + loop + intrinsic-null cases) — small edits to `own_step`/`derefs_nullable`, big trust payoff. Also just correcting the "work-stealing" and safety-soundness claims costs nothing and stops overselling.
- **Medium, highest-leverage:** M1 (typed-actor↦pool) — the engine exists; this is monomorphization + wiring, and it moves two pillars.
- **Risky/large:** M4 comptime+reflection is a genuine new compiler stage (type-table exposure + splice ordering vs check/genc); real value but real scope — sequence it last and don't underestimate it. M3 named-behaviors is a language-surface change (new declaration form + desugaring) — medium risk, do it on top of a unified scheduler so it doesn't fork the backends again.
- **Note (not a regression):** the metaprogramming probe confirms `sizeof(<concrete type>)` and generic `sizeof<T>` are **correct** now — the earlier "returns 0" memory is stale; don't spend effort re-fixing it.