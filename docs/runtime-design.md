# Runtime design — the current source of truth (2026-07)

**Status:** CURRENT. This is the single source of truth for Zen's runtime/capability model.
It supersedes the *ambient rt* line of design (`rt-scoped-runtime.md`,
`pluggable-runtime-plan.md`, `scope-runtime-goal.md`, `actors-pony-zig.md`), all now marked
SUPERSEDED. `sys-migration-plan.md` is not yet written. Phase-2 Writer→Result is shipped
([`sys-phase2-print-writer.md`](sys-phase2-print-writer.md)).

## The one-line model

**A capability is a value you are handed and must name.** The runtime builds one root
capability — `Sys` — and passes it explicitly to `main`:

```zen
main = (sys: Sys) i32 {
    sys.stdout().write("hello\n")     // needs only a Writer
    h := sys.heap()                   // the process-heap Allocator
    0
}
```

There is **no ambient runtime, no thread-local "current rt", no default singleton**. If a
function can do a side effect, it takes the capability for that effect in its signature. A pure
leaf takes none and provably cannot allocate, print, or spawn.

### Why explicit (the reversal)

The earlier direction (the "ambient rt" docs) made the runtime an **ambient, thread-local
default** that trivial code reached without ceremony (`rt.current()`), explicit only at scope
edges. **The user reversed this.** Ambient capabilities re-hide the effect, defeat test
injection at call granularity, and reintroduce exactly the ambient-fd-1 / ambient-heap
anti-pattern we were trying to remove. Explicit `Sys` threading is the model: the signature is
the effect row.

## Attenuation — narrow capabilities, never the whole `Sys`

`Sys` is a plain record bundling **narrow** capabilities. A library takes the *narrowest*
capability it actually needs, never the whole world:

| Capability | What it grants | Surface (via `Sys`) | Shipped? |
|---|---|---|---|
| `Writer`    | write bytes to one fd (stdout/stderr) | `sys.stdout()` / `sys.stderr()` | ✅ Phase 1 |
| `Allocator` (`Heap`) | process-heap acquire/resize/release | `sys.heap()` | ✅ Phase 1 |
| `Env`       | argv + environment variables | `sys.env()` | ✅ Phase 1 |
| `Clock`     | monotonic + wall time | `sys.clock()` | ✅ Phase 1 |
| `Fs`        | file read/write | `sys.fs()` | ✅ Phase 1 |
| `Spawner`   | spawn actors onto the scheduler | (planned) | ⏳ unbuilt |

```zen
greet = (w: Writer) void { w.write("hi\n") }   // narrowest — a Writer, not Sys
```

`root()` (pure Zen, `std/sys.zen`) assembles the default `Sys` over the real OS. The compiler
emits a niladic `zen_main` trampoline that calls a `(sys: Sys)`-shaped `main` with `root()`, so
the C boundary (`zenrt.c`) stays byte-identical. `main = () i32` (niladic) remains legal — Sys
is **additive**.

## Concurrency — Pony actors (unchanged, sound)

The actor model is **unchanged** by the ambient→explicit reversal and remains the design:

- The **actor is the unit of concurrency**: private state + behaviors that run to completion.
  A behavior never blocks, never awaits, never suspends mid-body — it mutates its own state,
  `send`s messages, and returns.
- **`send` is fire-and-forget**; results come back as messages, not awaited returns. There is
  no `await` / future-`get` / blocking `request`.
- **No function coloring, by construction** — a behavior cannot depend on another actor's
  result mid-body, so there is no sync/async split to color.
- **Parallelism = many actors × many OS threads.** The shipped scheduler is a multi-threaded
  pool (`std.concurrent.pool`) — real pthreads + atomics + `std.sync` Mutex/CondVar, with
  Arc-backed actor lifetime, race-free under stress. Per-worker work-stealing deques are
  roadmap.

