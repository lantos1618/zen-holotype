# How Zen actually uses memory — a review map

**Purpose.** Every way memory is obtained, represented, passed, and released in this tree today,
with real code. Not verdicts — *usage*. Read it and write your call under each entry.

**Baseline** `origin/main` = `6b60d5b`. Counts exclude comments and the declaring module itself.

**How to review.** Each entry has a `**YOUR CALL:**` line. Fill it in with keep / kill / merge /
change, and why. Anything you leave blank I'll treat as "no opinion yet."

Legend for the "Status" line: **load-bearing** = lots of real users · **niche** = few real users ·
**dead** = no real users · **invisible** = the programmer never wrote it.

---

# Part 1 — GETTING memory

## 1.1 Threaded allocator parameter — *the dominant pattern*

```zen
read_bytes_alloc<A> = (a: MutPtr<A>, fd: i32, n: i64) Result<[u8], IoError> {
    a.try_acquire(n + 1).match ({ … })          // src/std/io/file.zen:89
}
```

**184** functions take `a: MutPtr<A>` this way; **1,076** allocator-threading signatures in the
compiler alone. This is Zen's real memory model and it is what the compiler dogfoods.

Note the `<A>` is **unbounded** — 284 sites rely on the *letter* `A` meaning "allocator" by
convention. `<A: Allocator>` is supported and enforced, but used **4** times. The cost is diagnostic
quality: pass a non-allocator and the error blames the library's line, not your call site.

**Status:** load-bearing.
**YOUR CALL:**

---

## 1.2 Fallible acquire — `try_acquire` → `Result`

```zen
a.try_acquire(n * sizeof(T)).match ({ .Ok(p) => …, .Err(e) => err(e) })
```

**92** call sites. Allocation failure is a value. There is also `try_acquire2`/`try_acquire3`
(`alloc.zen:247,271`) — all-or-nothing rollback for 2 or 3 buffers, **7 real call sites each** in
`btree`/`set`/`hmap`/`map`.

**Status:** load-bearing.
**YOUR CALL:**

---

## 1.3 Infallible acquire — raw nullable pointer

```zen
out: [u8] := a.acquire(n).slice(n)        // src/std/text/str.zen:298 (and 7 more in that file)
```

**120** call sites. Returns `RawPtr<u8>`; **null on failure, with no error**. Of ~32 in `src/std`,
**exactly one** is null-checked (`build.zen:48`). So the same module ships a careful rollback
combinator (1.2) *and* eight consecutive unchecked acquires in `str.zen`.

**Status:** load-bearing.
**YOUR CALL:**

---

## 1.4 Typed buffer helper — `cbuf<T>`

```zen
cbuf*<T> = (a: MutPtr<Malloc>, n: i64) [T] { slice(a.acquire(n * sizeof(T)), n) }   // genc.zen:25
```

**78** uses. Length and element size derive from one `T`, so a size/type mismatch is
*unrepresentable*. This is the safest allocation shape in the tree.

Two competing twins exist: `str.nbuf` (14 uses) and `raw.of` (4 uses). Same function, three names.

