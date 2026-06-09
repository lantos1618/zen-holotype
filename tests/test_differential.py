"""Differential regression tests — guard against bugs found by the bug-hunt (the self-hosted
toolchain miscompiling or mis-checking). Each entry is a minimal program that previously diverged;
we assert the self-hosted side now computes the right value / verdict.

`self_side(src)` runs the program through the self-hosted BINARY oracle (`_oracle.self_side`) and
returns {verdict: accept|reject, value: int|None}. NO Python frontend is in the loop — the EMIT +
CHECK binaries (built from the committed bootstrap C by `cc` alone) are the sole correctness
reference.
"""
import pytest

from _oracle import self_side


# Value-correctness: the self-hosted toolchain must compute these exactly (silent-miscompile guards).
@pytest.mark.parametrize("src,want", [
    # i64 integer literals (were truncated through an i32 accumulator / gen_int)
    ("test* = () i64 { 10000000000 / 10 }", 1000000000),     # was 141006540
    ("test* = () i64 { 9999999999 - 9999999990 }", 9),
    ("test* = () i64 { 5000000000 + 5000000000 }", 10000000000),
    # NESTED block comments: the inner `*/` must NOT close the outer comment (was stopping early → 1)
    ("test* = () i32 {\n  1 + /* outer /* inner */ still-comment */ 41\n}", 42),
    ("test* = () i32 { 3 + /* plain */ 4 }", 7),
    # char literals must not desync the token stream — a malformed 'ab' used to corrupt the NEXT decl
    ("bad* = () i32 { 'ab' }\ntest* = () i32 { 5 }", 5),
    ("test* = () i32 { 'A' }", 65),
    # slice-literal STATEMENT must not glue onto the previous statement as an index (`x := 7` ⨯ `[1]`)
    ("test* = () i32 {\n  x := 7\n  [1]\n  x\n}", 7),
    ("test* = () i32 {\n  [9, 9]\n  1 + 2\n}", 3),
    # same-line indexing must still work (regression guard for the newline-aware fix)
    ("test* = () i32 {\n  s := [10, 20, 30]\n  s[2]\n}", 30),
    # generic CONSTRUCTOR called with a non-literal (Var) arg: T must be inferred from the local's
    # type (was → `Box_void` miscompile because light_ty couldn't type a Var without an env)
    ("Box<T>: { v: T }\nwrap<T> = (x: T) Box<T> { Box<T>(v: x) }\nget<T> = (b: Box<T>) i32 { b.v }\ntest* = () i32 {\n  n := 5\n  get(wrap(n))\n}", 5),
    ("Box<T>: { v: T }\nwrap<T> = (x: T) Box<T> { Box<T>(v: x) }\nget<T> = (b: Box<T>) i32 { b.v }\ntest* = () i32 {\n  n := 9\n  w := wrap(n)\n  get(w)\n}", 9),
    # generic ENUMS (Opt<T>) — monomorphized by use like generic structs. Values + matching across
    # the realistic patterns: direct ctor, let-bound, producer (Some/None/conditional), consumer.
    ("Opt<T>: Some(T) | None\ntest* = () i32 { (.Some(5)).match({ .Some(x) => x, .None => 0 }) }", 5),
    ("Opt<T>: Some(T) | None\ntest* = () i32 {\n  o := .Some(7)\n  o.match({ .Some(x) => x, .None => 0 })\n}", 7),
    ("Opt<T>: Some(T) | None\nmk<T> = (x: T) Opt<T> { .Some(x) }\ntest* = () i32 { mk(8).match({ .Some(x) => x, .None => 0 }) }", 8),
    ("Opt<T>: Some(T) | None\none<T> = (x: T) Opt<T> { .None }\ntest* = () i32 { one(5).match({ .Some(x) => x, .None => 3 }) }", 3),
    ("Opt<T>: Some(T) | None\npick<T> = (x: T, b: i32) Opt<T> { (b == 1).match({ true => .Some(x), false => .None }) }\ntest* = () i32 { pick(9, 0).match({ .Some(x) => x, .None => 3 }) }", 3),
    ("Opt<T>: Some(T) | None\nunwrap<T> = (o: Opt<T>, d: T) T { o.match({ .Some(x) => x, .None => d }) }\ntest* = () i32 {\n  o := .Some(7)\n  unwrap(o, 0)\n}", 7),
    # a generic fn's tparam inferred from a SLICE-LITERAL argument (`[T]` param vs `[i32]` arg → T=i32);
    # without it light_ty returned void → a `void`-element miscompile
    ("first<T> = (xs: [T]) T { xs[0] }\ntest* = () i32 { first([7, 8]) }", 7),
    ("pick2<T> = (xs: [T], a: T) T { xs[1] + a }\ntest* = () i32 { pick2([3, 4], 5) }", 9),
    # a generic CALL's return type is inferred + substituted, so a let bound to it (and a downstream
    # generic call on it) carries the concrete instance — `mk(...)` returns Box<i32>, not the leaked Box<T>
    ("Box<T>: { v: T }\nmk<T> = (x: T) Box<T> { Box<T>(v: x) }\nget<T> = (b: Box<T>) T { b.v }\ntest* = () i32 {\n  b := mk(42)\n  b.get()\n}", 42),
    # a generic container round-trip (the Vec<T> substrate): build from a slice, read back through a
    # second generic call — exercises generic-call return inference + element-type preservation on inline
    ("Vec<T>: { ptr: RawPtr<u8>, len: i64, cap: i64 }\nmalloc = (n: i64) RawPtr<u8>\nbuf<T> = (v: Vec<T>) [T] { slice(v.ptr, v.cap) }\nget<T> = (v: Vec<T>, i: i64) T { v.buf()[i] }\nof<T> = (xs: [T]) Vec<T> {\n  v := Vec<T>(ptr: malloc(xs.len * sizeof(T)), len: xs.len, cap: xs.len)\n  b := v.buf()\n  xs.loop((h, i, x) { b[i] = x })\n  v\n}\ntest* = () i32 {\n  v := of([10, 20, 30])\n  v.get(0) + v.get(2)\n}", 40),
    # bug-hunt #11: a bare ctor passed DIRECTLY as a generic-consumer arg (T inferred from the payload)
    ("Opt<T>: Some(T) | None\nu<T> = (o: Opt<T>) i32 { o.match({ .Some(x) => 1, .None => 0 }) }\ntest* = () i32 { u(.Some(42)) }", 1),
    ("Opt<T>: Some(T) | None\nunwrap<T> = (o: Opt<T>, d: T) T { o.match({ .Some(x) => x, .None => d }) }\ntest* = () i32 { unwrap(.Some(7), 0) }", 7),
    # MULTI-IMPLEMENTOR traits (#5-full): two types implementing the same trait method now emit
    # DISTINCT C functions (impl_<Trait>_<Type>_<m>) and `x.m()` dispatches on x's type — previously
    # both emitted `int32_t area(...)` and cc rejected with "conflicting types".
    ("A*: { v: i32 }\nB*: { v: i32 }\nShow*: { area: (Ptr<Self>) i32 }\nA.impl(Show, { area = (a: Ptr<A>) i32 { a.v } })\nB.impl(Show, { area = (b: Ptr<B>) i32 { b.v * b.v } })\ntest* = () i32 {\n  a := A(v: 5)\n  b := B(v: 6)\n  addr(a).area() + addr(b).area()\n}", 41),
    # a single trait method with two implementors taking an extra arg, both reached + dispatched
    ("P*: { x: i32 }\nQ*: { x: i32 }\nDbl*: { f: (Ptr<Self>, i32) i32 }\nP.impl(Dbl, { f = (p: Ptr<P>, k: i32) i32 { p.x + k } })\nQ.impl(Dbl, { f = (q: Ptr<Q>, k: i32) i32 { q.x * k } })\ntest* = () i32 {\n  p := P(x: 10)\n  q := Q(x: 3)\n  addr(p).f(2) + addr(q).f(4)\n}", 24),
    # MODULE-LEVEL MUTABLE GLOBALS (Goal Z E1): `counter := 0` emits `static int32_t counter = 0;`
    # and a function reads/assigns it across calls (state persists). Was: mis-parsed as an enum.
    ("counter := 0\nbump* = () i32 { counter = counter + 1  counter }\ntest* = () i32 { bump() + bump() }", 3),
    ("total := 100\nadd* = (n: i32) i32 { total = total + n  total }\ntest* = () i32 { add(5)  add(20) }", 125),
    # store_i64/load_i64 intrinsics (Goal Z 2b): a typed 8-byte write/read at a byte ptr (arena cursors,
    # Rc/ARC headers) — `store(offset(p,8),x)` would write only 1 byte (uint8_t* cast); these write 8.
    ("Cell*: { x: i64 }\ntest* = () i64 { c := Cell(x: 0)  store_i64(addr(c), 42)  load_i64(addr(c)) }", 42),
    # ARENA bump allocator (Goal Z 4): two bump allocations from one buffer, each written/read via the
    # cursor — proves pointer-add allocation + field mutation through MutPtr<Arena>. (std.arena, here
    # inlined since run_value has no module resolver yet; arena.zen itself is acid-checked.)
    ("Arena*: { buf: RawPtr<u8>, off: i64, cap: i64 }\nmalloc = (n: i64) RawPtr<u8>\nan* = (cap: i64) Arena { Arena(buf: malloc(cap), off: 0, cap: cap) }\nbump* = (a: MutPtr<Arena>, n: i64) RawPtr<u8> { p := a.buf.offset(a.off)  a.off = a.off + n  p }\ntest* = () i64 {\n  a := an(64)\n  p := addr(a).bump(8)\n  store_i64(p, 99)\n  q := addr(a).bump(8)\n  store_i64(q, 1)\n  load_i64(p) + load_i64(q)\n}", 100),
    # a VOID-tail bool match (a conditional side-effect, e.g. a guarded store/free) must lower to an
    # `if` STATEMENT, not a C ternary — `(c ? void : void)` is invalid C. Here set() stores only when
    # n != 0; the tail match yields nothing. (Regression guard for the void-Cond → if fix.)
    ("Cell*: { x: i64 }\nset = (c: MutPtr<Cell>, n: i64) void { (n == 0).match({ true => {}, false => store_i64(c, n) }) }\ntest* = () i64 {\n  c := Cell(x: 1)\n  set(addr(c), 0)\n  set(addr(c), 9)\n  load_i64(addr(c))\n}", 9),
    # Rc<T> reference counting (Goal Z 5, the RC in ARC/ORC): shared heap value with a refcount header
    # [count|value]; clone bumps the count, drop decrements + frees at zero (a void-tail conditional
    # free). Asserts clone→2, drop→1, value 42 preserved. (std.rc, inlined; rc.zen is self-hosted-only.)
    ("Rc<T>: { base: RawPtr<u8> }\nmalloc = (n: i64) RawPtr<u8>\nfree = (p: RawPtr<u8>) void\nrc_val<T> = (r: Rc<T>) [T] { slice(r.base.offset(8), 1) }\nrc_new<T> = (x: T) Rc<T> { base := malloc(8 + sizeof(T))  store_i64(base, 1)  r := Rc<T>(base: base)  s := r.rc_val()  s[0] = x  r }\nrc_get<T> = (r: Rc<T>) T { r.rc_val()[0] }\nrc_clone<T> = (r: Rc<T>) Rc<T> { store_i64(r.base, load_i64(r.base) + 1)  Rc<T>(base: r.base) }\nrc_drop<T> = (r: Rc<T>) void { n := load_i64(r.base) - 1  store_i64(r.base, n)  (n == 0).match({ true => free(r.base), false => {} }) }\nrc_count<T> = (r: Rc<T>) i64 { load_i64(r.base) }\ntest* = () i64 {\n  r := rc_new(42)\n  r2 := r.rc_clone()\n  a := r.rc_count()\n  r.rc_drop()\n  b := r.rc_count()\n  v := r.rc_get()\n  a * 100 + b * 10 + v\n}", 252),
    # STACKFUL COROUTINE over libc ucontext (Goal Z 6, the no-color async primitive): a fiber on its
    # own stack yields back to the resumer and is resumed again. work() yields twice (g_n 1→11→111),
    # resume reports 1,1 (alive) then 0 (returned) → 111*10 + 1+1+0 = 1112. Exercises: a function-
    # pointer extern param (makecontext's `void(*)()`), null_ptr globals, store_i64 into a raw context
    # buffer, and bodyless-extern-with-FnT not being inlined. (std.coroutine, inlined here.)
    ("getcontext  = (ctx: RawPtr<u8>) i32\nmakecontext = (ctx: RawPtr<u8>, fn: () void, argc: i32) void\nswapcontext = (out: RawPtr<u8>, inc: RawPtr<u8>) i32\nmalloc = (n: i64) RawPtr<u8>\ng_cur := null_ptr()\ng_link := null_ptr()\ng_yielded := 0\ng_n := 0\nCoro*: { ctx: RawPtr<u8>, link: RawPtr<u8>, stack: RawPtr<u8> }\ncoro_new = (work: () void) Coro {\n  stack := malloc(65536)\n  ctx := malloc(1024)\n  link := malloc(1024)\n  getcontext(ctx)\n  store_i64(ctx.offset(16), stack)\n  store_i64(ctx.offset(32), 65536)\n  store_i64(ctx.offset(8), link)\n  makecontext(ctx, work, 0)\n  Coro(ctx: ctx, link: link, stack: stack)\n}\ncoro_resume = (c: Coro) i32 { g_cur = c.ctx  g_link = c.link  g_yielded = 0  swapcontext(c.link, c.ctx)  g_yielded }\ncoro_yield = () void { g_yielded = 1  swapcontext(g_cur, g_link) }\nwork = () void { g_n = g_n + 1  coro_yield()  g_n = g_n + 10  coro_yield()  g_n = g_n + 100 }\ntest* = () i32 { c := coro_new(work)  r1 := coro_resume(c)  r2 := coro_resume(c)  r3 := coro_resume(c)  g_n * 10 + r1 + r2 + r3 }", 1112),
    # COLORLESS RUNTIME (Goal Z 7 — the thesis): ONE generic worker<R> calls r.suspend(); with Sync
    # it's a no-op (runs straight through, 111); with Async it's a coroutine yield (driven by 3 resumes,
    # also 111). Same source, sync or async chosen by the Runtime type — zero function coloring, the
    # compiler has no async machinery. 111*1000 + 111 = 111111. (std.runtime + std.coroutine, inlined.)
    ("getcontext  = (ctx: RawPtr<u8>) i32\nmakecontext = (ctx: RawPtr<u8>, fn: () void, argc: i32) void\nswapcontext = (out: RawPtr<u8>, inc: RawPtr<u8>) i32\nmalloc = (n: i64) RawPtr<u8>\ng_cur := null_ptr()\ng_back := null_ptr()\ng_flag := 0\ng_n := 0\nCoro*: { ctx: RawPtr<u8>, link: RawPtr<u8>, stack: RawPtr<u8> }\ncoro_new = (work: () void) Coro {\n  stack := malloc(65536)\n  ctx := malloc(1024)\n  link := malloc(1024)\n  getcontext(ctx)\n  store_i64(ctx.offset(16), stack)\n  store_i64(ctx.offset(32), 65536)\n  store_i64(ctx.offset(8), link)\n  makecontext(ctx, work, 0)\n  Coro(ctx: ctx, link: link, stack: stack)\n}\ncoro_resume = (c: Coro) i32 { g_cur = c.ctx  g_back = c.link  g_flag = 0  swapcontext(c.link, c.ctx)  g_flag }\ncoro_yield = () void { g_flag = 1  swapcontext(g_cur, g_back) }\nRuntime*: { suspend: (Ptr<Self>) void }\nSync*: { _: i32 }\nAsync*: { _: i32 }\nSync.impl(Runtime, { suspend = (s: Ptr<Sync>) void { } })\nAsync.impl(Runtime, { suspend = (a: Ptr<Async>) void { coro_yield() } })\nworker<R> = (r: Ptr<R>) void { g_n = g_n + 1  r.suspend()  g_n = g_n + 10  r.suspend()  g_n = g_n + 100 }\nawork = () void { a := Async(_: 0)  worker(addr(a)) }\ntest* = () i32 {\n  s := Sync(_: 0)\n  worker(addr(s))\n  sync_n := g_n\n  g_n = 0\n  c := coro_new(awork)\n  coro_resume(c)\n  coro_resume(c)\n  coro_resume(c)\n  sync_n * 1000 + g_n\n}", 111111),
    # COOPERATIVE SCHEDULER (Goal Z 9): a general round-robin run([Coro]) drives two coroutines to
    # completion. Each appends its id to a shared log between yields (A:1,1,1  B:2,2); interleaved
    # execution gives 12121 (sequential would be 11122). Exercises a slice-of-struct literal [a,b]
    # whose elements come from template-call locals (the Block-type-inference fix). (std.sched, inlined.)
    ("getcontext  = (ctx: RawPtr<u8>) i32\nmakecontext = (ctx: RawPtr<u8>, fn: () void, argc: i32) void\nswapcontext = (out: RawPtr<u8>, inc: RawPtr<u8>) i32\nmalloc = (n: i64) RawPtr<u8>\ng_cur := null_ptr()\ng_back := null_ptr()\ng_flag := 0\ng_log := 0\nCoro*: { ctx: RawPtr<u8>, link: RawPtr<u8>, stack: RawPtr<u8> }\ncoro_new = (work: () void) Coro { stack := malloc(65536)  ctx := malloc(1024)  link := malloc(1024)  getcontext(ctx)  store_i64(ctx.offset(16), stack)  store_i64(ctx.offset(32), 65536)  store_i64(ctx.offset(8), link)  makecontext(ctx, work, 0)  Coro(ctx: ctx, link: link, stack: stack) }\nresume = (c: Coro) i32 { g_cur = c.ctx  g_back = c.link  g_flag = 0  swapcontext(c.link, c.ctx)  g_flag }\ncoro_yield = () void { g_flag = 1  swapcontext(g_cur, g_back) }\nawork = () void { g_log = g_log * 10 + 1  coro_yield()  g_log = g_log * 10 + 1  coro_yield()  g_log = g_log * 10 + 1 }\nbwork = () void { g_log = g_log * 10 + 2  coro_yield()  g_log = g_log * 10 + 2 }\nmark_alive = (flags: RawPtr<u8>, i: i32, n: i32) void { store_i64(flags.offset(i * 8), 1)  init_flags(flags, i + 1, n) }\ninit_flags = (flags: RawPtr<u8>, i: i32, n: i32) void { (i < n).match({ true => mark_alive(flags, i, n), false => {} }) }\ndo_tick = (coros: [Coro], flags: RawPtr<u8>, i: i32) i32 { r := coros[i].resume()  store_i64(flags.offset(i * 8), r)  r }\ntick = (coros: [Coro], flags: RawPtr<u8>, i: i32) i32 { (load_i64(flags.offset(i * 8)) == 1).match({ true => do_tick(coros, flags, i), false => 0 }) }\npass = (coros: [Coro], flags: RawPtr<u8>, i: i32, n: i32) i32 { (i < n).match({ true => tick(coros, flags, i) + pass(coros, flags, i + 1, n), false => 0 }) }\ndrive = (coros: [Coro], flags: RawPtr<u8>, n: i32) void { (pass(coros, flags, 0, n) > 0).match({ true => drive(coros, flags, n), false => {} }) }\nrun = (coros: [Coro]) void { n := coros.len  flags := malloc(n * 8)  init_flags(flags, 0, n)  drive(coros, flags, n) }\ntest* = () i32 { a := coro_new(awork)  b := coro_new(bwork)  run([a, b])  g_log }", 12121),
    # ACTORS over a mailbox (Goal Z 9): a producer and consumer coroutine, scheduled cooperatively,
    # communicate ONLY through a heap FIFO. Producer sends 1,2,3 (yielding between); consumer folds
    # g_acc = g_acc*10 + recv(), yielding when empty. Ordered hand-off → 123. (std.actor, inlined.)
    ("getcontext  = (ctx: RawPtr<u8>) i32\nmakecontext = (ctx: RawPtr<u8>, fn: () void, argc: i32) void\nswapcontext = (out: RawPtr<u8>, inc: RawPtr<u8>) i32\nmalloc = (n: i64) RawPtr<u8>\ng_cur := null_ptr()\ng_back := null_ptr()\ng_flag := 0\ng_mbox := null_ptr()\ng_head := 0\ng_tail := 0\ng_acc := 0\nCoro*: { ctx: RawPtr<u8>, link: RawPtr<u8>, stack: RawPtr<u8> }\ncoro_new = (work: () void) Coro { stack := malloc(65536)  ctx := malloc(1024)  link := malloc(1024)  getcontext(ctx)  store_i64(ctx.offset(16), stack)  store_i64(ctx.offset(32), 65536)  store_i64(ctx.offset(8), link)  makecontext(ctx, work, 0)  Coro(ctx: ctx, link: link, stack: stack) }\ncoro_resume = (c: Coro) i32 { g_cur = c.ctx  g_back = c.link  g_flag = 0  swapcontext(c.link, c.ctx)  g_flag }\ncoro_yield = () void { g_flag = 1  swapcontext(g_cur, g_back) }\nsend = (m: i64) void { store_i64(g_mbox.offset(g_tail * 8), m)  g_tail = g_tail + 1 }\nrecv = () i64 { m := load_i64(g_mbox.offset(g_head * 8))  g_head = g_head + 1  m }\nhas_msg = () i32 { (g_head < g_tail).match({ true => 1, false => 0 }) }\nproducer = () void { send(1)  coro_yield()  send(2)  coro_yield()  send(3) }\ntake = () void { g_acc = g_acc * 10 + recv() }\nconsume = (remaining: i32) void { (remaining == 0).match({ true => {}, false => (has_msg() == 1).match({ true => after_take(remaining), false => after_wait(remaining) }) }) }\nafter_take = (remaining: i32) void { take()  consume(remaining - 1) }\nafter_wait = (remaining: i32) void { coro_yield()  consume(remaining) }\nconsumer = () void { consume(3) }\nstep = (c: Coro, alive: i32) i32 { (alive == 1).match({ true => coro_resume(c), false => 0 }) }\nrun2 = (a: Coro, b: Coro, aa: i32, bb: i32) void { na := step(a, aa)  nb := step(b, bb)  ((na + nb) > 0).match({ true => run2(a, b, na, nb), false => {} }) }\ntest* = () i32 { g_mbox = malloc(128)  p := coro_new(producer)  c := coro_new(consumer)  run2(p, c, 1, 1)  g_acc }", 123),
    # ONE ALLOCATOR ABSTRACTION over HEAP + ARENA (Goal Z): a single Alloc trait, implemented by Heap
    # (malloc-backed, stateless) and Bump (a stateful arena that advances its cursor through MutPtr<Self>
    # INSIDE the dispatched impl method). The same generic fill<A> allocates two i64s from either — 42
    # from each → 84. This is the unified memory abstraction the colorless Runtime builds on.
    ("Alloc*: { acquire: (MutPtr<Self>, i64) RawPtr<u8> }\nmalloc = (n: i64) RawPtr<u8>\nHeap*: { _: i32 }\nBump*: { buf: RawPtr<u8>, off: i64 }\nHeap.impl(Alloc, { acquire = (s: MutPtr<Heap>, n: i64) RawPtr<u8> { malloc(n) } })\nBump.impl(Alloc, { acquire = (s: MutPtr<Bump>, n: i64) RawPtr<u8> { p := s.buf.offset(s.off)  s.off = s.off + n  p } })\nfill<A> = (a: MutPtr<A>) i64 { p := a.acquire(8)  store_i64(p, 21)  q := a.acquire(8)  store_i64(q, 21)  load_i64(p) + load_i64(q) }\ntest* = () i32 {\n  h := Heap(_: 0)\n  b := Bump(buf: malloc(64), off: 0)\n  fill(addr(h)) + fill(addr(b)) + b.off\n}", 100),
    # Arc<T> ATOMIC reference counting (Goal Z, the ARC in ARC/ORC): same layout/API as Rc<T> but
    # clone/drop adjust the refcount with the atomic_add_i64 intrinsic (a SEQ_CST fetch-add → GCC
    # __atomic_add_fetch) so concurrent threads can share it race-free. clone→2, drop→1, value 42 → 252.
    # (std.arc, inlined; the `0 - 1` decrement avoids a prefix-minus literal.)
    ("Arc<T>: { base: RawPtr<u8> }\nmalloc = (n: i64) RawPtr<u8>\nfree = (p: RawPtr<u8>) void\narc_val<T> = (r: Arc<T>) [T] { slice(r.base.offset(8), 1) }\narc_new<T> = (x: T) Arc<T> { base := malloc(8 + sizeof(T))  store_i64(base, 1)  r := Arc<T>(base: base)  sl := r.arc_val()  sl[0] = x  r }\narc_get<T> = (r: Arc<T>) T { r.arc_val()[0] }\narc_count<T> = (r: Arc<T>) i64 { load_i64(r.base) }\narc_clone<T> = (r: Arc<T>) Arc<T> { atomic_add_i64(r.base, 1)  Arc<T>(base: r.base) }\narc_drop<T> = (r: Arc<T>) void { (atomic_add_i64(r.base, 0 - 1) == 0).match({ true => free(r.base), false => {} }) }\ntest* = () i64 {\n  r := arc_new(42)\n  r2 := r.arc_clone()\n  a := r.arc_count()\n  r.arc_drop()\n  b := r.arc_count()\n  v := r.arc_get()\n  a * 100 + b * 10 + v\n}", 252),
    # DROP DISPATCH (Goal Z ORC, the deterministic-destruction primitive): a concrete type that implements
    # the Drop trait has its destructor reached as `addr(value).drop()` → impl_Drop_Resource_drop, the same
    # UFCS trait dispatch std.runtime/std.alloc use. Proves a destructor runs side effects (g += id) on the
    # value via a MutPtr<Self> receiver, with ZERO compiler support beyond multi-implementor traits.
    ("g_dropped := 0\nDrop*: { drop: (MutPtr<Self>) void }\nResource*: { id: i32 }\nResource.impl(Drop, { drop = (s: MutPtr<Resource>) void { g_dropped = g_dropped + s.id } })\ntest* = () i32 {\n  r := Resource(id: 7)\n  addr(r).drop()\n  g_dropped\n}", 7),
    # OWNING Rc + DROP-AT-ZERO (Goal Z ORC, the whole point): an owning refcounted pointer over a Resource
    # that implements Drop. release() decrements; at count ZERO it calls the payload's Drop (concrete
    # dispatch → impl_Drop_Resource_drop) BEFORE freeing — deterministic destruction. We clone (count 2),
    # release once (count 1 → drop must NOT fire: mid stays 0), release again (count 0 → drop fires EXACTLY
    # once: g_dropped → 1). mid*10 + g_dropped = 0*10 + 1 = 1. (std.drop, inlined; drop.zen is the canonical
    # @self-hosted-only form, acid-checked. Concrete Own here; a fully GENERIC Own<T> is the next case.)
    ("malloc = (n: i64) RawPtr<u8>\nfree = (p: RawPtr<u8>) void\ng_dropped := 0\nDrop*: { drop: (MutPtr<Self>) void }\nResource*: { id: i32 }\nResource.impl(Drop, { drop = (s: MutPtr<Resource>) void { g_dropped = g_dropped + 1 } })\nOwn*: { base: RawPtr<u8> }\nown_val = (o: Own) [Resource] { slice(o.base.offset(8), 1) }\nown_new = (x: Resource) Own { base := malloc(8 + sizeof(Resource))  store_i64(base, 1)  o := Own(base: base)  s := o.own_val()  s[0] = x  o }\nown_clone = (o: Own) Own { store_i64(o.base, load_i64(o.base) + 1)  Own(base: o.base) }\nown_ptr = (o: Own) MutPtr<Resource> { addr(o.own_val()[0]) }\nown_release = (o: Own) void { n := load_i64(o.base) - 1  store_i64(o.base, n)  (n == 0).match({ true => own_fin(o), false => {} }) }\nown_fin = (o: Own) void { o.own_ptr().drop()  free(o.base) }\ntest* = () i32 {\n  o := own_new(Resource(id: 5))\n  o2 := o.own_clone()\n  o.own_release()\n  mid := g_dropped\n  o2.own_release()\n  mid * 10 + g_dropped\n}", 1),
    # GENERIC OWNING POINTER + DROP-AT-ZERO (THE generic-dispatch keystone — unblocks generic Drop/ORC):
    # a fully GENERIC Own<T> over ANY T that impls Drop. own_fin<T>'s body does `o.own_ptr().drop()` where
    # own_ptr<T> returns MutPtr<T> — a UFCS trait call whose receiver is the bare tparam in the template.
    # It re-dispatches to the CONCRETE impl only after Own<T> is monomorphized into Own<Resource>: (1)
    # check.index_elem infers the spliced `own_val(o)[0]` element from the substituted Index.elem (=Resource,
    # not the void-typed inlined slice), so the receiver infers as MutPtr<Resource> and the post-inline
    # re-resolve pass routes `.drop()` → impl_Drop_Resource_drop; (2) check_validate.is_trait_method keeps the
    # un-monomorphized template's bare `drop` from being false-rejected. Same clone→2, release×2 dance as the
    # concrete case: drop fires EXACTLY once at count zero → mid*10 + g_dropped = 1. This is the canonical
    # std.drop Own<T> proof (drop.zen now holds the generic form, acid-checked).
    ("malloc = (n: i64) RawPtr<u8>\nfree = (p: RawPtr<u8>) void\ng_dropped := 0\nDrop*: { drop: (MutPtr<Self>) void }\nResource*: { id: i32 }\nResource.impl(Drop, { drop = (s: MutPtr<Resource>) void { g_dropped = g_dropped + 1 } })\nOwn<T>: { base: RawPtr<u8> }\nown_val<T> = (o: Own<T>) [T] { slice(o.base.offset(8), 1) }\nown_new<T> = (x: T) Own<T> { base := malloc(8 + sizeof(T))  store_i64(base, 1)  o := Own<T>(base: base)  s := o.own_val()  s[0] = x  o }\nown_clone<T> = (o: Own<T>) Own<T> { store_i64(o.base, load_i64(o.base) + 1)  Own<T>(base: o.base) }\nown_ptr<T> = (o: Own<T>) MutPtr<T> { addr(o.own_val()[0]) }\nown_release<T> = (o: Own<T>) void { n := load_i64(o.base) - 1  store_i64(o.base, n)  (n == 0).match({ true => own_fin(o), false => {} }) }\nown_fin<T> = (o: Own<T>) void { o.own_ptr().drop()  free(o.base) }\ntest* = () i32 {\n  o := own_new(Resource(id: 5))\n  o2 := o.own_clone()\n  o.own_release()\n  mid := g_dropped\n  o2.own_release()\n  mid * 10 + g_dropped\n}", 1),
    # ── std.cown — the FFI MEMORY CONVENTION (Goal N3): a RAW boundary pointer (RawPtr<u8> from C
    # malloc) is re-owned by wrapping it in `Buf` + impl(Drop, { … free … }); Own<Buf> then fires the
    # matching `free` EXACTLY ONCE at refcount zero. A `g_freed` counter (incremented by the wrapped
    # free) makes the boundary release OBSERVABLE. clone -> count 2; first release does NOT free
    # (mid g_freed == 0); second release at count 0 -> Buf.drop -> free fires ONCE (g_freed == 1).
    # Result = v(65) + mid(0)*100 + end(1)*10 = 75. This is example 1 of zen/std/cown.zen, flattened
    # (drop.zen is @self-hosted-only, inlined as the canonical Own<T> proofs above are).
    ("malloc = (n: i64) RawPtr<u8>\nfree = (p: RawPtr<u8>) void\ng_freed := 0\nfree_obs = (p: RawPtr<u8>) void { g_freed = g_freed + 1  free(p) }\nDrop*: { drop: (MutPtr<Self>) void }\nOwn<T>: { base: RawPtr<u8> }\nown_val<T> = (o: Own<T>) [T] { slice(o.base.offset(8), 1) }\nown_get<T> = (o: Own<T>) T { o.own_val()[0] }\nown_new<T> = (x: T) Own<T> { base := malloc(8 + sizeof(T))  store_i64(base, 1)  o := Own<T>(base: base)  s := o.own_val()  s[0] = x  o }\nown_clone<T> = (o: Own<T>) Own<T> { store_i64(o.base, load_i64(o.base) + 1)  Own<T>(base: o.base) }\nown_ptr<T> = (o: Own<T>) MutPtr<T> { addr(o.own_val()[0]) }\nown_release<T> = (o: Own<T>) void { n := load_i64(o.base) - 1  store_i64(o.base, n)  (n == 0).match({ true => own_fin(o), false => {} }) }\nown_fin<T> = (o: Own<T>) void { o.own_ptr().drop()  free(o.base) }\nBuf*: { p: RawPtr<u8>, len: i64 }\nbuf_alloc = (n: i64) Own<Buf> { own_new(Buf(p: malloc(n), len: n)) }\nbuf_set = (o: Own<Buf>, i: i64, v: u8) void { store(o.own_get().p.offset(i), v) }\nbuf_get = (o: Own<Buf>, i: i64) u8 { load(o.own_get().p.offset(i)) }\nBuf.impl(Drop, { drop = (b: MutPtr<Buf>) void { free_obs(b.p) } })\ntest* = () i32 {\n  o := buf_alloc(8)\n  o.buf_set(0, 65)\n  v := o.buf_get(0)\n  o2 := o.own_clone()\n  o.own_release()\n  mid := g_freed\n  o2.own_release()\n  end := g_freed\n  v + mid * 100 + end * 10\n}", 75),
    # std.cown example 2 — a POSIX file descriptor (RawPtr-equivalent raw OS handle) re-owned via
    # `File` + impl(Drop, { … close … }); Own<File> fires the matching `close` EXACTLY ONCE at zero.
    # A `g_closed` counter (incremented by the wrapped close) makes close-on-drop observable. Same
    # clone(count 2) -> release(no close, mid==0) -> release(close fires once, end==1) dance. Result =
    # fd(7) + mid(0)*100 + end(1)*10 = 17.
    ("malloc = (n: i64) RawPtr<u8>\nfree = (p: RawPtr<u8>) void\nclose = (fd: i32) i32\ng_closed := 0\nclose_obs = (fd: i32) i32 { g_closed = g_closed + 1  0 }\nDrop*: { drop: (MutPtr<Self>) void }\nOwn<T>: { base: RawPtr<u8> }\nown_val<T> = (o: Own<T>) [T] { slice(o.base.offset(8), 1) }\nown_get<T> = (o: Own<T>) T { o.own_val()[0] }\nown_new<T> = (x: T) Own<T> { base := malloc(8 + sizeof(T))  store_i64(base, 1)  o := Own<T>(base: base)  s := o.own_val()  s[0] = x  o }\nown_clone<T> = (o: Own<T>) Own<T> { store_i64(o.base, load_i64(o.base) + 1)  Own<T>(base: o.base) }\nown_ptr<T> = (o: Own<T>) MutPtr<T> { addr(o.own_val()[0]) }\nown_release<T> = (o: Own<T>) void { n := load_i64(o.base) - 1  store_i64(o.base, n)  (n == 0).match({ true => own_fin(o), false => {} }) }\nown_fin<T> = (o: Own<T>) void { o.own_ptr().drop()  free(o.base) }\nFile*: { fd: i32 }\nfile_wrap = (fd: i32) Own<File> { own_new(File(fd: fd)) }\nfile_fd = (o: Own<File>) i32 { o.own_get().fd }\nFile.impl(Drop, { drop = (f: MutPtr<File>) void { close_obs(f.fd) } })\ntest* = () i32 {\n  o := file_wrap(7)\n  fd := o.file_fd()\n  o2 := o.own_clone()\n  o.own_release()\n  mid := g_closed\n  o2.own_release()\n  end := g_closed\n  fd + mid * 100 + end * 10\n}", 17),
    # ORC CYCLE COLLECTION (the TRACING half of ORC — std.trace; std.drop is the deterministic half).
    # Two refcounted Nodes point at each other (A.kid=B, B.kid=A): a CYCLE, unreachable from outside, whose
    # refcounts never reach 0 — std.drop alone LEAKS it. A synchronous Bacon–Rajan trial-deletion collects it:
    # mark-gray decrements internal counts via each node's `trace` (the keystone: a generic do_trace<T> /
    # Rc<T> dispatches the bare `.trace()` to impl_Trace_Node_trace after monomorphization); scan finds both
    # counts hit 0 ⇒ pure cycle garbage ⇒ white; gather+free_white finalize them. EACH Node impls Drop
    # (bumps g_dropped, dispatched via do_drop<T>), so after collect() g_dropped == 2 PROVES BOTH cycle
    # members were finalized — the leak is reclaimed. (std.trace, inlined; trace.zen is the canonical
    # @self-hosted-only form, acid-checked. Exercises both ORC traits — Trace AND Drop — through one Rc<T>.)
    ('malloc = (n: i64) RawPtr<u8>\nrealloc = (p: RawPtr<u8>, n: i64) RawPtr<u8>\nfree = (p: RawPtr<u8>) void\ng_freed := 0\ng_dropped := 0\nBLACK := 0\nGRAY  := 1\nWHITE := 2\nstore_ptr = (b: RawPtr<u8>, p: RawPtr<u8>) void { store_i64(b, p) }\nload_ptr = (b: RawPtr<u8>) RawPtr<u8> { load_i64(b).offset(0) }\nhcount = (b: RawPtr<u8>) i64 { load_i64(b.offset(0)) }\nhset_count = (b: RawPtr<u8>, v: i64) void { store_i64(b.offset(0), v) }\nhcolor = (b: RawPtr<u8>) i64 { load_i64(b.offset(8)) }\nhset_color = (b: RawPtr<u8>, v: i64) void { store_i64(b.offset(8), v) }\ng_white := null_ptr()\nlist_new = () RawPtr<u8> { l := malloc(16 + 64)  store_i64(l.offset(0), 0)  store_i64(l.offset(8), 8)  l }\nlist_len = (l: RawPtr<u8>) i64 { load_i64(l.offset(0)) }\nlist_get = (l: RawPtr<u8>, i: i64) RawPtr<u8> { load_ptr(l.offset(16 + i * 8)) }\nlist_push = (l: RawPtr<u8>, p: RawPtr<u8>) RawPtr<u8> {\n  n := list_len(l)\n  r := (n == load_i64(l.offset(8))).match({ true => { nc := load_i64(l.offset(8)) * 2  g := realloc(l, 16 + nc * 8)  store_i64(g.offset(8), nc)  g }, false => l })\n  store_ptr(r.offset(16 + n * 8), p)\n  store_i64(r.offset(0), n + 1)\n  r\n}\nroots := null_ptr()\nroots_list = () RawPtr<u8> {\n  (roots == null_ptr()).match({ true => { roots = list_new()  roots }, false => roots })\n}\nroots_add = (b: RawPtr<u8>) void { roots = roots_list().list_push(b) }\nroots_clear = () void { store_i64(roots_list().offset(0), 0) }\nTracer*: { op: i32 }\nTrace*: { trace: (Ptr<Self>, MutPtr<Tracer>) void }\nDrop*: { drop: (MutPtr<Self>) void }\nRc<T>: { base: RawPtr<u8> }\nrc_val<T> = (r: Rc<T>) [T] { slice(r.base.offset(16), 1) }\nrc_get<T> = (r: Rc<T>) T { r.rc_val()[0] }\nrc_base<T> = (r: Rc<T>) RawPtr<u8> { r.base }\nrc_new<T> = (x: T) Rc<T> {\n  base := malloc(16 + sizeof(T))\n  store_i64(base.offset(0), 0)\n  store_i64(base.offset(8), 0)\n  r := Rc<T>(base: base)\n  s := r.rc_val()\n  s[0] = x\n  r\n}\nrc_inc<T> = (r: Rc<T>) void { store_i64(r.base.offset(0), load_i64(r.base.offset(0)) + 1) }\ndo_drop<T> = (r: Rc<T>) void { s := r.rc_val()  addr(s[0]).drop() }\ndo_trace<T> = (r: Rc<T>, t: MutPtr<Tracer>) void {\n  s := r.rc_val()\n  addr(s[0]).trace(t)\n}\nvisit_child = (cb: RawPtr<u8>, t: MutPtr<Tracer>) void {\n  (t.op == 0).match({ true => { hset_count(cb, hcount(cb) - 1)  cc_mark(cb) }, false =>\n  (t.op == 1).match({ true => { cc_scan(cb) }, false =>\n  (t.op == 2).match({ true => { hset_count(cb, hcount(cb) + 1)  cc_scan_black(cb) }, false =>\n  { cc_gather(cb) } }) }) })\n}\ncc_mark = (b: RawPtr<u8>) void {\n  (hcolor(b) == GRAY).match({ true => {}, false => {\n    hset_color(b, GRAY)\n    mt := Tracer(op: 0)\n    blk_trace(b, addr(mt))\n  } })\n}\ncc_scan = (b: RawPtr<u8>) void {\n  (hcolor(b) == GRAY).match({ true => {\n    (hcount(b) > 0).match({ true => { cc_scan_black(b) }, false => {\n      hset_color(b, WHITE)\n      st := Tracer(op: 1)\n      blk_trace(b, addr(st))\n    } })\n  }, false => {} })\n}\ncc_scan_black = (b: RawPtr<u8>) void {\n  hset_color(b, BLACK)\n  bt := Tracer(op: 2)\n  blk_trace(b, addr(bt))\n}\ncc_gather = (b: RawPtr<u8>) void {\n  (hcolor(b) == WHITE).match({ true => {\n    hset_color(b, BLACK)\n    g_white = g_white.list_push(b)\n    gt := Tracer(op: 3)\n    blk_trace(b, addr(gt))\n  }, false => {} })\n}\nNode*: { has: i32, kid: RawPtr<u8> }\nNode.impl(Drop, { drop = (s: MutPtr<Node>) void { g_dropped = g_dropped + 1 } })\nNode.impl(Trace, { trace = (s: Ptr<Node>, t: MutPtr<Tracer>) void {\n  (s.has == 0).match({ true => {}, false => { visit_child(s.kid, t) } })\n} })\nblk_trace = (b: RawPtr<u8>, t: MutPtr<Tracer>) void { do_trace(Rc<Node>(base: b), t) }\nblk_drop = (b: RawPtr<u8>) void { do_drop(Rc<Node>(base: b)) }\nnode_set_kid = (parent: Rc<Node>, child: Rc<Node>) void {\n  p := parent.rc_val()\n  p[0] = Node(has: 1, kid: child.base)\n  child.rc_inc()\n}\ndrive = (op: i32, i: i64) void {\n  (i < roots_list().list_len()).match({ true => {\n    b := roots_list().list_get(i)\n    (op == 0).match({ true => { cc_mark(b) }, false =>\n    (op == 1).match({ true => { cc_scan(b) }, false =>\n    { cc_gather(b) } }) })\n    drive(op, i + 1)\n  }, false => {} })\n}\nfree_all = (i: i64) void {\n  (i < g_white.list_len()).match({ true => { g_freed = g_freed + 1  blk_drop(g_white.list_get(i))  free(g_white.list_get(i))  free_all(i + 1) }, false => {} })\n}\ncollect = () void {\n  g_white = list_new()\n  drive(0, 0)\n  drive(1, 0)\n  drive(2, 0)\n  free_all(0)\n  roots_clear()\n}\ntest* = () i32 {\n  a := rc_new(Node(has: 0, kid: null_ptr()))\n  b := rc_new(Node(has: 0, kid: null_ptr()))\n  node_set_kid(a, b)\n  node_set_kid(b, a)\n  roots_add(a.base)\n  roots_add(b.base)\n  collect()\n  g_dropped\n}', 2),
    # CAPSTONE (Goal Z, the whole thesis in one program): ONE Runtime trait unifies allocation AND
    # suspension { alloc, suspend }. The SAME generic task<R> — allocate a cell from R, fill it across a
    # suspend point — runs SYNC (Sync: alloc=malloc, suspend=no-op; straight through) and ASYNC (Async:
    # alloc=arena, suspend=coroutine-yield; driven by two resumes). Zero function coloring, one source,
    # memory + scheduling both chosen by the Runtime. 105 (sync) + 105 (async) = 210.
    ("getcontext  = (ctx: RawPtr<u8>) i32\nmakecontext = (ctx: RawPtr<u8>, fn: () void, argc: i32) void\nswapcontext = (out: RawPtr<u8>, inc: RawPtr<u8>) i32\nmalloc = (n: i64) RawPtr<u8>\ng_cur := null_ptr()\ng_back := null_ptr()\ng_flag := 0\ng_result := 0\nCoro*: { ctx: RawPtr<u8>, link: RawPtr<u8>, stack: RawPtr<u8> }\ncoro_new = (work: () void) Coro { stack := malloc(65536)  ctx := malloc(1024)  link := malloc(1024)  getcontext(ctx)  store_i64(ctx.offset(16), stack)  store_i64(ctx.offset(32), 65536)  store_i64(ctx.offset(8), link)  makecontext(ctx, work, 0)  Coro(ctx: ctx, link: link, stack: stack) }\ncoro_resume = (c: Coro) i32 { g_cur = c.ctx  g_back = c.link  g_flag = 0  swapcontext(c.link, c.ctx)  g_flag }\ncoro_yield = () void { g_flag = 1  swapcontext(g_cur, g_back) }\nRuntime*: { alloc: (MutPtr<Self>, i64) RawPtr<u8>, suspend: (MutPtr<Self>) void }\nSync*: { _: i32 }\nAsync*: { buf: RawPtr<u8>, off: i64 }\nSync.impl(Runtime, { alloc = (s: MutPtr<Sync>, n: i64) RawPtr<u8> { malloc(n) }\nsuspend = (s: MutPtr<Sync>) void { } })\nAsync.impl(Runtime, { alloc = (s: MutPtr<Async>, n: i64) RawPtr<u8> { p := s.buf.offset(s.off)  s.off = s.off + n  p }\nsuspend = (s: MutPtr<Async>) void { coro_yield() } })\ntask<R> = (r: MutPtr<R>) void { p := r.alloc(8)  store_i64(p, 5)  r.suspend()  store_i64(p, load_i64(p) + 100)  g_result = g_result + load_i64(p) }\nawork = () void { a := Async(buf: malloc(64), off: 0)  task(addr(a)) }\ntest* = () i32 {\n  sy := Sync(_: 0)\n  task(addr(sy))\n  c := coro_new(awork)\n  coro_resume(c)\n  coro_resume(c)\n  g_result\n}", 210),
    # COMMA-SEPARATED multi-method impl (harden): methods in `Type.impl(Trait, { m1 = f1, m2 = f2 })`
    # may be separated by a COMMA (like struct-literal fields), not only a newline. Before the fix the
    # second method's name became `,` (it emitted `impl_Runtime_Sync_,` and dispatch broke). Here a
    # two-method Runtime{alloc,suspend} is written with comma separators and BOTH methods dispatch:
    # alloc stores 5, suspend is a no-op, then 5+100=105. (Pairs with the newline-separated capstone.)
    ("malloc = (n: i64) RawPtr<u8>\nRuntime*: { alloc: (MutPtr<Self>, i64) RawPtr<u8>, suspend: (MutPtr<Self>) void }\nSync*: { _: i32 }\nSync.impl(Runtime, { alloc = (s: MutPtr<Sync>, n: i64) RawPtr<u8> { malloc(n) }, suspend = (s: MutPtr<Sync>) void { } })\ntask<R> = (r: MutPtr<R>) i64 { p := r.alloc(8)  store_i64(p, 5)  r.suspend()  store_i64(p, load_i64(p) + 100)  load_i64(p) }\ntest* = () i64 {\n  sy := Sync(_: 0)\n  task(addr(sy))\n}", 105),
    # the SAME impl with NEWLINE separators must still work (don't regress the existing convention).
    ("malloc = (n: i64) RawPtr<u8>\nRuntime*: { alloc: (MutPtr<Self>, i64) RawPtr<u8>, suspend: (MutPtr<Self>) void }\nSync*: { _: i32 }\nSync.impl(Runtime, { alloc = (s: MutPtr<Sync>, n: i64) RawPtr<u8> { malloc(n) }\nsuspend = (s: MutPtr<Sync>) void { } })\ntask<R> = (r: MutPtr<R>) i64 { p := r.alloc(8)  store_i64(p, 5)  r.suspend()  store_i64(p, load_i64(p) + 100)  load_i64(p) }\ntest* = () i64 {\n  sy := Sync(_: 0)\n  task(addr(sy))\n}", 105),
    # MULTI-STATEMENT BLOCK ARM (block-arm validator harden): a match arm body `{ s1  s2 }` runs BOTH
    # statements. The validator used to flag the parser's synthesized trailing-return on the block's
    # final expr as a "dropped return"; the emit was always correct. Here the `go == 1` true arm writes
    # two distinct slots (7 and 35); reading both back proves both statements executed. 7 + 35 = 42.
    ("malloc = (n: i64) RawPtr<u8>\nfill = (p: RawPtr<u8>, go: i32) void { (go == 1).match({ true => { store_i64(p.offset(0), 7)  store_i64(p.offset(8), 35) }, false => {} }) }\ntest* = () i64 {\n  p := malloc(64)\n  store_i64(p.offset(0), 0)\n  store_i64(p.offset(8), 0)\n  fill(p, 1)\n  load_i64(p.offset(0)) + load_i64(p.offset(8))\n}", 42),
    # the no-op (false) arm path: the SAME function with go != 1 leaves the slots at their primed 0s.
    ("malloc = (n: i64) RawPtr<u8>\nfill = (p: RawPtr<u8>, go: i32) void { (go == 1).match({ true => { store_i64(p.offset(0), 7)  store_i64(p.offset(8), 35) }, false => {} }) }\ntest* = () i64 {\n  p := malloc(64)\n  store_i64(p.offset(0), 0)\n  store_i64(p.offset(8), 0)\n  fill(p, 0)\n  load_i64(p.offset(0)) + load_i64(p.offset(8))\n}", 0),
    # an ENUM match with a multi-statement block arm (same harden, enum-with-payload form, so the lowering
    # uses a real tag test). .Ok(7) takes the first arm, writing 3 then 39 to the two slots; 3 + 39 = 42.
    ("R*: Ok(i32) | Err\nmalloc = (n: i64) RawPtr<u8>\nfill = (p: RawPtr<u8>, r: R) void { r.match({ .Ok(v) => { store_i64(p.offset(0), 3)  store_i64(p.offset(8), 39) }, .Err => {} }) }\ntest* = () i64 {\n  p := malloc(64)\n  store_i64(p.offset(0), 0)\n  store_i64(p.offset(8), 0)\n  fill(p, .Ok(7))\n  load_i64(p.offset(0)) + load_i64(p.offset(8))\n}", 42),
    # FILE + PROCESS I/O in Zen (std.io, Move-to-Zen Phase A) — the capability gap to a Python-free
    # build driver. These inline std.io's POSIX externs (open/read/write/close/lseek/system) + its
    # read_file/write_file/run_cmd mechanics, since run_value has no module resolver yet; io.zen itself
    # is acid-checked. The harness compiles+RUNS the emitted C against libc, so the FFI executes for
    # real — a file is written and read back. (POSIX fd calls, not the stdio FILE* family, so the
    # foreign prototypes don't collide with the <stdio.h> the value-printing harness includes.)
    #
    # 1) run_cmd("true") -> 0: `system` invokes a subprocess and returns its exit status.
    ("system = (cmd: str) i32\ntest* = () i32 { system(cstr(\"true\")) }", 0),
    # 2) write "ABC" with open/write, then read the first byte back -> 65 ('A'). The round-trip proves
    #    open(O_WRTRUNC)/write/close + open(O_RDONLY)/read/close all bind to libc and the bytes survive.
    #    577 = O_WRONLY|O_CREAT|O_TRUNC, 420 = 0o644 (io.zen's O_WRTRUNC / MODE_644).
    ("malloc = (n: i64) RawPtr<u8>\nopen = (path: str, flags: i32, mode: i32) i32\nwrite = (fd: i32, buf: RawPtr<u8>, n: i64) i64\nread = (fd: i32, buf: RawPtr<u8>, n: i64) i64\nclose = (fd: i32) i32\ntest* = () i32 {\n  wbuf := malloc(8)\n  store(offset(wbuf, 0), 'A')\n  store(offset(wbuf, 1), 'B')\n  store(offset(wbuf, 2), 'C')\n  wfd := open(cstr(\"/tmp/zen_io_diff_rt.txt\"), 577, 420)\n  write(wfd, wbuf, 3)\n  close(wfd)\n  rbuf := malloc(8)\n  rfd := open(cstr(\"/tmp/zen_io_diff_rt.txt\"), 0, 0)\n  read(rfd, rbuf, 3)\n  close(rfd)\n  load(offset(rbuf, 0))\n}", 65),
    # 3) read_file-style length: `system` creates a 3-byte file, then the file_size (lseek SEEK_END +
    #    rewind) + read + NUL-terminate path from io.zen's read_file reports length 3. `test` returns
    #    i64 (the length is an i64) so there's no narrowing — the harness reads it just the same.
    ("malloc = (n: i64) RawPtr<u8>\nsystem = (cmd: str) i32\nopen = (path: str, flags: i32, mode: i32) i32\nread = (fd: i32, buf: RawPtr<u8>, n: i64) i64\nclose = (fd: i32) i32\nlseek = (fd: i32, off: i64, whence: i32) i64\nread_len = (path: str) i64 {\n  fd := open(path, 0, 0)\n  n := lseek(fd, 0, 2)\n  lseek(fd, 0, 0)\n  buf := malloc(n + 1)\n  read(fd, buf, n)\n  store(offset(buf, n), 0)\n  close(fd)\n  n\n}\ntest* = () i64 {\n  system(cstr(\"printf ABC > /tmp/zen_io_diff_len.txt\"))\n  read_len(cstr(\"/tmp/zen_io_diff_len.txt\"))\n}", 3),
])
def test_self_hosted_computes_value(src, want):
    assert self_side(src)["value"] == want


