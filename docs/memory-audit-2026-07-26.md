> **Historical audit (2026-07-26).** Names such as dyn_from, heap_scope, and hs_on below describe the pre-refactor tree. The current API is documented in MEMORY_MODEL.md.

# Zen memory audit — 2026-07-26

> Follow-up (2026-07-30): the experimental `std.mem.trace`, `std.scope`,
> `std.concurrent.sched`, `std.concurrent.atomic`, `std.concurrent.cown`, and unused `std.sys.path`
> modules were retired. References below are preserved as historical audit evidence, not current APIs.

**Scope.** Every memory surface in the tree: allocators, pointer kinds, raw operations, reference
counting, cycle collection, the ambient runtime, the actor memory model, and what the docs promise
versus what the compiler enforces.

**Baseline.** `origin/main` = `6b60d5b`. Six parallel audit lanes.

**Method.** Claims here were established by *running programs* — building the compiler, compiling
probe programs, and checking behaviour under ASAN — not by reading source. Where a claim is
enforcement-related, it was established by **mutating the tree and watching the gate go red**.
Every row is marked:

- **[V]** — verified directly by the author of this document, re-running the probe.
- **[L]** — reported by an audit lane with a stated repro, not independently re-run.
- **[U]** — unverified / stated as suspicion by the lane that raised it.

**Correction protocol.** Two lane findings were **wrong** and are excluded or restated below; one
of my own earlier statements was understated and is corrected. See *Appendix B*. A lane finding is
not a fact.

---

## 1. Verdict

Zen's memory story is **not one model with gaps. It is four half-built models sharing a namespace.**

1. An **explicit allocator** model (Zig-shaped). Real, dominant, works — 1,076 threaded-allocator
   signatures in the compiler alone.
2. An **ambient runtime** model (dynamic scoping). Built, then deliberately retreated from; now has
   **zero production call sites** outside the actor pool's per-behavior injection.
3. An **ownership/capability** model (Rust/Pony-shaped). Real diagnostics, genuinely good deep
   reachability — but keyed on *type shape* and *method name*, so it is unsound by construction.
4. A **tracing/refcount** model (`Rc`/`Arc`/`Traced`, ORC-shaped). `Arc` is production-solid; the
   cycle collector was diverging on the one case it exists for until today.

The single most useful thing in this audit is not any individual bug. It is that **the escape
hatches are the most-used primitives in the language**: `offset()` (238 uses) erases pointer kind
and pointee type; `slice()` (217 uses) builds a fat pointer with an unchecked length;
`RawPtr<u8>` (485 uses) satisfies every pointer type. Meanwhile the *elaborate* machinery —
Stage-3 nullability with `assert_nonnull` — guards **14** sites and has **one** real caller.

We are paying for precision where it does not matter and taking it on faith where it does.

---

## 2. Inventory

### 2.1 Allocators — 25 distinct surfaces

| Surface | Declared | Real users | Verdict |
|---|---|---|---|
| `Allocator` trait | `mem/alloc.zen:12` | 44 std + 60 compiler modules | **KEEP** — the one true interface |
| `Malloc` | `alloc.zen:20` | 1,317 `MutPtr<Malloc>` in `src/compiler` | **MERGE into `Heap`** |
| `Heap` | `alloc.zen:17` | 8 std, 7 examples, 0 compiler | **KEEP as the one name** |
| `DynAlloc` | `alloc.zen:314` | 4 std modules | **KEEP** — needs the missing ctor |
| `Rt` (allocator half) | `rt.zen` | stores one `DynAlloc` | **DONE — duplicate vtable removed** |
| `Arena` | `arena.zen:6` | `runtime.zen`, `pool.zen`, `pool_actor.zen` | **KEEP** |
| `SyncArena`/`AsyncArena` | `runtime.zen:12,19` | `scope.zen` + fixtures | **MERGE into `Arena`** |
| `Scope<A>` | `scope.zen:16` | **0** in `src/std`, `src/compiler`, `examples` | **DELETE or adopt** |
| `Buf2`/`Buf3` + `try_acquire2/3` | `alloc.zen:238,242` | 7 call sites each | **KEEP** (a lane initially guessed dead — wrong) |
| `genc.acquire` / `genc.resize` | `genc.zen:45,46` | bootstrap compatibility; no direct seed calls | **KEEP** — raw bodies replaced by `heap_request_acquire` / `heap_resize` routing |
| `rt.dyn_of_rt` / `rt.dyn_current` | removed | 0 | **DONE** |
| debug / GPA / counting allocator | — | **does not exist** | **ADD** |

### 2.2 The four-representations problem  **[V]**

`Allocator`, `DynAlloc`, `Rt`, and `Heap`/`Malloc` are **one concept at two levels of erasure,
spelled four times**.

