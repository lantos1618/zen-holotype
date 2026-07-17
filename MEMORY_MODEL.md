# Zen Memory Model

This is the current memory model implemented by this repository. It is not the
final pointer/borrow/lifetime design.

## The model: explicit capabilities, threaded allocators

Zen's memory model is **explicit**, not ambient. Memory comes from an `Allocator`
that a function receives as a parameter, so allocation is visible in the
signature — never a hidden global heap. The outside world enters through a
**capability**: the entry `main = (sys: Sys) i32` receives a `Sys`
(`std.sys`) and hands out narrow capabilities, notably `sys.heap()` (the process
`Allocator`) and `sys.stdout()`/`sys.stderr()` (`Writer`s). Libraries take the
narrowest capability they need (an `Allocator`, a `Writer`), which is the same
discipline one level up from threading `MutPtr<A>` allocators through container
and ownership APIs.

> **The ambient runtime is not the model.** `std.rt` (a thread-local `Rt`
> capability with `rt.alloc`/`rt.with`) and `std.scope` exist as an experiment
> toward scoped runtimes, but the shipped, documented model is the explicit one
> above. The A-wrapper convenience constructors (`vec.new`, `set.new`, `hmap.new`,
> and their `from`/`from` variants) no longer draw from `std.rt` — they capture the
> process heap once via `dyn_heap()` at construction and store that `DynAlloc` for
> the container's lifetime. `new_in`/`from_in` remain the explicit real paths.

String bytes carry their own provenance discipline — static `string_literal`,
borrowed NUL-terminated `string_cstr`, general borrowed `string_view`, and the
heap-owned `String` (freed through the allocator that owns its buffer). The old
`text`/`Cstr`/`str` spellings are parser aliases; see [STRING_TYPES.md](STRING_TYPES.md).

## Current Rules

Allocation is explicit. User-facing containers, ownership types, and runtime APIs
should take an allocator (`MutPtr<A>`) or use a documented default-allocator convenience wrapper.
Raw `malloc`, `free`, pointer arithmetic, and `@` primitives are the substrate for
bootstrap, FFI boundaries, and low-level std modules.
`std.mem.raw` keeps direct `alloc`/`zeroed` escape hatches, and also exposes
`try_alloc`/`try_zeroed`/`try_of` when allocation failure should stay in the
value flow.

Raw allocation calls are guarded by `tests/harness_boundaries.zen`:
`malloc`/`calloc`/`realloc`/`free` may appear only in `std.mem.alloc`,
`std.mem.raw`, or the compiler bootstrap allocation shim. Everything else should
thread an allocator and call `acquire`/`resize`/`release` or a higher-level
allocator-aware API.

Arena backing storage follows the same rule. `arena.new_in(backing, cap)` and
`Arena.free_in(backing)` acquire and release the arena's backing block through a
caller allocator. `Arena.free` is the default-heap convenience path.

Compiler-adjacent AST builders follow the same convention where they return
owned slices: `std.internal.ast.dbuf_in` and `derive_accessors_in` place
declaration buffers through a caller allocator, while the short builders use the
documented default allocator helpers.

Owned values are library types:

- `Own<T>` owns a ref-counted heap block and finalizes the payload through `Drop`
  when the last owner is released.
- `Rc<T>` is single-threaded shared ownership.
- `Arc<T>` is atomically reference-counted shared ownership.
- `std.mem.trace.Rc<T>` is the cycle-tracing experiment. Its public allocation,
  root-registration, and collection entrypoints have allocator-first forms
  (`tracked_in`, `root_in`, `collect_in`) plus default-heap wrappers. Tracked
  block allocation also has `try_tracked_in` / `try_tracked` so allocation
  failure can stay in the value flow.

The preferred ownership constructors are allocator-first:

```zen
own = std.mem.own
alloc = std.mem.alloc
heap := alloc.default()
o := own.new_in(heap.addr(), own.Resource(id: 7, slot: 0))
o.release_in(heap.addr())
```

Fallible constructors are value-shaped and use the same allocator:

```zen
alloc = std.mem.alloc
heap := alloc.default()
r := own.try_new_in(heap.addr(), own.Resource(id: 7, slot: 0))
r.match({
    .Ok(o) => { o.release_in(heap.addr()) },
    .Err(e) => {}
})
```

The short default-heap forms are intentionally absent for ownership containers.
Use `new_in`/`try_new_in` plus `release_in`/`drop_in` so the allocator that owns
the block is explicit at both construction and release.

## Sendability (move-on-send)

Actor sends have a second enforced rule. When an owned `Own<T>` is passed into a
`send(handle, msg)`, ownership transfers to the receiving actor, so the checker
kills the sender's binding — a later use is `error[ownership]`. This stops the
double-free where both actors free the same block. A `Ptr<T>` is sendable only
when `T` is deeply immutable; `Arc<T>` is the shared-sendable path; a companion
scratch-escape pass keeps actor-local scratch from escaping across a send. At
runtime, a `panic` inside one actor is isolated to that actor (per-worker catch in
`zenrt.c`) rather than killing the process.

## Local ownership rule

The checker enforces one local ownership rule before generic inlining erases
method calls into raw pointer operations:

```zen
own = std.mem.own
alloc = std.mem.alloc
heap := alloc.default()
o := own.new_in(heap.addr(), own.Resource(id: 7, slot: 0))
o.release_in(heap.addr())
o.get()          // rejected: use of consumed owner
```

For a local variable in the same function body:

- `Own<T>.release_in(...)` consumes that local.
- `Rc<T>.drop_in(...)` consumes that local.
- `Arc<T>.drop_in(...)` consumes that local.
- A later value use of the same local is rejected as `error[ownership]`.

Cloning before consuming is still valid because the clone is a different local:

```zen
own = std.mem.own
alloc = std.mem.alloc
heap := alloc.default()
o := own.new_in(heap.addr(), own.Resource(id: 7, slot: 0))
c := o.clone()
o.release_in(heap.addr())
n := c.get().id
c.release_in(heap.addr())
```

## Partly Enforced; Remaining Work

The compiler now enforces pointer direction, typed-raw null checks, nested type
invariance, local alias/consume flow, loop/branch UAF checks, and several escape
and sendability rules. These are still open:

- complete branch-sensitive/interprocedural ownership flow;
- alias tracking through arbitrary parameters, slices, fields, and generic wrappers;
- general pointer lifetimes and borrow scopes beyond the current escape passes;
- branch-refined null proofs (today `assert_nonnull` carries the proof in the type);
- sound nullability for the permissive `RawPtr<u8>` allocator/FFI floor;
- full thread-safety traits (the move-on-send and deep-immutability send rules
  above are enforced; a general `Send`/`Sync`-style capability layer is not);
- guaranteed destructor coverage for every owning type.

The current rule is intentionally narrow but real: it rejects a concrete
use-after-release/drop pattern in the compiler instead of relying on comments or
examples.
