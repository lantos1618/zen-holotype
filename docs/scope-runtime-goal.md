# GOAL — Scope / Runtime / Capability surface (colorless, no-keyword)

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