`DynAlloc` and `Rt` used to repeat the same four fields under different field-name prefixes. This
part is resolved: `Rt` now stores one `DynAlloc`, and `Rt.allocator()` exposes the narrow capability.

`Heap` and `Malloc` are both `{_: i32}` and differ in exactly one line — and **the names are
backwards**: `Malloc` is the LSP request-scoped one, `Heap` is the durable one.

**The load-bearing conversion gap is resolved.** `dyn_from(a)` erases a caller allocator into the
storable value used by explicit container constructors, and `Rt.allocator()` exposes an already-erased
runtime allocator without rebuilding its vtable. The old private zero-caller helpers were removed.

### 2.3 `heap.gpa()` is a promise the code does not keep  **[V]**

```zen
gpa* = () Heap { Heap(_: 0) }
```

The module header says *"Mirrors Zig: `std.heap.page_allocator`"*. But in Zig,
`GeneralPurposeAllocator` **is the checking allocator** — leak detection, double-free detection,
use-after-free detection. Ours borrows the name and does none of it. In Zig terms this is
`c_allocator`.

**There is no debug allocator anywhere in `src/`.** Meanwhile **26 test files hand-roll their own**
`Counting`/`Limit` allocators (57 lines of duplicated declarations). That is demand, unmet, in
writing.

### 2.4 Fallibility — three incompatible stories in one module  **[L]**

| Story | Entry points | Call sites |
|---|---|---|
| `Result<_, IoError>` (`try_acquire`, `try_resize`, `try_acquire2/3`, `make_in`) | 9 | ~60 std, 7 compiler |
| Raw nullable pointer, **no error** (`acquire`, `heap_acquire`, `rt.alloc`, `raw.alloc`, `Arena.bump`) | 15 | 89 compiler, 32 std |
| Panic (`zen__salloc` on escaping slice literals) | 1 implicit | ubiquitous |

Of ~32 raw `.acquire(` results in `src/std`, **exactly one** is null-checked (`build.zen:48`). The
same module ships a careful all-or-nothing rollback combinator *and* eight consecutive unchecked
acquires in `str.zen`.

---

## 3. The pointer and raw layer

### 3.1 What genuinely works  **[V]**

The read-only `Ptr<T>` discipline is real:

| Probe | Result |
|---|---|
| `p: Ptr<i64>; p.store(99)` | `error[ptr-write]` |
| `q: MutPtr<i64> = p` | `error[assign-fit]` |
| `poke = (c: Ptr<Cell>) void { c.v = 7 }` | `error[ptr-write]` |
| `s: [i64] = slice(p, 1)` from a `Ptr` | `error[ptr-write]` — `slice` is in the write gate |

That last row matters: someone thought about the laundering route through `slice` and closed it.

### 3.2 …and the one-token bypass  **[V]**

```zen
p: Ptr<i64> = x.addr()
p.store(99)              // error[ptr-write]
p.offset(0).store(99)    // compiles, prints 99
```

`offset` is missing from the intrinsic return-type table (`check.zen:752-793`) and from
`is_write_intrinsic` (`validate/util.zen:359-366`). It is a universal `T* → anything` cast that
also erases the pointee type. **238 uses.**

Every `ptr-write` guarantee in the language is one `.offset(0)` away from void. This is the
highest value-per-line fix in this document.

### 3.3 `slice()` — unchecked fat-pointer construction  **[V]**

`slice(p, n)` lowers to a bare `(zslice){.ptr=…,.len=…}` with no validation, and `zen__idx` then
bounds-checks against **the number the programmer typed**.

ASAN, `slice(p, 1000)` over a 16-byte block: `heap-buffer-overflow WRITE of size 8`. Program
exits 0. `slice(p, 0-5)` is also accepted and yields `len == -5`.

Call-site classification (217 sites): **114 structurally safe** (empty, or allocation and length
paired in one expression), **100 trust-me (46%)**.

The lane machine-checked every alloc-inline site for element-type/size agreement and found **zero
real mismatches** — the sizing discipline is genuinely good. One is fragile and worth noting:
`parse_match.zen:535` declares `[StringView]` but sizes with `sizeof(NameSlot)`; correct today,
silently under-allocates the moment `NameSlot` gains a field. That is exactly the shape of the
`int32_t`-array-read-as-`int64_t` bug fixed in PR #699.

### 3.4 Other confirmed holes

| Finding | Status |
|---|---|
| `store(p, v)` does not check `v` against the pointee — `store(MutPtr<u8>, 999999)` prints `63` | **[L]** |
| `RawPtr<u8>` satisfies *any* pointer type (`raw_floor_fits`); ASAN-verified struct punning | **[L]** |
| Stage-3 nullability guards 14 sites; `assert_nonnull` has **1** real caller | **[L]** |
| `MutPtr` aliasing is entirely unrestricted — it means "writable", never "unique" | **[L]** |