# Block-arm validator harden (reject-parity side): a well-typed multi-statement block arm validates with
# ZERO errors (the false positive), but a genuinely-bad call INSIDE a block arm is still caught — the
# validator now recurses a value-position block arm's statements. self_side returns reject for these.
@pytest.mark.parametrize("src,verdict", [
    # well-typed multi-statement block arm -> accepted
    ("f* = (flags: RawPtr<u8>, i: i32, n: i32) void { (i < n).match({ true => { store_i64(flags, 1)  store_i64(flags, 2) }, false => {} }) }\ntest* = () i32 { 0 }", "accept"),
    # wrong-arity local call inside a block arm -> rejected
    ("g* = (x: i32) i32 { x }\nf* = (flags: RawPtr<u8>, i: i32, n: i32) void { (i < n).match({ true => { g(1, 2, 3)  store_i64(flags, 1) }, false => {} }) }\ntest* = () i32 { 0 }", "reject"),
    # mis-arity'd intrinsic inside a block arm -> rejected (store_i64 needs 2 args)
    ("f* = (flags: RawPtr<u8>, i: i32, n: i32) void { (i < n).match({ true => { store_i64(flags)  store_i64(flags, 1) }, false => {} }) }\ntest* = () i32 { 0 }", "reject"),
])
def test_block_arm_validation(src, verdict):
    assert self_side(src)["verdict"] == verdict, src