**Status:** load-bearing (compiler only — `src/std` mostly doesn't use it).
**YOUR CALL:**

---

## 1.5 Stored allocator — containers that capture one

```zen
AVec*<T>: { …, alloc: DynAlloc }          // set.zen:456, hmap.zen:436
new_in*<T> = (a: DynAlloc) AVec<T> { … }
new*<T>    = () AVec<T> { a := dyn_heap()  … }     // hmap.zen:482 — captures the PROCESS heap
```

`vec.new()` / `v.push(x)` with no allocator argument. The ergonomic win is real. Note it is *not*
ambient — it stores `dyn_heap()` once at construction.

**Gap:** there is no `dyn_of_alloc<A>(a: MutPtr<A>) DynAlloc`, so `AVec`/`ASet`/`AHMap` can
**only ever** be process-heap-backed. You cannot hand one an arena or a test allocator.
`vec.zen:286` advertises a path through `rt.dyn_of_rt` that is unexported with zero callers.

**Status:** load-bearing, with a hard ceiling.
**YOUR CALL:**

---

## 1.6 Arena / bump

```zen
make_in*<A> = (backing: MutPtr<A>, cap: i64) Result<Arena, IoError>    // arena.zen:40
bump        = (a: MutPtr<Arena>, n: i64) RawPtr<u8>                    // arena.zen:10
reset       = (a: MutPtr<Arena>) void { a.off = 0 }
```

Individual `release` is a **no-op**; `reset` frees the scope. Used by the actor pool's per-behavior
scratch and by `SyncArena`/`AsyncArena`. **Zero** uses in the compiler, **zero** in examples.

This is also the only allocator that **defends against overflow** (`rounded < 0` check). Every other
size computation in the tree is unchecked.

**Status:** niche, but it is the de-facto reclamation strategy where it is used.
**YOUR CALL:**

---

## 1.7 Direct libc

```zen
p := malloc(n)      // 49 call sites, gated by an allowlist in tests/harness_boundaries.zen
```

Allowlist is 9 files. Real distribution: `pool.zen` 16, `pool_actor.zen` 11, `alloc.zen` 6,
`raw.zen` 5, `thread.zen` 4, `genc.zen` 2. So **31 of them are the concurrency layer** —
`pool_actor.zen:104` even hand-builds an `Arena` over a raw `malloc` instead of calling `make_in`.

**Status:** load-bearing floor, plus 31 sites that arguably shouldn't be there.
**YOUR CALL:**

---

## 1.8 Scoped scratch — the RAII-by-closure form

```zen
with_scratch*<T> = (n: i64, f: (RawPtr<u8>) T) T { c := zeroed(n)  r := f(c)  release(c)  r }
```

**14** call sites (socket 5, clock 3, fs 2, …). Cleanest ownership shape in the stdlib.

**Known defect:** it does **not** survive `or_return`. The emitted C shows `or_return` lowering to a
raw C `return` that exits the *enclosing function*, jumping over `release(c)`. Same for `Mutex.with`
(15 sites) and `with_pool` — where the skipped cleanup is **pthread teardown**. Zero production
sites hit it today; nothing prevents one.

**Status:** niche, correct-looking, quietly broken on the error path.
**YOUR CALL:**

---

## 1.9 Compiler-inserted allocation — *invisible*

```c
// emitted for EVERY escaping slice literal, c_expr.zen:188
({ int64_t _zsa[] = {…}; uint8_t* _zsp = zen__salloc(sizeof(_zsa)); memcpy(…); (zslice){…}; })
```

A `malloc` with **no allocator, no signature, no owner, and no free path**. `c_expr.zen:168`
documents it as a known leak. Measured: **10.6 MB / 300,000 allocations per 100k `formatln` calls**.
It scales with loop count and `error[leak]` never fires.

**Status:** invisible, unbounded, documented.
**YOUR CALL:**

---

## 1.10 Ambient runtime — `rt.alloc`

```zen
rt.alloc(n) / rt.with(custom, body) / rt.enter(a.art) … rt.leave(saved)
```

**Zero** production call sites outside the actor pool. The only live use is `pool.zen:390,641`
injecting a per-actor `Rt` around each behavior — and **nothing reads `rt.current()` in production**,
so the injection routes nothing to nowhere. `alloc.zen:313` already states the policy: *"`std.rt`
remains for pool/actor ambient runtime — not for collections."*

The experiment was run and reverted: PR #420 made collections draw ambient rt; `794828b` replaced
every `dyn_current()` with `dyn_heap()`. The ergonomics survived without the mechanism.

**Status:** dead as an allocation API; the `enter`/`leave` slot is live but unread.
**YOUR CALL:**

---

## 1.11 The LSP request scope — a hidden ambient allocator

```zen
hs_on := false                                    // alloc.zen:92 — a PROCESS-GLOBAL mutable bool
Malloc.acquire → heap_request_acquire(n)          // consults hs_on, bump-allocates when set
Heap.acquire   → heap_acquire(null, n)            // always malloc, durable
```

`heap_scope_begin`/`heap_scope_end` have **exactly two call sites in the whole tree** —
`lsp.zen:974` and `:979`. **1,343 `MutPtr<Malloc>` occurrences exist to serve those two lines.**

`Heap` and `Malloc` are both `{_: i32}` and differ in that one routing line — and the names are
backwards: `Malloc` is the scoped one.

**Status:** load-bearing by count, two real users by function.
**YOUR CALL:**

---

# Part 2 — REPRESENTING memory

## 2.1 `slice(p, n)` — the fat-pointer constructor

```zen
s: [i64] := slice(p, n)       // lowers to (zslice){ .ptr = …, .len = … } — NO validation
```

**314** occurrences (217 bare `slice(` sites). The runtime bounds check `zen__idx` compares against
`z.len` — *the number the programmer typed*. `slice(p, 1000)` over a 16-byte block passes the check
and writes 4 KB past the end (ASAN-confirmed). `slice(p, 0-5)` yields `len == -5`.

Classification of the 217: **114 structurally paired** (empty, or allocation and length in one
expression) · **100 trust-me**. Even the "paired" ones use an unchecked `n * sizeof(T)`.

**Status:** load-bearing, and the single most dangerous primitive.
**YOUR CALL:**

---

## 2.2 The three pointer kinds

| kind | uses | enforced? |
|---|---|---|
| `MutPtr<T>` | 2,007 | direction only — aliasing is unrestricted, so it means "writable", never "unique" |
| `Ptr<T>` | 817 | **yes** — writes rejected, incl. through `slice()`. Escapes via `.offset()` |
| `RawPtr<u8>` | 485 | **nothing** — satisfies *any* pointer type (`raw_floor_fits`) |
| `RawPtr<T>`, T≠u8 | 14 | nullable; needs `assert_nonnull` — which has **1** real caller |

**Status:** `Ptr` discipline is real and worth keeping; `RawPtr<u8>` is the universal escape hatch;
Stage-3 nullability is elaborate machinery guarding 14 sites.
**YOUR CALL:**

---

## 2.3 `offset()` — the untyped cast

```zen
p: Ptr<i64> := x.addr()
p.store(99)             // error[ptr-write]
p.offset(0).store(99)   // compiles, writes 99
```

**238** uses. Erases pointer kind *and* pointee type. It is also doing double duty as the
**int→pointer cast**, because Zen has no `as` keyword (`alloc.zen:95`:
`load_i64(c).offset(0)` returns a pointer from an integer).

**Status:** load-bearing, and it voids the `Ptr<T>` guarantee.
**YOUR CALL:**

---

## 2.4 Ownership wrappers

| type | real users (excl. tests) | what it does |
|---|---|---|
| `Own<T>` | **1** (`cown.zen`) | refcount + `Drop` at zero. **Affine in the binding, not the object** — `o.ptr()` extracts a `MutPtr` with no ceremony, `o.clone()` refcounts the "unique" owner |
| `Rc<T>` | **0** in production | verified working; exists mainly as the ownership checker's test subject |
| `Arc<T>` | **production** — pool allocates every actor as `Arc<PoolActor>` | genuinely atomic, contention-verified |
| `Traced<T>` | **0** | trial-deletion cycle collector; hardcoded to one payload type, single-threaded, no `dec` |
| `Drop` | 2 impls | **declared twice** (`own.zen:14`, `trace.zen:127`); which one governs depends on the caller's import set |

**Status:** `Arc` load-bearing; the rest niche-to-dead.
**YOUR CALL:**

---

## 2.5 Hand-rolled block layouts

```zen
// trace.zen:23-26 — [count:i64 | color:i64 | value:T], by hand
hcount = (b: RawPtr<u8>) i64 { load_i64(b.offset(0)) }
hcolor = (b: RawPtr<u8>) i64 { load_i64(b.offset(8)) }
```

**51 literal-offset sites across 8 files, ≥11 distinct unchecked ABIs**: rc/arc/own block,
trace block (a *duplicate* of the rc one), arena chunk, heap size header, pool header, thread arg,
ring buffers, `timespec`, `struct stat`, `sockaddr_in`.

`alloc.zen:211` already unifies rc/arc/own via `val_slot`. `trace.zen` re-implements it instead.

**Status:** load-bearing at the FFI edges, duplicated in the middle.
**YOUR CALL:**

---

# Part 3 — RELEASING memory

## 3.1 Explicit release — 113 calls

```zen
a.release(p) / o.release_in(a) / arena.free_in(backing)
```

Note the shape: **`Allocator.release` takes a pointer and no size.** That is why a debug allocator
can't poison a block or report bytes-leaked without an address-keyed side table, and part of why
`slice()` has to be trusted — the length is discarded at `acquire`.

**Status:** load-bearing.
**YOUR CALL:**

---

## 3.2 Never releasing — the arena/leak-on-purpose culture

**167** function bodies acquire and never release. `alloc.zen:70-84` states the policy outright: a
batch compile is *allowed* to leak; the LSP bounds it with the request scope (1.11). The compiler —
54k lines — contains **7** `.release(` calls total.

**Status:** deliberate, documented, and the de-facto strategy.
**YOUR CALL:**

---

## 3.3 Scope reclamation — actor scratch

```zen
saved := enter(a.art)          // pool.zen:390
__zen_actor_call(…)
leave(saved)
a.scratch_reset()              // pool.zen:393 — runs on normal return AND caught panic
```

A real region discipline: bounded lifetime, wholesale reclamation, and a static
`error[scratch-escape]` prohibiting escape across a send. **This is the closest thing Zen has to a
per-actor heap**, and it is scoped to one behavior rather than the actor's life.

**Status:** load-bearing, and the most promising foundation in the tree.
**YOUR CALL:**

---

# Part 4 — PASSING memory across threads

## 4.1 What a send actually checks

```zen
mode_of(decls, t)   // a pure function of the TYPE'S SHAPE — no program point
//   owned (iso)  = Own<T>            → sendable
//   frozen (val) = reaches no MutPtr → sendable
//   mut   (ref)  = top-level MutPtr  → NOT sendable
//   read  (box)  = readonly alias reaching a MutPtr → NOT sendable
```

Triggered by the **method names** `send` / `pool_send` / `ref_send_msg`. Rename the verb and the
check disappears.

Six shapes compile clean and race for real: `Ptr<T>` with a retained `MutPtr` (*the remedy the
compiler's own hint recommends*), `RawPtr<u8>` (classified immutable, yet has `store_i64`), a
mutable `[i64]` slice, an `Arena` by value, a hand-boxed pointer through the raw floor, and a
**generic forwarder** — where the byte-identical *concrete* forwarder is correctly rejected.

**Measured, so we don't repeat it:** narrowing the lattice to reject `RawPtr<u8>` rejects **32
matrix cells, all named `__good`, catching 0 real bugs** — because the actor stdlib *is* raw
pointers.

**Status:** unsound, and not cheaply fixable by tightening.
**YOUR CALL:**

---

## 4.2 What messages actually carry

```zen
ChatMsg*: Join(string_view) | Say(SayArgs) | GetStats(ReplyRef<ChatStats>)
Msg*:     Inc(i64) | Work(i64) | Boom(i64) | Ping(ReplyRef<i32>)
```

**Not one message in the repository carries a `Ptr<T>`, `MutPtr<T>`, or `Own<T>`.** Every real
payload is a scalar, a plain struct, a `string_view`, or an opaque capability.

That is the fact that makes copy-on-send or per-actor heaps viable without reference capabilities —
the copy is already happening in practice, it just isn't guaranteed.

**Status:** the most useful empirical fact in this document.
**YOUR CALL:**

---

# Part 5 — the shape of the whole thing

Four ways to say "a thing you can allocate from":

| | what it is | conversions |
|---|---|---|
| `Allocator` | the trait | — |
| `DynAlloc` | erased 3-fn vtable + state | `dyn_of`, `dyn_heap` |
| `Rt` | **the same four fields** + a `ready` flag | `mem_rt`, `heap_rt` — *same bodies, different return type* |
| `Heap` / `Malloc` | two empty structs differing in one routing line | — |

Missing conversions: `DynAlloc → Rt`, `any A: Allocator → DynAlloc`, and `Rt` has no
`impl(Allocator)` at all.

**YOUR CALL on the whole shape:**

---

## Open questions I'd like your ruling on

1. **`Allocator` returns `RawPtr<u8>`, not `[T]`; `release` takes no size.** Zig returns `[]T` and
   takes it back. Changing this makes `slice()` lengths derived instead of trusted, and makes a
   debug allocator implementable. It is also the single most invasive change on the list.

2. **`n.loop(f)` as the general loop.** Today `.loop` walks slices only; `iter.range_in` heap-
   allocates `n` integers to count to `n`; and `n.loop(…)` passes `zen check` then emits C that
   won't compile. Should an integer receiver mean a counted loop?

3. **Scope-exit cleanup.** `or_return` skips it (1.8). Options: reject `or_return` inside an
   FnT-param lambda (zero production sites today), change `or_return` in a lambda to return from the
   *lambda*, add `defer`, or lean on `Own`/`Drop`. Three of four panel judges argued against `defer`
   as the first move.

4. **`RawPtr<u8>` as the universal floor.** Keep it and delete the Stage-3 nullability machinery it
   makes vacuous, or commit to typed `RawPtr<T>` everywhere?

5. **Per-actor heap.** Extend 3.3's scratch arena from per-behavior to per-actor-persistent, with
   copy-on-send at the boundary — justified by 4.2. Or leave actors on the shared heap?