### 3.5 Hand-rolled block layouts  **[L]**

**51 literal-offset sites across 8 files, ≥11 distinct unchecked ABIs.** `val_slot`/`rc_block_new_in`
(`alloc.zen:211-224`) already unify `Rc`/`Arc`/`Own` correctly — but `trace.zen` keeps its **own
parallel copy** of the block-header concept (20 literal offsets, 18 raw `load_i64`/`store_i64`)
instead of extending it.

### 3.6 `Drop` is declared twice, and one declaration is inert  **[V]**

`own.zen:14` (`Drop*`, exported) and `trace.zen:127` (`Drop`, unexported), identical bodies.

This is **not** a C-symbol collision — a trait name emits no C symbol, and impls mangle per
implementing type (`impl_Drop_Resource_drop`, `impl_Drop_Node_drop`). Importing both compiles clean.

But the mutation test is decisive, and stronger than "they might diverge". Diverging **own.zen's**
`Drop*` breaks conformance in *both* modules:

```
error[conformance]: ./src/std/mem/own.zen:49     Resource.impl(Drop, {
error[conformance]: ./src/std/mem/trace.zen:246  Node.impl(Drop, {
```

Diverging **trace.zen's** copy changes nothing. So they resolve to **one name, own.zen's wins, and
trace.zen's declaration is already dead** — a local edit in `own.zen` silently redefines the trait
`trace.zen` and `cown.zen` conform to.

Other duplicate top-level names: **40** of 4,248. Memory-relevant: `alloc`×2, `release`×2,
`resize`×2, `of`×6, `new_in`×8, and `set`×2 with *different signatures* (`raw.zen:32` vs
`internal/ast.zen:69`) — currently unexercisable only because `std.internal.ast` does not compile
standalone (`error[struct-field]: struct 'Func' has no field 'ast__ret'` — a namespace-prefixing
bug worth handing to whoever owns namespacing). **[L]**

---

## 4. Reclamation

| Piece | State |
|---|---|
| `Rc<T>` | **Verified working** as a manual-discipline primitive; ASAN/LSan/UBSan clean **[L]** |
| `Arc<T>` | **Verified working, genuinely atomic** — 8 threads × 200k clone/drop → count exactly 1 **[L]** |
| `Own<T>` + `Drop` | Works; **1** real user (`cown.zen`) **[L]** |
| `Arena` | Works, and is the de-facto strategy **[L]** |
| `Traced<T>` cycle collector | **Was diverging on any surviving cycle — fixed today, PR #701** **[V]** |
| `Resource` | **0** non-test users — a fixture shipping in the stdlib **[L]** |
| ORC | **Does not exist.** No deferred RC, no cycle-detector actor, no message RC protocol **[L]** |

### 4.1 The cycle collector  **[V]**

`trace.zen` is a faithful Bacon-Rajan skeleton. It worked on every all-garbage graph: 2-cycles,
self-cycles, transitive discovery through a 4-cycle with one root, two disjoint cycles.

It **diverged into unbounded recursion on any cycle that survives** — i.e. any cycle with a live
external reference. `cc_scan_black` set BLACK and re-traced unconditionally, so a block on a cycle
re-entered through its own back edge forever.

That is *the case trial deletion exists for*. All three existing fixtures collect only all-garbage
graphs, which reach `gather` and never run the restore path — so it had zero coverage.

Fixed in **PR #701** — open, CI-green, **not merged** (one colour guard) with a fixture covering both directions. Teeth-checked:
without the guard the fixture exits 134 with a segfault.

### 4.2 Deeper limits a guard does not fix  **[L]**

- **`Traced<T>` is really `Traced<Node>`** — `blk_trace`/`blk_drop` hardcode the payload type. Any
  other `T` is type-confused (ASAN heap-buffer-overflow inside `impl_Trace_Node_trace`). `Node` has
  exactly one child pointer, so no multi-child graphs.
- **`Traced` has no `dec`.** `tracked_in` starts the count at 0; only `set_kid` increments. External
  liveness is inexpressible except by an `inc` you can never undo, and candidates are never
  auto-registered on decrement-not-to-zero. `trace.zen:78` already admits this.
- **Single-threaded only** — `roots`/`white`/`tracked_blocks` are plain process globals.
- The ownership checker covers `Own`/`Rc`/`Arc`; **`Traced` is not covered** (a forgotten `Traced`
  checks clean where a forgotten `Rc` is `error[leak]`).

### 4.3 Distance to ORC  **[L]**