# Reject-parity: programs that emit UB or wrong C (false-accepts the checker must reject). The
# self-hosted CHECK binary must NOT accept these.
@pytest.mark.parametrize("src", [
    "test* = () i32 {  }",                         # empty body, non-void return -> no value (was accepted -> UB)
    "test* = () i32 {\n  x := 5\n}",               # body ends in a let -> no value (was accepted -> UB)
    "test* = () i32 {\n  x := 5\n  x = 6\n}",      # body ends in an assign -> no value
    'test* = () i32 { "hi" }',                     # trailing value is str, not i32
])
def test_self_hosted_rejects(src):
    assert self_side(src)["verdict"] == "reject", src


# Integer/literal match `(n).match({ 0 => …, 1 => …, _ => … })` — lowers to an equality-cond chain.
# Was: 3+ arms crashed the parser, 2-arm non-zero labels were silently mis-evaluated.
@pytest.mark.parametrize("src,want", [
    ("test* = () i32 { (2).match({ 0 => 10, 1 => 11, 2 => 12, _ => 99 }) }", 12),   # 4 arms (was SIGSEGV)
    ("test* = () i32 { (1).match({ 0 => 10, 1 => 11, _ => 20 }) }", 11),            # 3 arms (was rejected)
    ("test* = () i32 { (1).match({ 1 => 100, _ => 200 }) }", 100),                  # 2-arm non-zero (was 200)
    ("test* = () i32 { (9).match({ 0 => 10, 1 => 11, _ => 20 }) }", 20),            # default arm
    ("test* = () i32 { (3).match({ 0=>0, 1=>10, 2=>20, 3=>30, _=>99 }) }", 30),     # 5 arms
])
def test_integer_match(src, want):
    assert self_side(src)["value"] == want


