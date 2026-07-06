# rt foundation slice — ambient thread-local Rt (implementation notes)

Implements docs/rt-scoped-runtime.md **§2b** (the ambient Rt: default singleton + injection).
This is the FOUNDATION slice only — M4 pool-routing and M3 build.zen are deferred (see below).

Module: `zen/std/rt.zen` (pure stdlib; not part of the compiler sources, so `bootstrap/zenc.gen.c`
is untouched). Import as `rt = std.rt`.

## Surface

| call | signature | meaning |
|---|---|---|
| `rt.current()` | `() -> Rt` | read the ambient thread-local rt (heap default when unset) |
| `rt.with(custom, body)` | `<R>(Rt, () R) -> R` | save-set-restore the ambient rt around `body` |
| `rt.alloc(n)` | `(i64) -> RawPtr<u8>` | allocate n bytes via the AMBIENT rt (no allocator param) |
| `rt.resize(p, n)` | `(RawPtr<u8>, i64) -> RawPtr<u8>` | grow/shrink via the ambient rt |
| `rt.release(p)` | `(RawPtr<u8>) -> void` | free via the ambient rt |
| `rt.heap_rt()` | `() -> Rt` | the process-wide default (heap malloc/free/realloc) |
| `rt.mem_rt(acq, rsz, rel, state)` | build a custom rt from an allocator vtable | for injection |

### Why not `Rt.current()` / `Rt.with(...)` verbatim
Zen has no static/associated-method call syntax (`Type.func()` does not resolve — verified; only
enum ctors `Type.Variant` and module-qualified calls `alias.func()` exist). The spec's `Rt.current()`
is realised as `rt.current()` where lowercase `rt` is the **module alias** (`rt = std.rt`) — same
reading, idiomatic Zen. `with` parses fine as a plain function name.

## The Rt value (this slice)

```
Rt: { mem_acquire, mem_resize, mem_release : fn-ptrs, state: RawPtr<u8>, ready: i64 }
```

- The three `mem_*` fields are the **allocator vtable**, with `Self` erased to `RawPtr<u8> state`, so
  any allocator plugs in with no generic `<A>` threading — the M3 trait-object shape, prototyped here.
  (Fields are prefixed `mem_` so they never collide with the same-named public fns `resize`/`release`;
  the compiler otherwise auto-mangles a field that shadows a top-level fn name and breaks field access.)
- `state` is the allocator instance data (null for heap).
- `ready` is the init **sentinel** (see below). sched/gc policy fields join the bundle in M3/M4; the
  surface above is stable across that growth.

## How the thread-local is stored (the key mechanism)

Reuses the **existing `thread_local(x)` mechanism** (same one std.concurrent.coroutine uses for coro
swap state). `slot := thread_local(heap_rt())` emits `static _Thread_local Rt slot;` whose init runs
in `zen__init_globals()` — which fires **once, on the main thread, at `zen_main` start**.

Consequence for M4 (pool runs actors on many OS workers): a **fresh worker thread sees a zero-init
slot** (init did not run there). The `ready` field is the guard: `ready == 0` means "this slot was
never set on this thread" → `current()` falls back to `heap_rt()`. So the process-wide default holds
on every thread with zero per-thread setup, and no worker is ever handed a half-built rt. This is
also exactly the hook M4 will use: the pool already sets a per-worker current-actor thread-local when
running a behavior; it sets `slot` (the current-rt) the same way.

`rt.with(custom, body)` is plain **save-set-restore** on `slot` — behaviors are run-to-completion and
there is no unwinding, so the saved slot can't leak.

## Proofs (tests/fixtures/zen/rt_ambient_*.zen, wired into the oracle)

- **(a) default, zero setup:** a program calls `rt.alloc` / `rt.release` with no rt setup at all; the
  ambient heap default serves it. Allocs made *outside* any `with` do not touch an injected counter.
- **(b) with-inject:** `rt.with(counting_rt, body)` where `counting_rt`'s `acquire` bumps a counter —
  three ambient `rt.alloc` calls inside the block drive the counter to exactly 3; outside stays 0.
- **(c) test-inject:** `rt.with(failing_rt, body)` where `acquire` always returns null — an ambient
  `rt.alloc` inside the block is observed to fail (returns null); after the block the ambient is
  restored to the heap default and allocation succeeds again.

## Deferred (NOT in this slice)

- **M4 pool-routing:** the pool setting the ambient rt per-actor (the injection hook is designed for
  above; the `ready` sentinel already makes worker threads safe).
- **M3 build.zen root:** `exe.runtime(...)` setting the process-wide default; attenuated `rt.mem`/
  `rt.sched`; sched/gc policy fields on `Rt`.
- **Arena-backed `arena_rt`:** deferred to M3 — needs a `MutPtr<Arena>`↔`RawPtr<u8>` cast idiom; the
  counting/failing rts prove injection without it.
- **Stdlib migration:** the existing explicit-allocator APIs (`Vec.new(alloc)`, arenas, etc.) are
  UNCHANGED. This slice only ADDS the ambient path; migrating stdlib to read the ambient rt is a
  later slice. Every existing fixture stays byte-identical (default never changes existing behavior).
