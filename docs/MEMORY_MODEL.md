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
   paths (`new_in`, `from_in`, `make_in`, …) take an `Allocator` as a parameter, so
   the *choice* of allocator is visible in the signature. But this is not universal:
   a zero-parameter function can reach the process heap (`std.mem.heap.gpa()`,
   `dyn_heap()`), and the convenience wrappers named below do exactly that. Those
   calls still allocate visibly — they just do not let the caller pick where from.

Do not read the pair as "the allocator is always a parameter". It is not.

The outside world enters through a
**capability**: the entry `main = (sys: Sys) i32` receives a `Sys`
(`std.sys.root` — there is no importable `std.sys` module; the directory
`src/std/sys/` holds `root.zen`, `fs.zen`, `os.zen`, `platform.zen`, and
`process.zen`) and hands out narrow capabilities, notably `sys.heap()` (the process
`Allocator`) and `sys.stdout()`/`sys.stderr()` (`Writer`s). Libraries take the
narrowest capability they need (an `Allocator`, a `Writer`), which is the same
discipline one level up from threading `a: Allocator` allocators through container
and ownership APIs.

> **The ambient runtime is not the model.** `std.rt` is a live thread-local `Rt`
> substrate used by pooled actors, but the shipped, documented model is the explicit one
> above. The A-wrapper convenience constructors (`vec.new`, `set.new`, `hmap.new`,
> and their `from`/`from` variants) no longer draw from `std.rt` — they capture the
> process heap once via `dyn_heap()` at construction and store that `DynAlloc` for
> the container's lifetime. `new_in`/`from_in` remain the explicit real paths.
> **These wrappers are the named exception to rule 2 above** — the allocation is
> still written where it happens (`vec.new()` is a constructor; rule 1 holds), but
> the allocator is not a parameter.

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
should take an allocator (`a: Allocator` — the implicit bounded generic, equivalently
`<A: Allocator>(a: MutPtr<A>)`) or use a documented default-allocator convenience wrapper.
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

`Allocator` and `DynAlloc` are two representations of that one capability, not two allocators:
`Allocator` is a statically dispatched borrowed trait parameter; `DynAlloc` is its erased, storable
value form for an owner that must remember where its bytes came from. `Rt` stores this same
`DynAlloc` rather than declaring a second allocator vtable.

Arena backing storage follows the same rule. `arena.make_in(backing, cap)` and
`Arena.free_in(backing)` acquire and release the arena's backing block through a
caller allocator. `Arena.free` is **not** a default-heap convenience path — it is a
one-line forwarder to `free_in` and takes the backing allocator as a required
parameter (`free<A: Allocator> = (a: MutPtr<Arena>, backing: MutPtr<A>) void`,
`src/std/mem/arena.zen:32`). There is no way to free an arena without naming the
allocator its block came from.

The arena constructor is spelled `make_in`, not `new_in`, on purpose: Zen's
namespace is flat, so two modules that both export a top-level `new_in` cannot
reach one program. `std.text.string` already owns `new_in`, and a String builder
sits beside the arena often enough (anything pulling in `std.concurrent.actor`
drags the arena along) that the arena took the distinct name.

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
new_in*<T> = (a: Allocator, x: T) Result<Own<T>, IoError>
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