| Ingredient | Status |
|---|---|
| seq-cst atomic refcount | **Have it**, contention-verified |
| Actor lifetime by RC | **Have it** — pool allocates actors as `Arc<PoolActor>` |
| Per-actor allocation context | **Partial** — a per-actor *allocator*, not a per-actor object heap |
| Trial-deletion algorithm | **Now correct** for single-threaded graphs of one payload type |
| Deferred cross-actor count updates | **Nothing** |
| Message-passing RC protocol | **Nothing** — messages are hand-freed malloc boxes |
| Cycle detector as an actor | **No** — synchronous, global state |
| Per-payload `Trace`/`Drop` bridges | **Missing** — needs codegen |

The done half is the boring half. Calling the collector "a large fraction of ORC" overstates it: it
is a large fraction of the *cycle-collection algorithm*, which in Pony sits behind a distributed
deferred-RC protocol that does not exist here in any form.

---

## 5. Actors and the capability question

**The engine is real and better than the docs suggest.** A genuine pthreads scheduler:
`workers_busy=4`, and 200,000 messages to one actor from 8 workers landed **exactly**, so
run-to-completion and one-worker-per-actor mutual exclusion hold under real contention. Plus
Arc-refcounted actor lifetime, per-actor panic isolation, supervision with restart policies,
back-pressure as a value, dead-letter counting. **[L]**

**`Own<T>` is NOT a working `iso`.** ~~It was described here as "a real, working `iso` move — the one
Pony capability Zen actually has."~~ **That claim was false and is retracted.** Sending an `Own<T>`
does kill the sender's *binding* — but it is affine in the binding, not in the object:

```zen
o = a.new_in(Cell(v: 1)).expect("own")
alias = o.ptr()      // public, zero-ceremony MutPtr<T> extraction
o.release_in(a)       // owner consumed, block freed
alias.v = 777         // zen check: ok  →  prints 777
```

`own.zen:20-25` exposes `ptr()`/`val()`/`get()` and a `clone()` that refcounts the "unique" owner,
and `is_consume_method` (`ownership.zen:146`) knows only `release`/`release_in`/`drop`/`drop_in` —
none of the extractors. **[V]**

This inverts §5's conclusion. The argument was "we have top-level `iso`, we lack viewpoint
adaptation, therefore caps are a large commitment." What is true is that Zen has **no** working
`iso` — which makes the distance to caps *larger*, and the distance to a *sound* send-check much
**smaller**: sealing `Own` plus narrowing the accepted set is days, not quarters.

### 5.1 Pony-semantics checklist  **[L]**

| Property | Verdict |
|---|---|
| Async, run-to-completion, no preemption | **Holds** — verified under contention |
| Causal per-pair ordering | **Holds** by construction; no fixture asserts it |
| No function coloring | **Holds** |
| Private actor state | **Doesn't hold** — `pa.actor_state(h)` hands the spawner a live `MutPtr` into a running actor |
| No shared mutable state | **Doesn't hold** — five independent bypasses |
| Actor-local heap | **Partial** — per-actor `Rt`, but `spawn_actor_heap` gives every actor the same process heap |

### 5.2 The send-check is unsound  **[L]**

There *is* a capability lattice, explicitly Pony-shaped (`ownership.zen:766-796`): `md_owned`(iso),
`md_frozen`(val), `md_mut`(ref), `md_read`(box), with `sendable = owned || frozen`. The deep
reachability walk is genuinely good — it descends struct fields, enum payloads, slice elements and
generic args.

**The problem is what the lattice is a function of.** `mode_of(decls, t)` is a pure function of a
*type's shape*. Pony's `val` is not a shape — it is the global claim that no `ref` alias exists
anywhere. Zen has no `recover`, no freeze, and no consume for anything but `Own<T>`.

Five programs that compile clean and race for real on the parallel path:

| Shape | Result |
|---|---|
| `Ptr<T>` sent while sender keeps a `MutPtr<T>` | receiver observed the sender's post-send write |
| `RawPtr<u8>` — "frozen" because `u8` reaches no `MutPtr`, yet it has `store_i64` | both wrote |
| mutable slice `[i64]` | both wrote |
| `Arena` value | both bump-allocate from one arena, unsynchronized |
| `MutPtr<T>` boxed through the raw `ref_send` floor | both mutated — **legitimate hatch**, visible at the point of danger |
| **generic forwarder** `fwd<T> = (p, h, m: T) void { p.send(h, m) }` | **`ok`, compiles, races — while the byte-identical CONCRETE forwarder is correctly rejected** **[L]** |

Row 1 deserves emphasis: **it is the remedy the compiler itself recommends.** The hint says *"send
a readonly `Ptr<T>` (a `frozen` value: deeply immutable, freely aliasable)"*. It is not deeply
immutable, and no operation in the language makes it so.