# Member-target assignment `p.x = v` — was dropped entirely (the `= v` glued onto the next line),
# silently corrupting the return value. Assert the self-hosted value directly.
@pytest.mark.parametrize("src,want", [
    # the write is a dead store; trailing 5 is returned (was miscompiled to 99)
    ("P*: { x: i32 }\nf* = (p: P) i32 {\n p.x = 99\n 5\n}\ntest* = () i32 { f(P(x: 0)) }", 5),
    # the write happens, then read it back
    ("P*: { x: i32 }\nf* = (p: P) i32 {\n p.x = 99\n p.x\n}\ntest* = () i32 { f(P(x: 0)) }", 99),
    # bare-variable reassignment still works (regression)
    ("test* = () i32 {\n x := 5\n x = 7\n x\n}", 7),
    # write through a Ptr receiver (auto-deref -> p->x)
    ("P*: { x: i32 }\nbump* = (p: Ptr<P>) i32 {\n p.x = 42\n p.x\n}\ntest* = () i32 { q := P(x: 0)\n bump(addr(q)) }", 42),
    # nested field write a.b.c = v
    ("I*: { n: i32 }\nO*: { i: I }\nf* = (o: O) i32 {\n o.i.n = 42\n o.i.n\n}\ntest* = () i32 { f(O(i: I(n: 0))) }", 42),
])
def test_member_assignment(src, want):
    assert self_side(src)["value"] == want


