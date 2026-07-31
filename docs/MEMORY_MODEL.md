# Zen Memory Model

This is the current memory model implemented by this repository. It is not the
final pointer/borrow/lifetime design.

## The model: explicit capabilities, threaded allocators

Zen's memory model is **explicit**, not ambient. That is two claims, and only the
first is a guarantee:

1. **No implicit allocation.** An allocation is always written at the point it
   happens — it is only ever the job of a call you can see. Nothing allocates as a
   *side effect*: there is no GC, no auto-boxing, no growing an aggregate behind an
   operator or an assignment, and no intrinsic that quietly heap-allocates. This is
   the rule that rejects a case-folding option on `variant_name()` (see
   [SPEC.md](SPEC.md)): folding case needs a fresh string, which would put an
   allocation behind a reflection intrinsic that otherwise returns a borrowed view.
2. **Allocator-explicit by default — a default, not a law.** The real construction
   paths (`new_in`, `from_in`, `make_in`, …) take an `AllocatorBackend` as a parameter, so
   the *choice* of allocator is visible in the signature. But this is not universal:
   a zero-parameter function can reach the process heap (`std.mem.heap.gpa()`,
   `heap_allocator()`), and the convenience wrappers named below do exactly that. Those
   calls still allocate visibly — they just do not let the caller pick where from.

Do not read the pair as "the allocator is always a parameter". It is not.

The outside world enters through a
**capability**: the entry `main = (sys: Sys) i32` receives a `Sys`
(`std.sys.root` — there is no importable `std.sys` module; the directory
`src/std/sys/` holds `root.zen`, `fs.zen`, `os.zen`, `platform.zen`, and
`process.zen`) and hands out narrow capabilities: `sys.heap()` returns the process `Heap`,
while `sys.stdout()` and `sys.stderr()` return `Writer`s. Libraries accept the narrowest
capability they need; generic allocation APIs use `AllocatorBackend`, while values that must
store or pass an allocator use `Allocator`.

> `std.rt` remains an ambient runtime substrate for actors. Default carrying constructors such
> as `vec.new()` capture `heap_allocator()` once; their `_in` variants accept an explicit
> `Allocator`.

String bytes carry their own provenance discipline — static `StringLiteral`,
borrowed NUL-terminated `StringCstr`, general borrowed `StringView`, the
heap-owned growable `String`, the frozen owned `StringConst`
(`src/std/text/string.zen:250`) and the sized-once writable `StringFixed`
(`:235`) — the owned three freed through the allocator the value carries. Six
live spellings, all of them real annotatable types today. The old
`text`/`Cstr`/`str` aliases have been removed, and so have the snake_case
spellings; see the string types section of [SPEC.md](SPEC.md).

That list describes what the compiler does TODAY. The target model — five roles
(`Literal`/`Const`/`Fixed`/growable/`View`) over an element type, with `String` as the `u8` case
of `Vec` — is written down in [string-vec-model.md](string-vec-model.md). The two language
changes that document once listed as gating it are both resolved (slice mutability is DONE;
the allocator-carrying question is DECIDED), so what is left is naming and coverage on the
`Vec` side, not a language change. Read that first; this section records the interim.