### 5.3 Can we do ORC without reference capabilities?

**No — by definition, not by difficulty.** Every ORC rule is keyed on the capability of the
reference being traced: `iso` transfers its subgraph and its RC with it; `val` is shared so the
sender sends an RC increment; `tag` is counted but not traced; `ref`/`box` never cross. Delete the
caps and ORC has no basis to decide whether a pointer in a message needs an RC message, a trace, or
nothing. **The reference capability is the input to the algorithm.**

The commitment, honestly: caps must become per-*binding* and inferred, not per-*type* (this touches
`infer_expr` and everything that threads a type); a `recover`/freeze construct, or `val` stays a
lie; viewpoint adaptation, without which `iso` collapses to the top-level-only wrapper `Own<T>`
already is; and — the one that collides hardest with the rest of Zen — **ambient raw-pointer
authority must go behind caps.** Pony has no raw pointers in ordinary code. Zen's entire actor
stdlib is raw pointers.

---

## 6. Spec drift

`docs/STATUS.md` and the `validate/*.zen` source comments are **already honest**. The drift is
entirely in the front door — `README.md` and `docs/SPEC.md` — which state guarantees without the
qualifiers the implementers wrote down four levels deeper.

| Claim | Status |
|---|---|
| "touching a pointer after `free` is `error[ownership]` at compile time" (`README:128`) | **PARTIAL — the strongest overclaim.** Holds for bare locals. Copy the pointer **once** into a struct field, slice element, or enum payload and tracking vanishes. The lane ran an accepted program that aborts with glibc `free(): double free detected`. |
| interprocedural free | **PARTIAL** — summarized only for `Own`/`Rc`/`Arc` params. A helper freeing a plain `RawPtr`, called twice, checks **ok**. This is the stdlib's own `Vec.free` idiom. |
| "an out-of-range index panics. Not UB." (`README:112`) | **PARTIAL — bypassable in one line** via `slice(p, n)`. |
| "no hidden heap" (`README:128`, `MEMORY_MODEL:8`) | **FALSE.** A zero-parameter function can call `halloc.gpa()` and allocate. `MEMORY_MODEL:22-24` contradicts itself two paragraphs later. |
| `main = (sys: Sys) i32` as *the* entry | **NOT ENFORCED** — both shapes legal; all 15 examples use the other one. |
| `arena.new_in` / `try_new_in` (`MEMORY_MODEL:47`, `SPEC:742`) | **FALSE — the API does not exist.** It is `make_in`, and `arena.zen:34-38` explains why it was renamed. Two docs name a function that was never followed. |
| arena lifetimes "follow the same rule" | **NOT ENFORCED** — use-after-`reset` checks ok. |
| "A send moves ownership (checker-enforced)" | **ENFORCED on the real API, but name-shaped.** Rename the verb `send`→`tell` and every send check silently disappears. |
| "`Ptr<T>` sendable only when `T` is deeply immutable" (`SPEC:848`) | **FULLY ENFORCED** within the name-gated surface — a real deep check |
| write through `Ptr<T>` is `error[ptr-write]` | **FULLY ENFORCED** — except `.offset()`, §3.2 |
| div-by-zero, null-deref panics | **FULLY ENFORCED**, verified at runtime |

**`STATUS.md:135-141` lists seven P0 memory-corruption defects in shipped code.** None are reachable
from README or MEMORY_MODEL. A reader who stops at README believes memory safety is solved.

### 6.1 Rules with zero tests  **[L]**

Each will regress silently: raw pointer into struct field / slice element / enum payload (the
`Own<T>` equivalents *are* tested exhaustively, which makes the gap look like coverage);
interprocedural raw double-free; `slice(p, n)` length validity; self out-param store escape; owner
moved into a struct field then leaked; arena use-after-reset; non-owner leaks; and —
highest-value — **no test asserts the name-shape fragility itself**, so nobody would learn if
renaming `send` silently dropped the check.

---

## 7. Consolidation proposal

Ordered by value-per-risk. Steps 1–4 are independently landable.

**1. Close the `offset()` laundering hole.** Give `offset` an entry in `infer_call` preserving kind
and pointee, and add it to `is_write_intrinsic`. *Small, highest value/LOC here.* Risk: 238 sites
rely on it being untyped — keep `RawPtr<u8>.offset` byte-typed and tighten only the typed kinds.

**2. Make `store` check its value** against the pointee. Will surface latent truncations.

**3. Keep bootstrap compatibility on the canonical floor; delete genuinely dead surfaces.**
`genc.acquire`/`genc.resize` remain as compatibility shims for the stripped bootstrap closure, but
their raw allocation bodies are gone: they route through `heap_request_acquire` / `heap_resize`.
Delete `Resource` (move it to the test tree) and **`trace.zen`'s inert `Drop`** — import that from
`std.mem.own` instead.