# Large constructs (bug-hunt #15/#16): parser buffers were fixed at cap 64 (params/fields/arms/
# variants) and cap 16 (type args) and overflowed the heap with no bounds check. Caps are now
# generous (1024 / 256) so any plausible program fits safely.
def test_many_params():
    ps = ", ".join(f"p{i}: i32" for i in range(80))
    args = ", ".join(str(i) for i in range(80))
    assert self_side(f"f* = ({ps}) i32 {{ p79 }}\ntest* = () i32 {{ f({args}) }}")["value"] == 79

def test_many_fields():
    fs = ", ".join(f"x{i}: i32" for i in range(80))
    inits = ", ".join(f"x{i}: {i}" for i in range(80))
    assert self_side(f"S*: {{ {fs} }}\ntest* = () i32 {{ S({inits}).x79 }}")["value"] == 79

def test_many_match_arms():
    arms = ", ".join(f"{i} => {i*2}" for i in range(80)) + ", _ => 999"
    assert self_side(f"test* = () i32 {{ (50).match({{ {arms} }}) }}")["value"] == 100


# Early `return <value>` + guard / partial matches. A match used as a STATEMENT (its value
# discarded) lowers to `if` STATEMENTS so an arm's `return` actually leaves the function; a terminal
# bare `_` (≡ `_ => {}`) closes a partial match with a void no-op. A VALUE-position match stays the
# exhaustive ternary. Exhaustiveness is still enforced — a partial match WITHOUT `_` is rejected.
@pytest.mark.parametrize("src,want", [
    # bool guard: f(false) takes the `return 9`; f(true) falls through to the trailing 7
    ("f* = (b: bool) i32 {\n b.match({ false => { return 9 }, _ })\n 7\n}\ntest* = () i32 { f(false) }", 9),
    ("f* = (b: bool) i32 {\n b.match({ false => { return 9 }, _ })\n 7\n}\ntest* = () i32 { f(true) }", 7),
    ("f* = (b: bool) i32 {\n b.match({ true => { return 9 }, _ })\n 7\n}\ntest* = () i32 { f(true) }", 9),
    # enum error-guard: an early return out of one variant, the rest a no-op `_`
    ("R*: Ok(i32) | Err\nf* = (r: R) i32 {\n r.match({ .Err => { return 9 }, _ })\n 7\n}\ntest* = () i32 { f(.Err()) }", 9),
    ("R*: Ok(i32) | Err\nf* = (r: R) i32 {\n r.match({ .Err => { return 9 }, _ })\n 7\n}\ntest* = () i32 { f(.Ok(0)) }", 7),
    # enum guard binding the payload: `.Err(e) => { return e }`
    ("R*: Ok(i32) | Err(i32)\nf* = (r: R) i32 {\n r.match({ .Err(e) => { return e }, _ })\n 7\n}\ntest* = () i32 { f(.Err(42)) }", 42),
    # literal guard if-chain with assigns + terminal bare `_`
    ("f* = (n: i32) i32 {\n x := 0\n n.match({ 0 => { x = 1 }, 1 => { x = 2 }, _ })\n x\n}\ntest* = () i32 { f(0)*100 + f(1)*10 + f(9) }", 120),
    # a FULLY EXHAUSTIVE statement-position enum match (no `_`) with returns still lowers + works
    ("R*: Ok(i32) | Err\nf* = (r: R) i32 {\n r.match({ .Ok(v) => { return v }, .Err => { return 9 } })\n 0\n}\ntest* = () i32 { f(.Ok(5)) + f(.Err()) }", 14),
])
def test_guard_early_return(src, want):
    assert self_side(src)["value"] == want, src