Under the Sys model, spawning is a capability: a `Spawner` handed out by `Sys` (planned),
rather than an ambient `rt.spawn`. The actor *semantics* above do not change.

### Sendability is a static, sound property (unchanged)

Data-race freedom is a **static property of the checker**, not a runtime barrier or GC:

- **Move-on-send** — a value passed to `send` is moved; using it after is use-after-move (a
  `zenc check` error, same machinery as use-after-free).
- **No actor-local escape** — a message may not carry a pointer into the sender's actor-local
  region.
- **Sendable data only** — a message is a value (copied) or an `owned` block (Pony `iso`, moved);
  borrowed pointers into another actor are rejected.

Sendability is read off the payload's **type** (the mode lattice: `frozen` (Pony `val`) =
deeply immutable / freely aliasable, `owned` (Pony `iso`) = uniquely owned / sent by move, plain
`value` = scalars, the common zero-ceremony case), **not** an explicit `share()`/`view()` stdlib verb.
This is shipped and sound.

## Panic isolation

Goal: a behavior panic (div0 / OOB / null / explicit) kills **that actor** and lets the pool
keep running the others — NOT restart / links / monitors (full OTP is deferred). Every normal
panic funnels through one choke point (`zen__panic` → `abort()` today); the isolation slice
intercepts it per-worker (setjmp/longjmp trampoline around the behavior call). Stack-overflow
recovery (signal-based) is deferred. See `actor-panic-isolation-findings.md`. This is
early-phase, not fully shipped.

## Two memories (design — load-bearing concept, verbs unbuilt)

One genuinely good idea from the ambient-rt line survives as a **concept**, decoupled from the
ambient delivery mechanism that was rejected. Full design:
[`two-memory-design.md`](two-memory-design.md).

- **scratch** — cheap region/bump memory, bulk-freed, scoped to (at most) one behavior run;
  **never** escapes its scope, **never** crosses a send or lands in actor state.
- **shared** — Arc-tracked heap; refcounted; the only memory that may cross an actor boundary.

Actor state is constructed under the actor's own memory at spawn (not the spawner's), which
kills cross-actor UAF by construction. Promotion (scratch→shared) is explicit via planned
`.share(alloc)` / `.give(alloc)` verbs (see design doc).

The **scratch-escape checker is shipped** (rejects spawner scratch in sends/state); promotion
verbs and scratch capabilities are **unbuilt**.

## What is shipped vs unbuilt (no overclaiming)

**Shipped:**
- `main = (sys: Sys) i32` with attenuated `Writer`/`Heap`/`Env`/`Clock`/`Fs` caps (Phase 1,
  #435); niladic `main` still legal; seed byte-exact.
- The `genjs` JS backend (Zen→JS, `emit-js` / `build --target js`, #436) — dual-backend.
- The multi-threaded actor pool + Arc-backed lifetimes + the static sendability checker.

**In progress / unbuilt:**
- **`Spawner` capability** — spawn-as-a-Sys-capability (actor semantics already shipped; the
  capability surface is not).
- **Two-memory promotion verbs** — `.share`/`.give` unbuilt; design in [`two-memory-design.md`](two-memory-design.md).
- **Ambient-`println` retirement** — batch migration; honest `Writer` spine already shipped
  ([`sys-phase2-print-writer.md`](sys-phase2-print-writer.md)).

**Shipped (Sys phase 2):**
- **Writer → Result** — `Writer.write` returns `Result<i64, IoError>`.

## See also

- [`two-memory-design.md`](two-memory-design.md) — scratch vs shared, promotion verbs (this lane).
- [`sys-phase2-print-writer.md`](sys-phase2-print-writer.md) — honest Writer spine (shipped).
- `sys-migration-plan.md` — full Sys execution plan; **not yet written**.
- Superseded (history, do not follow): `rt-scoped-runtime.md`, `pluggable-runtime-plan.md`,
  `scope-runtime-goal.md`, `actors-pony-zig.md`.