**4. Add `std.mem.debug`** — `Counting` and `Limit` implementing `Allocator`, plus poisoning,
double-free detection, and a leak report. Then migrate the 26 fixtures that hand-roll it.
*Flat-namespace hazard:* those names already exist as top-level names in 26 test programs; migrate
declaration-and-import together, file by file.

> **Correction.** An earlier draft called this "the correct answer to §5.2". It is not. A
> counting/poisoning allocator catches leaks, double-frees and use-after-free, and catches
> **exactly zero data races**. Every failure in §5.2 is a race. The runtime tool for that class is
> TSan; the static tool is narrowing `mode_sendable`. `std.mem.debug` is well-motivated on its own
> terms — 26 hand-rolled counting allocators is real demand — and should be sold as what it is.

**5. Rename `slice()` → `slice_unchecked` and add checked constructors.** `[T].sub(lo,hi)` for the
20 sub-span sites and `[T].take(n)` for the 38 narrowing sites are pure wins — the length is
derivable. That leaves ~42 genuinely-raw field-ptr sites. **The rename converts an invisible 46%
into a greppable 19%** and is the highest-leverage single step in this document.

**6. Collapse the allocator representations.** `Rt{alloc: DynAlloc, ready}`; add the missing
`dyn_of_alloc<A>`; fix the false comment at `vec.zen:286`. Then merge `Malloc` into `Heap` —
1,601 occurrences, **highest risk**, own branch, seed regenerated *after* the rename and committed
last.

**7. One block-header module.** Extend `val_slot`/`rc_block_new_in` with a `[count|color|value]`
variant and delete `trace.zen`'s parallel copy; give the remaining hand-rolled layouts named
accessors. 51 literal offsets → ~11 named ABIs.

**8. Fix the docs by consolidating *downward*.** `STATUS.md` and the source comments are already
honest; README and SPEC are not. **One rule:** every safety sentence must name (a) the diagnostic
kind it produces, (b) the syntactic scope it covers, and (c) one shape it does not catch. If a
sentence cannot carry all three, it is a *direction*, not a guarantee. Delete "no hidden heap". Fix
`arena.new_in`. Link the P0 table from `MEMORY_MODEL.md`.

**9. Decide the `RawPtr` question and stop paying for the half we don't use.** Either commit to
typed `RawPtr<T>` (large, invasive, and Stage-3 nullability starts earning its keep) or accept
`RawPtr<u8>` as the FFI floor and **delete the Stage-3 nullability machinery** — one caller. The
evidence says the design already chose the second; the code has not caught up.

**Not recommended: extending the ownership checker interprocedurally.** That is building a borrow
checker, and it is the wrong axis for a language whose stated direction is Zig-style explicit
allocation plus actors. The static checker should stay a cheap local net that never over-rejects;
runtime catching belongs in step 4.

---

## 8. Found and fixed during this audit — **OPEN PRs, not on `main`**

> ⚠️ **THIS SECTION IS STALE (as of 2026-07-27).** All three PRs have since **merged**: #699 as
> `b311d75`, #700 as `5378353`, #701 as `e813d8f`. The paragraph and table below are preserved as
> the audit author wrote them on 2026-07-26 and are *not* rewritten; read them as a snapshot of that
> day, not as current status.