The growable `String` and `Vec<T>` remain distinct nominal types with flat public headers, while
their shared allocation, growth, sticky-OOM, freeze and drop mechanics live in `std.mem.buffer`.
The representation and module-boundary rationale is recorded in
[string-vec-model.md](string-vec-model.md#shared-storage-kernel-nominal-container-surfaces).

## Current Rules

> **Enforced vs. convention.** Only two things in this section are checked by a
> machine: the raw-allocation allowlist below (`tests/harness_boundaries.zen`)
> and the local ownership rule further down (the checker). Every sentence in
> this section written with "should" or "by convention" is a **house style rule
> a reviewer enforces, not the compiler** — code that breaks it still compiles.

Allocation is explicit. **(Convention.)** User-facing containers, ownership types, and runtime APIs
should take an allocator (`a: AllocatorBackend` — the implicit bounded generic, equivalently
`<A: AllocatorBackend>(a: MutPtr<A>)`) or use a documented default-allocator convenience wrapper.
Raw `malloc`, `free`, pointer arithmetic, and `@` primitives are the substrate for
bootstrap, FFI boundaries, and low-level std modules.
`std.mem.raw` keeps direct `alloc`/`zeroed` escape hatches, and also exposes
`try_alloc`/`try_zeroed`/`try_of` when allocation failure should stay in the
value flow.

**(Enforced.)** Raw allocation calls are guarded by `tests/harness_boundaries.zen`. Its
`alloc_not_whitelisted` predicate is the authority, and the allowlist for non-test production
`.zen` source is two paths — a bare `malloc`/`calloc`/`realloc`/`free` call may appear only in:

- `src/std/mem/alloc.zen`
- `src/std/mem/raw.zen`

Everything else in that production scan must thread an allocator and call
`acquire`/`resize`/`release` or a higher-level
allocator-aware API. Low-level thread and pool storage and the compiler's bootstrap compatibility
shims route through the canonical heap floor rather than importing raw C allocation names. An
unreadable file fails the scan rather than passing silently.

`Allocator` is the public passable capability and is exactly two machine words:

| field | meaning |
|---|---|
| `state: RawPtr<u8>` | borrowed concrete-backend state |
| `vtable: RawPtr<u8>` | pointer to a durable module-level `AllocatorVTable` |

`AllocatorBackend` is the static contract for concrete implementations. Use `.allocator()`
to obtain the passable value. Custom backends call `allocator_of` with durable state and a
module-level vtable; both must outlive every copied `Allocator`. `Rt` stores this same value.

`RequestArena` is a growable chunk arena created with `request_arena(backing: Allocator)`.
The LSP owns one for request-scoped work; callers pass its `Allocator` capability rather than
coupling library APIs to the concrete arena. `reset()` invalidates one request's allocations and
reuses any fitting retained chunk across varied request shapes; `deinit()` releases all chunks
through the backing allocator. There is no process-global allocator mode, scope flag, or
conditional heap fallback.

`std.mem.arena` is a fixed-capacity arena. `make_in(backing, cap)` acquires its block and
`free_in(backing)` returns it through the same backend. The constructor is named `make_in`
to avoid a flat-namespace collision with `std.text.string.new_in`.

**(Convention.)** Compiler-adjacent AST builders follow the same style where they return
owned slices: `std.internal.ast.dbuf_in` and `derive_accessors_in` place
declaration buffers through a caller allocator, while the short builders use the
documented default allocator helpers.

Owned values are library types:

- `Own<T>` owns a ref-counted heap block and finalizes the payload through `Drop`
  when the last owner is released.
- `Rc<T>` is single-threaded shared ownership.
- `Arc<T>` is atomically reference-counted shared ownership.

Ownership construction is allocator-first and fallible. `src/std/mem/own.zen`
declares exactly **one** constructor —

```
new_in*<T> = (a: AllocatorBackend, x: T) Result<Own<T>, IoError>
```

— so there is no infallible/fallible pair to choose between: `new_in` *is* the
fallible one, and its `Result` has to be opened before you hold an `Own<T>`.
At a fail-fast root that is `.expect(...)`:

```zen
own = std.mem.own
heap = std.mem.heap
h = heap.gpa()
o = own.new_in(h.addr(), own.Resource(id: 7, slot: 0)).expect("own.new_in")
o.release_in(h.addr())
```

Inside a `Result`-returning function, use `or_return()` instead; where allocation
failure is a real branch, match the same value:

```zen
own = std.mem.own
heap = std.mem.heap
h = heap.gpa()
r = own.new_in(h.addr(), own.Resource(id: 7, slot: 0))
r.match({
    .Ok(o)  => { o.release_in(h.addr()) },
    .Err(e) => {},
})
```

The short default-heap forms are intentionally absent for ownership containers.
Use `new_in` plus `release_in`/`drop_in` so the allocator that owns the block is
explicit at both construction and release. **(Convention — nothing rejects a
convenience wrapper if someone adds one; the absence is a design choice, not a
checked rule.)**

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
heap = std.mem.heap
h = heap.gpa()
o = own.new_in(h.addr(), own.Resource(id: 7, slot: 0)).expect("own.new_in")
o.release_in(h.addr())
o.get()          // error[ownership]: use of an owner after it was consumed
```

For a local variable in the same function body:

- `Own<T>.release_in(...)` consumes that local.
- `Rc<T>.drop_in(...)` consumes that local.
- `Arc<T>.drop_in(...)` consumes that local.
- A later value use of the same local is rejected as `error[ownership]`.

Cloning before consuming is still valid because the clone is a different local:

```zen
own = std.mem.own
heap = std.mem.heap
h = heap.gpa()
o = own.new_in(h.addr(), own.Resource(id: 7, slot: 0)).expect("own.new_in")
c = o.clone()
o.release_in(h.addr())
n = c.get().id
c.release_in(h.addr())
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
