# Actor API convergence — incremental plan (GOALS #14)

Status: **IN PROGRESS** (Wave 3 slice). Full merge of cooperative `actor.zen` + parallel
`pool_actor.zen` behind one typed spawn is tracked here; this doc is the conductor-facing
milestones before coroutine/checkpoint retirement.

## End state (unchanged ruling)

Per [`runtime-design.md`](runtime-design.md):

- One typed spawn surface schedules on the pool (run-to-completion, no blocking `request`/`ask`).
- Cancellation is a message, not a hidden future cancel.
- Spawning is a **`Spawner` Sys capability**, not ambient `rt.spawn`.

## Current surfaces (honest)

| Surface | Scheduling | Notes |
|---|---|---|
| `std.concurrent.actor` | Cooperative — caller-thread inline drain | `send` + `run`/`request`/`ask` |
| `std.concurrent.pool_actor` | Parallel — `std.concurrent.pool` workers | Per-(M,ActorT) dispatch trampoline |

`spawn_actor` is deliberately named (not `spawn`) to avoid clashing with `std.thread.spawn`.

## Incremental slices (Wave 3 → merge)

1. **Document + stub capability** (this slice): `Spawner` record on `Sys` with `spawn` returning
   `Result<…, IoError>`; body panics `unimplemented` until pool wiring lands. Demos keep using
   `pool_actor` directly.
2. **Typed pool spawn helper**: thin wrapper `spawner.spawn(pool, actor)` delegating to
   `spawn_actor_heap` + existing trampolines; cooperative `actor.run` marked deprecated in header.
3. **Retire blocking replies**: migrate `request`/`ask` call sites to message+match; delete paths.
4. **Coroutine substrate removal**: drop `coroutine.zen` / checkpoint from default builds once
   actor-only paths cover the example corpus.

## Gates per slice

Each slice merges only after isolated `make harness` ALL PASS and byte-exact seed fixpoint.