# Exhaustiveness stays enforced: a partial STATEMENT match WITHOUT a terminal `_` must be rejected
# (no implicit fall-through). The `_` is what licenses a subset of cases.
@pytest.mark.parametrize("src", [
    # partial enum match, no `_` — missing .Ok
    "R*: Ok(i32) | Err\nf* = (r: R) i32 {\n r.match({ .Err => { return 9 } })\n 7\n}\ntest* = () i32 { f(.Ok(0)) }",
    # partial bool match, no `_` — only the false arm
    "f* = (b: bool) i32 {\n b.match({ false => { return 9 } })\n 7\n}\ntest* = () i32 { f(false) }",
])
def test_partial_match_without_wildcard_rejected(src):
    assert self_side(src)["verdict"] == "reject", src


@pytest.mark.parametrize("src", [
    "f* = (b: bool) i32 {\n if (b) { return 9 }\n 7\n}\ntest* = () i32 { f(true) }",
    "f* = (b: bool) i32 {\n if (b) { return 9 } else { return 8 }\n 7\n}\ntest* = () i32 { f(false) }",
])
def test_source_if_rejected(src):
    assert self_side(src)["verdict"] == "reject", src


# A VALUE-position match arm with an EARLY (non-trailing) `return` is rejected. A value-position match
# lowers to a `({…})`/ternary; the emitter (genc's ret_to_expr) makes the block's TRAILING statement the
# yielded value, but an EARLY `return` mid-block is turned into a bare `e;` and silently dropped — so
# control never leaves the function and the WRONG (later) expr is yielded. Here `{ return x  x + 1 }`
# would drop `return x` and yield `x + 1`. Guard returns must be STATEMENT-position (those lower to real
# `if`, tested above). So reject early value-position returns. (C-audit #7; block-arm harden.)
@pytest.mark.parametrize("src", [
    "R*: Ok(i32) | Err(i32)\nf* = (r: R) i32 {\n v := r.match({ .Ok(x) => { return x  x + 1 }, .Err(e) => e })\n v + 1\n}\ntest* = () i32 { f(.Ok(5)) }",
    "f* = (b: bool) i32 {\n v := b.match({ true => { return 7  9 }, false => 0 })\n v\n}\ntest* = () i32 { f(true) }",
])
def test_value_position_return_rejected(src):
    assert self_side(src)["verdict"] == "reject", src


