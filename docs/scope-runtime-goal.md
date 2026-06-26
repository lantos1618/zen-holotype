# GOAL — Scope / Runtime / Capability surface (colorless, no-keyword)

> **Note (status):** the *concurrency* half of this thesis — colorless sync/async via a
> `Runtime.checkpoint` cooperative-yield — is **superseded** by the Pony×Zig actor model in
> [`actors-pony-zig.md`](actors-pony-zig.md) (run-to-completion behaviors on real threads; `checkpoint`
> removed). What survives and is still current here: **memory-as-stdlib**, the `Scope` capability-
> threading surface, explicit allocators, and the escape/lifetime checker. Kept as the milestone/status
> record (it also absorbs the former `ideal-scope-concurrency.md` surface spec, below).

North star: **a capability is a receiver you must name; your signature is your effect row.**
One value — `Scope` — carries every capability a function needs, threaded explicitly:

    Scope = Allocator (memory)  +  Runtime (sync/async mode)  +  Deadline (cancellation)  +  cleanup ledger (lifetime)

A function that takes a `Scope` announces it may allocate / suspend / clean up; a pure leaf
takes none and provably cannot. Control flow stays on receivers: branch = `.match`,
iterate = `.loop`, propagate = `.or_return()`, cleanup = `s.onExit(...)`, suspend = `s.checkpoint()`.
No prefix keywords (no `async`/`await`/`defer`/`try`). Capabilities are passed, never ambient.

## The category (validated by two founder panels)
Two orthogonal axes plus data — NOT three:
- **Memory ⊇ Lifetime** — where bytes live + when/order they die. Carried by `Scope` (alloc + cleanup ledger).
- **Concurrency ⊇ Cancellation** — whether `checkpoint` yields + whether it must stop. Carried by `Scope` (backing Runtime + deadline).
- **Errors** — plain `Result` values, deliberately OFF the receiver so they can't perturb cleanup. Not an axis.
The unanimous *missing* piece was cancellation: `checkpoint` must return a value, not `void`.

## Design rules baked in
- Methods travel with their type: define `onExit`/`drain`/`child`/`checkpoint`/`acquire` INSIDE `Scope: {…}`,
  and `with` inside `SyncArena`/`AsyncArena` (the arena makes the scope). Importing the type brings the methods;
  stop importing loose functions. (Mirrors how `SyncArena` already defines `free_in`/`free` in-body.)
- Generics are introduced by USE: a free capital in a param/field type (`a: MutPtr<A>`) is the type param.
  The `<A>` declaration list becomes optional, then unnecessary. Type *application* (`Scope<A>`, `Vec<Job>`) keeps brackets.
- Cleanup attaches to a scope and is drained by the OWNER combinator (`with`), structurally above every exit,
  so an early `.Err` return cannot skip it. `.or_return()` desugars to a guard-match (no `?` keyword).

## Milestones (ordered by risk × value; green byte-exact fixpoint after each)
- **M0 — de-slop the raw-C floor.** Funnel scattered bodyless libc decls (malloc/free/realloc in raw.zen+alloc.zen,
  open/read/write/close in io/file.zen, write/strlen/abort in result.zen, strlen in str.zen) into ONE `std.c.libc`;
  everyone imports it. malloc lives in one file. Low risk; pure consolidation.
- **M1 — `checkpoint -> Signal`.** Add `Signal: Go | Stop(CancelReason)` + `CancelReason: Deadline | Parent | User`;
  change `Runtime.checkpoint` trait + 3 impls (Sync/Heap = `.Go`, Async = `checkpoint_current()  sig_go()`).
  No live consumers today → low blast radius. The spine. [DONE]
