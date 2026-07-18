# Zen memory and safety model

Zen exposes allocation and pointer provenance in types and signatures. The compiler enforces useful
local rules, but it is not a Rust-style borrow checker and does not implement move semantics for all
values. This document separates enforced guarantees from conventions and proposals.

## The intended shape

- Allocation is a capability. Heap-backed APIs receive an `Allocator` or a concrete allocator.
- Ordinary values copy by value unless a specific ownership/send rule says otherwise.
- Pointer direction and nullability are explicit: `Ptr`, `MutPtr`, and `RawPtr`.
- Recoverable allocation failure is `Result<_, IoError>`.
- Owned wrappers make release/drop operations visible.
- Actor boundaries apply extra sendability and scratch-escape checks.

`std.sys.Sys` is the preferred root capability at an executable boundary. Libraries should accept
the narrow capability they need. A legacy `std.rt` ambient allocator/runtime remains public and is
used by parts of the actor stack; removing or explicitly legitimizing it is unfinished work.

## Pointers

| Type | Nullability | Write through pointee | Intended use |
|---|---|---|---|
| `Ptr<T>` | Non-null | Rejected | Read-only borrow. |
| `MutPtr<T>` | Non-null | Allowed | Writable borrow. |
| `RawPtr<T>` | Nullable/raw | Allowed by raw operations | FFI and allocator floor. |

All three lower to target pointers, but their kind survives parsing, formatting, type compatibility,
and validation.

The checker currently enforces:

- `Ptr<T>` cannot satisfy `MutPtr<T>`;
- field, nested-field, index, and `store` writes rooted through `Ptr<T>` are `error[ptr-write]`;
- a non-null pointer field cannot be omitted from a record literal;
- a nullable `RawPtr<T>` cannot be dereferenced or passed to a non-null slot without proof;
- `assert_nonnull(raw)` panics on null and returns `MutPtr<T>`;
- recursive types must introduce indirection rather than contain themselves by value.

`RawPtr<u8>` is the trusted byte-buffer floor used by allocators, FFI, and compiler internals. Its
intrinsic rules are intentionally less strict. A plain comparison against null does not flow-narrow a
`RawPtr`; bind the result of `assert_nonnull`.

These rules do not prove lifetime, exclusive aliasing, or provenance. A `MutPtr<T>` can still be
aliased, and raw pointer operations can violate memory safety. `Ptr` means read-only through that
path, not globally immutable memory.

## Allocators and regions

`std.mem.alloc.Allocator` is the narrow allocation trait. The common heap is explicit:

```zen
halloc = std.mem.heap
use_heap = () i32 {
    heap := halloc.gpa()
    p := heap.addr().acquire(64)
    p.store(42)
    value := p.load()
    heap.addr().release(p)
    to_i32(value)
}
```

Fallible generic helpers `try_acquire` and `try_resize` lift null/sentinel allocation failure into
`Result`.

An arena owns one block supplied by a backing allocator:

```zen
arena_mod = std.mem.arena
halloc = std.mem.heap
{ expect } = std.core.result
run = () i32 {
    heap := halloc.gpa()
    arena := arena_mod.make_in(heap.addr(), 4096).expect("arena allocation")
    p := arena.addr().acquire(32)
    p.store(7)
    value := p.load()
    arena.addr().free_in(heap.addr())
    to_i32(value)
}
```

Individual arena releases are no-ops; `free_in` releases the backing block. Returning an arena-backed
pointer beyond the arena lifetime is not generally proven safe by the type system.

Collections and owned text accept allocators. APIs that allocate normally return `Result`; a method
named `expect` or an explicitly panicking wrapper is the deliberate fail-fast boundary. Exact API
names belong to `zenc doc` and the module source rather than a duplicated table here.

## Ownership wrappers

The current library supplies:

- `Own<T>`: reference-counted owner that invokes `T: Drop` when the final reference releases;
- `Rc<T>`: non-atomic reference counting;
- `Arc<T>`: atomic reference counting for shared cross-thread state;
- `Arena`: region/bump allocation;
- tracing primitives in `std.mem.trace`.