# The dual of the above: a value-position arm whose block ends in a TRAILING `return` (or a bare trailing
# expr) is the block's yielded value — genc emits it correctly, so it is ACCEPTED and computes the right
# value. `{ return x }` and `{ x }` are AST-identical (the parser wraps a block's final expr in a Return);
# only an EARLY return is the dropped-guard bug. This is the false-positive the block-arm harden removed.
@pytest.mark.parametrize("src,want", [
    ("R*: Ok(i32) | Err(i32)\nf* = (r: R) i32 {\n v := r.match({ .Ok(x) => { return x }, .Err(e) => e })\n v + 1\n}\ntest* = () i32 { f(.Ok(5)) }", 6),
    ("f* = (b: bool) i32 {\n v := b.match({ true => { 7 }, false => 0 })\n v\n}\ntest* = () i32 { f(true) }", 7),
])
def test_value_position_trailing_yield_accepted(src, want):
    d = self_side(src)
    assert d["verdict"] == "accept" and d["value"] == want, (src, d)


# Two top-level decls with the same FUNCTION name emit colliding C definitions (cc "redefinition" /
# "conflicting types"). The self-hosted backend doesn't mangle plain fn names, so the checker must
# reject duplicates before C emission. Zen has no overloading. (#5.)
@pytest.mark.parametrize("src", [
    "foo* = () i32 { 1 }\nfoo* = () i32 { 2 }\ntest* = () i32 { foo() }",
    "a* = () i32 { 1 }\ndup* = () i32 { 2 }\ndup* = () i32 { 3 }\ntest* = () i32 { a() }",
])
def test_duplicate_function_name_rejected(src):
    assert self_side(src)["verdict"] == "reject", src