- **M2 — implicit type params.** `resolve.zen`/`parse.zen` collect-free-tyvars pass: a short all-caps type-position name
  that is unbound binds as an implicit param BEFORE undefined-name fires. Makes `<A>` optional (don't rewrite 334 sites). [DONE a4a75a4]
- **M3 — `std.scope`.** `Scope` struct + in-body methods (`acquire`/`onExit`/`drain`/`child`/`checkpoint`) + `with` on the arenas.
  Capstone: the SAME `run(s)` compiles and runs both sync and async.
- **M4 — `.or_return()`.** Parse-time desugar to `x.match({ .Ok(v) => v, .Err(e) => return .Err(e) })`.
- **M5 — escape check (the hard one, the soundness story).** A value derived from `s` may not outlive `s`;
  error at the offending `return`, naming the value + line. Lexical, tractable because scopes are lexical.
- **M6 — build backend (`build.zen`).** `Build`/`exe.dep`/`exe.link("c")`; pairs link flags with `std.c.libc` decls.
  Largest; `zenc` is emit-only today.

## Acceptance
- Each milestone lands with a green idempotent `--build-self` regen and a passing suite.
- M3 capstone: one `run` proven sync AND async with zero source change.
- M5: a known-bad escape program is REJECTED with a value+line diagnostic.

Subsumes the concrete build of the memory+concurrency-as-stdlib thesis.

---

# The ideal surface — one `Scope`, you pick the mode

*Folded in from the former `ideal-scope-concurrency.md`. NB: per the status note at the top, the
`parallel`/`async` concurrency modes sketched below are the colorless-via-`checkpoint` thesis now
superseded by [`actors-pony-zig.md`](actors-pony-zig.md); the memory/`Scope`/cleanup surface remains
the live design.*

North star: **memory, concurrency, cancellation, and cleanup are one value you open — `Scope` — and
the only thing that changes between single-threaded and 8-core is the MODE you open it with.**
No raw pointers, no `arg` smuggling, no pthread handles, no color (`async`/`await`) keywords.

Legend:  ✅ exists today · 🔨 needs building (the 3 gaps: capturing closures, `parallel` mode, `s.spawn`)

## 1. The shape

```zen
{ with_scope } = std.scope
{ println }    = std.text.fmt

// a PURE leaf: takes no scope → provably cannot allocate, suspend, or spawn.
heavy = (x: i64) i64 { x * x * x }

main = () i32 {
    data: [i64] := [1, 2, 3, 4, 5, 6, 7, 8]

    // open a scope; pick the mode. the body gets ONE capability `s`.
    total := with_scope(.parallel(4), (s) {        // 🔨 mode = 4 worker cores
        s.map(data, (x) { heavy(x) }).sum()        // 🔨 fan out → join → reduce; captures `data`
    })                                             // ✅ joins every task + frees the arena, every exit path

    println(total)                                 // 1296
    0
}
```

The `with_sync`/`with_async` combinators, the arena, checkpoint, and cancellation budget under this are
all ✅ today — what's missing is the closure capture, the `parallel` mode, and `s.map`/`s.spawn`.

## 2. Colorless: the SAME body, sync OR parallel

```zen
// generic over the scope's mode — works under any backing.
crunch = (s: Scope) i64 { s.map(dataset, expensive).sum() }

with_scope(.sync,         crunch)   // single-threaded
with_scope(.parallel(8),  crunch)   // 8 cores — IDENTICAL body, no rewrite
with_scope(.async,        crunch)   // cooperative coroutines
```

This is the capstone that **already runs today** for `.sync`/`.async` (`scope_colorless_sync_async.zen`,
exit 3). `.parallel(n)` is the missing third mode — same idea, pool-backed.

## 3. Fork / join with captured state (replaces the raw thread floor)

```zen
// today (the rough floor): non-capturing fn + state smuggled through arg: RawPtr<u8>, manual offsets…
// ideal:
sum := with_scope(.parallel(2), (s) {
    lo := s.spawn(() { sum_slice(data, 0, 4) })    // 🔨 fork — closure CAPTURES `data`
    hi := s.spawn(() { sum_slice(data, 4, 8) })    // 🔨 fork
    lo.await() + hi.await()                         // 🔨 join — typed results, no pointer reads
})
```

Shared mutation stays race-safe because the scope hands out synchronized cells:

```zen
with_scope(.parallel(4), (s) {
    hits := s.atomic(0)                            // 🔨 scope-owned atomic cell
    s.each(jobs, (j) { hits.add(1) })             // 🔨 concurrent, safe by construction
    hits.get()
})
```

> Captures are sound **because of the safety work already landed**: a closure can't outlive the scope
> (the escape checker rejects `return`ing a scope-derived pointer), and use-after-free / double-free are
> already `zenc check` errors. Structured concurrency + the borrow rules reinforce each other.

## 4. Memory, cancellation, cleanup — all on the same `s`

```zen
with_scope(.parallel(4).deadline(ms(500)), (s) {   // 🔨 mode + deadline, chained
    s.onExit(() { conn.close() })                  // ✅ cleanup ledger — runs on EVERY exit path
    buf := s.acquire(4096)                          // ✅ scratch from the scope arena, freed at exit
    rows := conn.fetch().or_return()                // ✅ error as a value; no `try` keyword
    s.checkpoint().match ({                         // ✅ suspension + cancellation point
        .Go        => {},
        .Stop(why) => return .Cancelled(why)        // deadline hit → bail cleanly, arena still freed
    })
    s.map(rows, transform)                          // 🔨 parallel map
})
```

`onExit`, `acquire`, `checkpoint -> Signal`, the `deadline → .Stop(.Deadline)` budget, and arena-free-on-
exit are ✅ today. `.deadline(ms(..))` sugar, `.or_return()`, and the parallel `map` are the additions.

## 5. Actors, lifetime-bound to the scope

```zen
with_scope(.parallel(4), (s) {
    room := s.actor(ChatRoom(online: 0, posted: 0))  // 🔨 lifetime tied to the scope
    room.send(.Join("alice"))                        // ✅ typed tell
    stats := room.request((r) { .GetStats(r) })      // ✅ typed ask/reply
    stats.online
})                                                   // 🔨 actor stopped + freed on scope exit
```

Typed `send`/`request` over a `Receiver<Msg>` impl is ✅ today (`actor_demo.zen`); only the
scope-bound lifetime (`s.actor(...)`, auto-stop on exit) is new.

## Why this is the right end-state

- **One concept.** A function's signature IS its effect row: takes a `Scope` ⇒ may allocate/suspend/
  spawn; takes none ⇒ a pure leaf that provably can't. No ambient globals, no `--mm:` flag.
- **Colorless.** sync ↔ async ↔ parallel is the *mode you open with*, not a keyword that infects every
  caller. One body, three runtimes.
- **Safe by construction.** Structured concurrency (join-on-exit) + the escape/UAF checker already
  built means captured state can't dangle and tasks can't outlive their scope.
- **The floor stays the floor.** Raw `spawn`/`Mutex`/atomics/`RawPtr` still exist underneath — but you
  reach for them only when writing a new runtime, never in application code.

## The build order to get here
1. **Capturing closures** (`closures-design.md`, M2) — unlocks `s.spawn(() { … })`. *The keystone.*
2. **`parallel` mode** — a `Scope` backing that dispatches `checkpoint`/`spawn` onto `std.concurrent.pool`.
3. **`s.spawn` / `s.map` / `s.each` / `s.atomic`** — the structured-concurrency combinators + scope-owned cells.
4. **Sugar** — `.deadline(...)`, `s.actor(...)`, unify `with_sync/async/parallel` under `with_scope(mode, …)`.