> **Status, stated precisely** *(as of 2026-07-26; superseded — see above)*: all three are **open, CI-green, and NOT merged**. `origin/main` is
> `6b60d5b` (PR #698). A reader who checks out `main` does **not** have these fixes. An earlier
> draft of this section said "fixed today", which was exactly the failure mode Appendix A and
> Appendix B exist to prevent; the panel caught it.

| PR (open) | Fix |
|---|---|
| **#699** | Slice-literal element types — variadic packs read at wrong stride, **and** struct-field inits, an ASAN-confirmed heap-buffer-overflow (`Holder(xs:[1,2,3])` for `xs:[i64]` emitted a 12-byte `int32_t` array read with `sizeof(int64_t)`; `.len` was correct so the bounds check passed) |
| **#700** | Indexed and loop-element receivers now light-type, so reflection expands — `cs[0].variant_name()` passed `zen check` then failed at link |
| **#701** | `ScanBlack` colour guard — the cycle collector diverged on any surviving cycle |

All three are teeth-checked: the regression test fails on the pre-fix compiler and passes after.

---

## 9. What the panel found that this audit missed

Four judges reviewed the above. These are their findings, verified, ordered by consequence. They
are more important than most of §7, and several **correct** it.

### 9.1 `Allocator` returns a pointer, not a slice — the root cause under §3.3  **[V]**

```zen
Allocator: { acquire: (MutPtr<Self>, i64) RawPtr<u8>, release: (MutPtr<Self>, RawPtr<u8>) void }
```

Length is discarded at `acquire`, and `release` never learns a size. **That is why `slice()` has to
be trusted** — the length is gone by the time anyone builds a fat pointer. Zig's `alloc(T, n) ![]T`
/ `free(slice)` is exactly the design that makes this bug class unrepresentable.

It also means **§7 step 4 cannot be built as written**: with no size at `release`, a debug allocator
cannot poison a freed block, detect size-mismatched free, or report bytes leaked, without an
address-keyed side table nobody has costed.

**And the tree already contains the fix.** `genc.zen:25`:

```zen
cbuf*<T> = (a: MutPtr<Malloc>, n: i64) [T] { slice(a.acquire(n * sizeof(T)), n) }
```

Length and element size derive from one `T`; a mismatch is unrepresentable. Generalise it over the
allocator as `alloc_n<T>() Result<[T], IoError>` with a **checked multiply** — which also fixes the
`STATUS.md:136` overflow-to-`Ok(null)` defect at all 68 alloc-paired sites at once — and migrate.
That is §7 step 5 done properly; the rename is the residual 20%, not the step.

### 9.2 There is no `defer`  **[V]**

Not a keyword; the construct does not exist. Zig's explicit-allocator model is survivable *only*
because `defer allocator.free(x)` sits on the line after the allocation.

Its absence is the reason an ownership checker exists at all, the reason `error[leak]` is needed,
and the reason §2.4 counts 89 unchecked `acquire` sites: **the correct rollback is too verbose to
write, so nobody writes it.** `alloc.zen` shipping a careful all-or-nothing rollback combinator
*and* eight consecutive unchecked acquires in `str.zen` is not a discipline failure — it is a
missing language feature showing through.

### 9.3 Every ownership guarantee is a `strcmp` — and no step fixed it  **[V]**

`ownership.zen:149,249,374` key on `sx_named("release", …)`, `sx_named("send", …)`,
`sx_named("free", …)`. §6 observed that renaming the verb deletes the check and §6.1 observed that
no test asserts it — and then §7 proposed nothing.

**This is a P0.** The next namespacing PR that mangles names silently deletes the entire ownership
checker with green CI. The fix is bounded and stays local — resolve the call to its decl and key on
**decl identity** (*this is `Allocator.release`; this parameter is declared `Own<T>`*) rather than
on `c.fn`'s spelling. The impl index and module signatures already exist. This is not the borrow
checker §7 rightly refuses.

### 9.4 The compiler's dominant allocator is ambient  **[V]**

§1 celebrates that the ambient-runtime model was retreated from. Meanwhile `Malloc.acquire` routes
on **`hs_on`, a process-global mutable bool** (`alloc.zen:92`), and `heap_scope_begin`/`end` have
**exactly two call sites in the entire tree** — `lsp.zen:974` and `:979`.

**1,343 `MutPtr<Malloc>` occurrences exist to serve two lines of LSP**, via dynamic scoping with the
serial numbers filed off. That reframes §7 step 6 entirely: merging the two type names *preserves*
the mechanism. Delete `hs_on`, give the LSP a real `Arena` per request, and `Heap`/`Malloc` collapse
for free.

### 9.5 Step 1's mechanism was misdiagnosed, and half of it is wrong  **[V]**

The stated risk — "238 sites rely on `offset` being untyped, so keep `RawPtr<u8>.offset` byte-typed"
— is not the axis that matters. A judge patched it and the unconditional fix dies on the first file:

```
./src/std/mem/alloc.zen:95: error[return-fit]: expected `RawPtr<u8>`, got `i64`
  hs_next = (c: RawPtr<u8>) RawPtr<u8> { load_i64(c).offset(0) }
```

**`offset` is doing double duty as the int→pointer cast**, because Zen deliberately has no `as`
keyword. The split is pointer-vs-not-a-pointer, not RawPtr-vs-typed. With that one guard the fix is
~7 lines and the whole-tree error diff is **zero**.

But it is **not** semantics-free: a byte-diff of emitted C shows `load(buf.offset(i))` now typing as
`u8`, so `(b - '0').to_i64()` wraps in `u8` instead of promoting to int (`lsp.zen:887`). Benign
there, invisible to `zen check` everywhere. **The migration gate must be a byte-diff of emitted C,
not an error count.**

And **cut the `is_write_intrinsic` half** — it would reject *reads*. `read2 = (p: Ptr<i64>) i64 {
load(p.offset(1)) }` checks ok today and would start failing; `cown.zen:10` is exactly that shape.
Once `offset` preserves the kind, the trailing `.store` is caught by the existing rule.

### 9.6 Smaller, all confirmed

- **No alignment, anywhere.** `acquire(n: i64)` has no alignment parameter; `Arena.bump` hardcodes
  8-byte rounding. Every arena allocation is 8-aligned by accident of malloc's 16-byte base. §7
  step 7 cannot be written correctly without this.
- **No sanitizer gate in CI.** Every enforcement claim in this document was established by hand
  under ASAN, and nothing in `bootstrap/Makefile` or the workflow builds the corpus with
  `-fsanitize=address,undefined`. For a project whose safety model is now *runtime catching*, that
  is one Makefile target that catches more than steps 1, 2, 5 and 7 combined.
- **A debug allocator no test uses by default is a museum piece.** Zig's leverage is not that
  `GeneralPurposeAllocator` exists — it is that `std.testing.allocator` is the default in every test
  and fails the test on leak.
- **Fallibility is undecided, not undisciplined.** Until `acquire` stops returning a nullable
  pointer, "89 unchecked sites" is the API working as designed.

### 9.7 Revised order of work

Synthesising the panel against §7:

1. **Docs** (§7 step 8) — one hour, zero risk, largest live falsehood in the repo. Was ranked 8th.
2. **ASAN + UBSan CI target** — the substrate every later step is verified against.
3. **Delete dead surfaces** (step 3), then **steps 1+2 merged**, gated on a byte-diff of emitted C.
4. **De-name the ownership checker** (§9.3) — protects everything else on the list.
5. **Fix the `Allocator` trait** (§9.1): return `[T]`, take `[T]` in `release`, add alignment and
   checked size arithmetic; land `alloc_n<T>`; migrate the 68 sites. Subsumes most of step 7.
6. **`defer`** (§9.2) — language work, start in parallel; everything above patches around it.
7. **Debug allocator**, now that `release` carries sizes, wired as the harness default.
8. **Delete `hs_on`, thread `DynAlloc`** — `Heap`/`Malloc` then collapse for free (§9.4).
9. Step 9, then the `slice_unchecked` rename as cleanup.

---

## Appendix A — the standing lesson

Three of the bugs fixed today, and most of the holes catalogued above, share one root cause:
**a walker or a table that silently does nothing for a case nobody wrote a test for.**
`resolve_slicelit` re-inferring a type that a lowering pass had already set; `light_ty`'s
`_ => tvoid()` swallowing `.Index`; `cc_scan_black` re-tracing a colour it had already painted;
`offset` missing from two intrinsic tables.

The gate that catches this class is not review. It is **mutate the tree and watch the gate go red** —
which is how every enforcement claim in this document was established, and how the `Drop` finding
went from "two identical declarations" to "one declaration is already inert."

## Appendix B — corrections

Recorded because a lane report is not a fact, and this document should model the standard it asks for.

1. **`docs/two-memory-design.md` link in a user-facing diagnostic.** `validate/args.zen`'s
   `sx_hint` ships *"see docs/two-memory-design.md"* — a file that no longer exists. Real, small,
   unfixed. **[L]**
2. **A lane reported `raw.copy` as dead and unexported → delete.** It read a working checkout that
   was **73 commits behind** `origin/main`. On current main it is `copy*`, exported, part of a
   deliberate new bulk-byte API with `move*`/`set*`/`compare*` and documented overlap semantics.
   Recommendation withdrawn. Two lanes were re-run against a fresh tree.
3. **A lane reported `tests/fixtures/matrix/expected.tsv` does not exist.** It does.
4. **A lane reported `Buf2`/`Buf3`/`try_acquire2/3` as probably dead.** They have 7 real call sites
   each. Kept.
5. **My own earlier statement — "`Drop`×2 is a latent hazard that would diverge if they ever
   differ" — was understated.** The mutation test shows `trace.zen`'s declaration is *already*
   inert and `own.zen` silently governs it. §3.6.
6. **The audit applied its scepticism asymmetrically** — rigorous about disconfirming bad news,
   credulous about good news. Every negative claim in §5 was marked `[L]` and survived re-running;
   the single *positive* claim (`Own<T>` is a working `iso`) was also `[L]` and was **false**. A
   panel judge broke it in eleven lines. **Mark and re-verify favourable findings at least as hard
   as unfavourable ones** — a claim that flatters the tree is the one most likely to go unchecked.
7. **"`std.mem.debug` answers §5.2" was a reasoning error**, not a fact error: it conflates
   leak/UAF detection with race detection. Corrected in §7 step 4.
8. **My earlier hypothesis that the escape/scratch checkers were ambient-rt machinery was wrong.**
   ~0 lines are attributable to ambient rt; those ~1,365 lines are explicit-allocator machinery and
   get *more* important without it, not less. Do not delete `std.rt` expecting the checker to shrink.
