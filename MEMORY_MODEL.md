# Zen Memory Model

This is the current memory model implemented by this repository. It is not the
final pointer/borrow/lifetime design.

## Current Rules

Allocation is explicit. User-facing containers, ownership types, and runtime APIs
should take an allocator (`MutPtr<A>`) or use a documented default-allocator convenience wrapper.
Raw `malloc`, `free`, pointer arithmetic, and `@` primitives are the substrate for
bootstrap, FFI boundaries, and low-level std modules.
`std.mem.raw` keeps direct `alloc`/`zeroed` escape hatches, and also exposes
`try_alloc`/`try_zeroed`/`try_of` when allocation failure should stay in the
value flow.

Raw allocation calls are guarded by `tests/test_primitive_boundaries.py`:
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

The checker now enforces one local ownership rule before generic inlining erases
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

## Not Yet Enforced

These are still open design/compiler work:

- branch-sensitive ownership flow;
- alias tracking across assignments, parameters, slices, and fields;
- pointer lifetimes and borrow scopes;
- `Ptr` / `MutPtr` / `RawPtr` capability enforcement;
- non-null `Ptr<T>` versus nullable option/raw pointer discipline;
- thread-safety traits for sending `Rc`, `Arc`, actor refs, and raw pointers;
- guaranteed destructor coverage for every owning type.

The current rule is intentionally narrow but real: it rejects a concrete
use-after-release/drop pattern in the compiler instead of relying on comments or
examples.
