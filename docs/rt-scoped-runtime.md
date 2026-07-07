# rt — the scoped runtime (design spec, v2)

> **SUPERSEDED (2026-07): ambient rt reversed → explicit Sys. See [runtime-design.md](runtime-design.md).**
> Kept for history. The ambient/thread-local "current rt" delivery in this doc is NOT the current
> design; capabilities are now threaded explicitly via `main(sys: Sys)`.

**Status:** approved direction (judge panels 2026-07: design 7.9/10 "nicer than Pony and
Zig", after fatal-hole revision from the 5.9 draft). This is the spec we build against.
Rulings: `rt-design-judge-ruling-2026-07.md`, `three-things-ruling-2026-07.md`.

## The idea in one line

**rt is the reification of "the scope you run in":** what memory it draws (mem), when that
memory dies (scope/drop), and who executes you (sched) — one unforgeable capability,
delivered like Pony's `Env`, pluggable like Zig's `Allocator`/`Io`, ambient *within* a
scope and explicit only at boundaries.

```zen
// build.zen — the executable IS the root rt-scope
exe.runtime(shared: Arc, sched: Pool, scratch: PerBehavior)

// main.zen — main receives it; a behavior looks like a plain method; sends are colorless
main = (rt: Rt) Result<i32, IoError> {
    c := rt.spawn(Counter(total: 0, seen: vec())).or_return()
    c.send(.Inc(3))
    ok(0)        // main = root actor; exit joins quiescence
}
```

## Prior art and the delta

| | Pony | Zig | **Zen rt** |
|---|---|---|---|
| provenance | `Env`/`AmbientAuth` to `Main.create` | none declared | **build.zen → `main(rt)`** |
| memory | hidden per-actor heap, not pluggable | `Allocator` param threaded per-call | two memories, plugged once, ambient in scope |
| concurrency | built-in sched, `be` behaviors | new `std.Io` value (0.16), threaded per-fn | `rt.sched` plug: `Inline` / `Pool` |
| coloring | colorless | colorless via stack-switch | **colorless by construction** (run-to-completion, no await exists) |

Zig threads two capabilities through every signature (noise, metastasis); Pony delivers one
but hides memory. Zen: **delivered like Pony, pluggable like Zig, ambient-within-scope like
neither** — that resolution is the contribution.

## 1. Two memories (the organizing principle)

Everything hangs off this split. Conflating "cheap local memory" with "memory that crosses
an actor boundary" was the fatal hole in v1 (cross-actor UAF).

| | **scratch** | **shared** |
|---|---|---|
| mechanism | region/bump, bulk-freed | Arc-tracked heap |
| lifetime | current scope — default **one behavior run** | refcounted |
| escapes scope? | **never** (escape/UAF checker, temporal) | yes |
| crosses a send / actor state? | **never** | **only this** |
| cost | pointer bump | rc ops |

- Actor state is constructed **under the actor's own memory** at `spawn` — never the
  spawner's (kills the v1 flagship UAF by construction).
- Promotion is explicit and visible — the ONLY place a lifetime changes:
  `v.share(rt)` (freeze → Arc) · `v.give(rt)` (iso move; sender's binding dies).
- No free alloc×gc matrix: scratch never has gc; shared always does. gc policy (rc/arc;
  ORC aspirational — we do NOT claim ORCA) is a per-actor choice for its shared allocs.

## 2. Ambient-within-scope, explicit-at-boundary (the calling convention)

Ruled 4/4 against rt-on-every-allocating-fn (metastasis: ~80% of non-leaf fns transitively
allocate — that marker is Haskell's ubiquitous `IO`, informationally dead). And ruled
against Odin-style dynamic ambient (re-hides the effect; kills test injection).

- **Explicit at exactly three places:** `build.zen` (root), `rt.spawn` (actor gets its
  own), `rt.region((r) { ... })` (nested override — tests, scratch arenas, CLI code).
- **Ambient everywhere else.** Mechanism: the scheduler already knows the current actor
  (per-worker thread-local, set at behavior start — exists since the parallelism work).
  "Current rt" = current actor's rt. You can only ever reach *your own* actor's rt —
  exactly Pony's "allocate in my heap", zero signature noise, still unforgeable.
- `Vec.new()`, `[1,2,3]`, `Map.new<K,V>()` draw the current scratch region. Containers are
  **unmanaged** (no stored handle — Zig's own managed→unmanaged lesson) but
  ambient-allocating; `v.push(x)` takes no allocator.
- UFCS receiver stays the **domain noun**: `cfg.render_rows()`, `iter.filter(f).map(g)
  .collect()` — rt never steals the receiver slot (v1 mistake, retracted).
- **Honesty note (retracted claim):** "no rt param ⇒ no allocation" is NOT claimed
  (closures capture, self carries, rt bundles). The true guarantee is scope-level:
  *nothing allocated here outlives here unless visibly promoted.*
- Attenuation: `rt.mem`, `rt.sched` are derived, smaller capabilities (AmbientAuth →
  TCPAuth pattern) — hand code only what it uses.

### 2b. The ambient Rt: default singleton + injection (user-directed 2026-07-06)

The ambient rt is a **default singleton so trivial programs need ZERO setup** — `main`,
plain fns, hello-world use it (heap alloc, default sched). But it is **THREAD-LOCAL, not a
true global**: the pool runs different actors on different workers concurrently, so "current
rt" must be per-worker (a shared mutable global would race + hand a behavior the wrong
actor's heap). So: a thread-local current-rt with a process-wide default.

Surface (`rt = std.rt`): `rt.current()` reads the ambient rt (fns that allocate read it — NO
rt param threading). Spelled `rt.current()` / `rt.with(...)` — NOT `Rt.current()` / `Rt.with()`:
Zen has no static/associated-method call syntax (`Type.func()` does not resolve), so the
ambient surface is module-qualified free functions with `rt` as the module alias — same
reading, idiomatic Zen. Injection/override at boundaries:
- `build.zen` `exe.runtime(...)` sets the process-wide DEFAULT (M3).
- `rt.spawn(actor)` gives each actor its OWN rt, set as the ambient during its behaviors →
  per-actor heap, Pony-style (M4). **M4 IS the injection mechanism**: the pool already sets
  a thread-local current-actor when running a behavior; the same hook sets current-rt (writes
  the `slot` thread-local in the behavior trampoline — the foundation's `ready==0` zeroed-worker
  fallback already makes an unset worker safe, so M4 is a pure write, no rework).
- `rt.with(custom, body)` rebinds the thread-local for the dynamic extent of `body`, then
  restores it (arenas + crucially TEST injection: a mock / failing allocator). Save-set-restore
  around the block; `body` is a niladic callback fn (Zen has no trailing-block syntax), mirroring
  std.scope's `with_sync`/`with_pool` combinators. Restore runs even when `body` early-returns.

This is the judge-panel's "ambient within a statically-known lexical/actor region, explicit
at the region edge" + a default so trivial code needs no ceremony. It is NOT spooky-dynamic
Odin scope (test injection is preserved via `rt.with`; overrides are lexical/actor-bounded).

The foundation slice (§2b, shipped) is `zen/std/rt.zen`: `Rt` (allocator vtable + state + `ready`
sentinel), `rt.current()`, `rt.with(custom, body)`, `rt.alloc/resize/release`, `rt.heap_rt()`,
`rt.mem_rt(...)`. See `docs/rt-foundation-notes.md` for the mechanism + the M4 hook.

## 3. Concurrency: pure Pony, no multisync

- Actors = `T.impl(Actor, { receive = (self: MutPtr<T>, m: Msg) void { m.match(…) } })`.
  No `be`/`spawn`/`await` keywords — spawn is `rt.spawn(…)`, a method returning
  `Result<Handle, IoError>` (#367).
- Behaviors are **run-to-completion**; sends are value-less and colorless; there is no
  suspension point, so coloring is *impossible*, not hidden. `checkpoint()`/coroutine
  hidden-await is REMOVED as user surface.
- I/O completions are **messages** (reactor delivers `.Done(bytes)` to your mailbox).
- Replies: `ReplyRef` — a promise fulfilled by a delivered message, never a blocking get.
- `main` is the root actor; program exit = quiescence join (sends can't be silently lost).
- `sched: Inline` = deterministic single-thread (tests); `sched: Pool` = the existing
  work-queue N-core scheduler (per-worker deques are Cut-2 roadmap; we don't claim
  work-stealing until they exist).

## 4. Sends are spatial (escape ≠ isolation) — sendability is a TYPE capability, NOT a verb

Escape analysis is temporal ("doesn't outlive"); Pony `iso` is spatial ("no aliases").
**CORRECTION (2026-07-05, user):** sendability is a property the checker reads off the
payload's TYPE — like Pony reference capabilities — NOT an explicit `share()`/`view()`
stdlib verb. A message is a **plain type**; the receiver reads it as its normal type
(`m.s` is an `i64`, never `Shared<i64>.get()`). No wrapper leaks into sender or receiver.
The `share`/`view`/`Shared<T>` surface (PR #398, held unmerged) is REJECTED as Arc-cosplay.

A send payload must be exactly one of (checker classifies from the type):

1. **value** — plain data, no pointers; copied by value. The COMMON case; needs ZERO
   ceremony (a struct/enum of scalars is trivially sendable — verify this already holds);
2. **`val`** — deeply immutable data (all reachable state read-only); freely sendable +
   aliasable. Built on the existing `Ptr<T>` (readonly, = Pony `box`) vs `MutPtr<T>`
   (= `ref`) lattice, lifted to whole values. The compiler may refcount it internally,
   but that is INVISIBLE — no user verb;
3. **`iso`** — uniquely owned (`Own<T>`), sent by MOVE; the move-on-send checker kills the
   sender's binding. NOTE (#398 finding): today the move checker only kills `Own<T>`, not
   bare value locals — `iso` sends must fix that.

Zen already has the bottom half of the cap lattice (`Ptr`/`MutPtr` = `box`/`ref`) + a
move checker (`Own<T>` ≈ `iso`). M2 lifts these to send-classification; no new verbs.

## 5. The teaching checker (ship-list item 5)

The escape checker is load-bearing for the whole ambient model. Every escape rejection must
print the one-token remedy verbatim:

```
error[scratch-escape]: `rows` (scratch, this behavior) is stored in actor state
hint: promote it: `rows.share(rt)` (freeze) or `rows.give(rt)` (move)
```

## 6. Error surface (shipped 2026-07-02)

`.or_return()` any-position (#366) · `.expect(msg)`/`.or`/`.or_else`/`.map_err`, no bare
unwrap (#365) · fallible APIs return `Result` always, `try_*` doubling deleted (#367) ·
statement-initial `.Ok(x)` parses (#364). Enum ctors stay **dotted** (5/5): qualified
`Type.Variant` keeps the dot on the type's line (grammar law since #364).

## Milestones

- **M1 — two memories in the checker:** scratch-vs-shared as checked kinds; actor state +
  send payloads must be shared/value; construct-under-actor spawn. (Everything leans on this.)
- **M2 — promotion verbs + teaching errors:** `share`/`give` + `error[scratch-escape]`
  with verbatim fixes; adversarial fixture suite (the checker is the product).
- **M3 — rt value + build.zen root:** `Rt` trait-object (no `<A,S,G>` generic threading),
  `exe.runtime(...)` → `main(rt)`, `rt.region`, attenuated `rt.mem`/`rt.sched`.
- **M4 — actors on rt:** typed spawn/send routed through the pool scheduler (heals the
  typed-vs-parallel split-brain); per-behavior scratch reset; quiescence-join main.
- **M5 — send shapes:** freeze/`Arc` + iso-move enforcement unified as THE send check.

Open (decide before M3 code): default scratch lifetime per-behavior vs per-actor
(leaning per-behavior); library convention for "fn needs shared memory"; nested-spawn
`self.rt` surface.