`own.new_in`, `rc.new_in`, and `arc.new_in` take an allocator and return `Result`. Their release
methods also require the allocator that owns the block.

Despite its name, `Own<T>` is not a universal affine value category: it has an explicit `clone` and
uses a reference count. The checker applies its bare-copy/parameter/field move rules specifically to
tracked `Own<T>` locals; it does not turn every Zen value into a moved value.

## Enforced ownership and escape checks

The semantic passes reject several concrete hazards:

| Rule | Current behavior |
|---|---|
| Use after `Own.release_in`, `Rc.drop_in`, or `Arc.drop_in` | Rejected for tracked locals and aliases. |
| Bare `Own<T>` copy `copy := owner` | Treated as consuming the source unless an explicit clone is used. |
| Passing `Own<T>` into an `Own<T>` parameter | Consumes the caller binding. |
| Moving `Own<T>` into a record field or slice element | Consumes the source binding. |
| Release through a recognized borrowed/aliased path | Propagates to the tracked owner in covered forms. |
| Returning the address of a local/stack-derived value | Rejected by escape analysis in covered forms. |
| Escaping through bounded call forwarding | Checked through a limited interprocedural search. |

The implementation is flow-sensitive enough to inspect branches and nested bodies, but remains a
set of AST analyses, not a single control-flow ownership model. Documented boundaries in the code
include simple/bare-variable alias classes, a bounded interprocedural forwarding budget, and
under-rejection around some generic record field moves. Globals, arbitrary pointer arithmetic,
complex aliases, and every possible lifetime path are not proven.

`Rc<T>` and `Arc<T>` have tracked explicit drop/use-after-drop checks, but this document does not
claim the same bare-copy affine rules for them. Call their explicit `clone`/`drop` operations rather
than relying on an untracked value copy.

Therefore the honest guarantee is: the compiler blocks a broad, regression-tested family of local
use-after-consume and stack-escape mistakes. It is not a proof of memory safety for arbitrary Zen.

## Actor sendability

The checker adds rules at recognized actor sends:

- sending `Own<T>` consumes the sender binding;
- a later sender use is `error[ownership]`;
- `Rc<T>` is rejected across thread/actor boundaries;
- mutable pointers and mutable reachable payloads are rejected;
- `Ptr<T>` is sendable only when the reachable value is classified deeply immutable;
- `Arc<T>` is the shared-sendable wrapper;
- plain pointer-free values copy into messages rather than acquire global move semantics.

This is a pragmatic static pass. It recognizes the current send APIs and derives a mode/sendability
classification from types. It is not yet one general capability lattice applied to every call.

The scratch-escape pass also rejects allocator/arena/stack-looking storage embedded in actor state or
sent across a boundary. Today that pass is a name/shape heuristic over allocation expressions, not an
implemented pair of `Scratch<T>`/`Shared<T>` region types. Earlier diagnostics recommended nonexistent
`.share`/`.give` verbs; current guidance instead points to actor-owned construction, an owning value
from suitably long-lived storage, or immutable `Arc<T>` sharing.

## Panic and cleanup

Runtime checks panic on integer divide/modulo errors, slice bounds violations, and failed non-null
assertions. Main and ordinary synchronous code abort the process.

The pooled actor worker installs an isolation boundary. A behavior panic or worker stack overflow
kills that actor and keeps the worker/pool alive. This is not language unwinding: the runtime uses a
non-local recovery boundary, so allocations made during the failed behavior can leak, and queued
typed message boxes do not yet have a type-aware cleanup path. Cooperative caller-thread actor drains
do not receive this isolation.

## Not guaranteed yet

- General borrow/lifetime checking or exclusive mutable borrows.
- Safe arbitrary `RawPtr`/FFI code.
- A complete unique-move model for ordinary values.
- Path-complete ownership/escape analysis across all generics, aliases, globals, and calls.
- A real typed scratch/shared region distinction with promotion verbs.
- Whole-program data-race freedom.
- Deterministic cleanup after an isolated actor panic.
- One settled runtime/memory surface; explicit `Sys` and legacy ambient `std.rt` still coexist.

These are tracked as partial or next work in [STATUS.md](STATUS.md), not described as shipped
guarantees.
