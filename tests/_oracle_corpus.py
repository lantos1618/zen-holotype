"""Golden corpus for the self-hosted-compiler oracle — single-sourced expected verdicts/values.

Migrated from test_differential.py's parametrize lists. This module imports NOTHING (no zen.*) — it is
pure data, so the oracle tests that read it have ZERO Python-frontend dependency after Stage D deleted
zen/*.py. These golden expectations are what keeps coverage.

  VALUE_CASES   : [(src, want_int)]   — the self-hosted binary must COMPUTE want
  VERDICT_CASES : [(src, "accept"|"reject")] — the check binary must produce that verdict
  VERDICT_KIND_CASES : [(src, kind)]  — a REJECT pinned by its first-error KIND (not just "reject"),
                                        so a reject-for-the-wrong-reason is caught (Diagnostics arc).
"""

# (src, want) the self-hosted toolchain must compute exactly (silent-miscompile guards).
VALUE_CASES = [

# --- test_self_hosted_computes_value ---
    ('test* = () i64 { 10000000000 / 10 }', 1000000000),
    ('test* = () i64 { 9999999999 - 9999999990 }', 9),
    ('test* = () i64 { 5000000000 + 5000000000 }', 10000000000),
    ('test* = () i32 {\n  1 + /* outer /* inner */ still-comment */ 41\n}', 42),
    ('test* = () i32 { 3 + /* plain */ 4 }', 7),
    ("bad* = () i32 { 'ab' }\ntest* = () i32 { 5 }", 5),
    ("test* = () i32 { 'A' }", 65),
    ('test* = () i32 {\n  x := 7\n  [1]\n  x\n}', 7),
    ('test* = () i32 {\n  [9, 9]\n  1 + 2\n}', 3),
    ('test* = () i32 {\n  s := [10, 20, 30]\n  s[2]\n}', 30),
    ('Box<T>: { v: T }\nwrap<T> = (x: T) Box<T> { Box<T>(v: x) }\nget<T> = (b: Box<T>) i32 { b.v }\ntest* = () i32 {\n  n := 5\n  get(wrap(n))\n}', 5),
    ('Box<T>: { v: T }\nwrap<T> = (x: T) Box<T> { Box<T>(v: x) }\nget<T> = (b: Box<T>) i32 { b.v }\ntest* = () i32 {\n  n := 9\n  w := wrap(n)\n  get(w)\n}', 9),
    ('Opt<T>: Some(T) | None\ntest* = () i32 { (.Some(5)).match({ .Some(x) => x, .None => 0 }) }', 5),
    ('Opt<T>: Some(T) | None\ntest* = () i32 {\n  o := .Some(7)\n  o.match({ .Some(x) => x, .None => 0 })\n}', 7),
    ('Opt<T>: Some(T) | None\nmk<T> = (x: T) Opt<T> { .Some(x) }\ntest* = () i32 { mk(8).match({ .Some(x) => x, .None => 0 }) }', 8),
    ('Opt<T>: Some(T) | None\none<T> = (x: T) Opt<T> { .None }\ntest* = () i32 { one(5).match({ .Some(x) => x, .None => 3 }) }', 3),
    ('Opt<T>: Some(T) | None\npick<T> = (x: T, b: i32) Opt<T> { (b == 1).match({ true => .Some(x), false => .None }) }\ntest* = () i32 { pick(9, 0).match({ .Some(x) => x, .None => 3 }) }', 3),
    ('Opt<T>: Some(T) | None\nunwrap<T> = (o: Opt<T>, d: T) T { o.match({ .Some(x) => x, .None => d }) }\ntest* = () i32 {\n  o := .Some(7)\n  unwrap(o, 0)\n}', 7),
    ('first<T> = (xs: [T]) T { xs[0] }\ntest* = () i32 { first([7, 8]) }', 7),
    ('pick2<T> = (xs: [T], a: T) T { xs[1] + a }\ntest* = () i32 { pick2([3, 4], 5) }', 9),
    # --- VARIADIC PARAMS: a trailing `...T` collects the surplus call args into a `[T]` slice ---
    ('sum = (xs: ...i32) i32 { t := 0  xs.loop((h, i, x) { t = t + x })  t }\ntest* = () i32 { sum(1, 2, 3, 4) }', 10),
    ('sum = (xs: ...i32) i32 { t := 0  xs.loop((h, i, x) { t = t + x })  t }\ntest* = () i32 { sum() }', 0),
    ('sum = (xs: ...i32) i32 { t := 0  xs.loop((h, i, x) { t = t + x })  t }\ntest* = () i32 { sum(7) }', 7),
    # a fixed param BEFORE the variadic one: base + collected sum
    ('addv = (base: i32, xs: ...i32) i32 { t := base  xs.loop((h, i, x) { t = t + x })  t }\ntest* = () i32 { addv(100, 1, 2, 3) }', 106),
    # str varargs after a fixed str: the body counts the collected names
    ('join = (sep: str, xs: ...str) i32 { n := 0  xs.loop((h, i, x) { n = n + 1 })  n }\ntest* = () i32 { join(", ", "a", "b") }', 2),
    # varargs of a STRUCT type (the motivating DSL case: div(child, child, ...))
    ('Node*: { tag: i32, val: i32 }\ndiv = (kids: ...Node) i32 { s := 0  kids.loop((h, i, c) { s = s + c.val })  s }\ntest* = () i32 { div(Node(tag: 1, val: 10), Node(tag: 2, val: 20)) }', 30),
    ('Box<T>: { v: T }\nmk<T> = (x: T) Box<T> { Box<T>(v: x) }\nget<T> = (b: Box<T>) T { b.v }\ntest* = () i32 {\n  b := mk(42)\n  b.get()\n}', 42),
    # --- RECURSIVE GENERIC FUNCTIONS: monomorphized per concrete instance (not inlined) ---
    # value-tparam recursion returning the tparam
    ('idn<T> = (x: T, n: i32) T { (n <= 0).match({ true => x, false => idn(x, n - 1) }) }\ntest* = () i32 { idn(42, 5) }', 42),
    # pointer-receiver recursive generic (the canonical `(a: MutPtr<A>)` self-call form)
    ('C*: { z: i32 }\nsumv<A> = (a: MutPtr<A>, xs: [i32], i: i64, acc: i32) i32 { (i >= xs.len).match({ true => acc, false => a.sumv(xs, i + 1, acc + xs[i]) }) }\ntest* = () i32 {\n  c := C(z: 0)\n  c.addr().sumv([1, 2, 3, 4], 0, 0)\n}', 10),
    # recursive generic whose RETURN type is itself a generic (Box<T>), constructed in the body
    ('Box<T>: { v: T }\nboxn<T> = (x: T, n: i32) Box<T> { (n <= 0).match({ true => Box<T>(v: x), false => boxn(x, n - 1) }) }\ntest* = () i32 { boxn(7, 3).v }', 7),
    # --- BARE generic-struct construction: infer the type arg (no explicit `<…>`) ---
    # form (1): infer S from the field value
    ('Store<S>: { state: S }\nAppState: { count: i32 }\ntest* = () i32 {\n  st := Store(state: AppState(count: 5))\n  st.state.count\n}', 5),
    # form (2): infer S from the LHS type annotation
    ('Store<S>: { state: S }\nAppState: { count: i32 }\ntest* = () i32 {\n  st: Store<AppState> := Store(state: AppState(count: 5))\n  st.state.count\n}', 5),
    # form (3): explicit type arg still works (regression guard)
    ('Store<S>: { state: S }\nAppState: { count: i32 }\ntest* = () i32 {\n  st := Store<AppState>(state: AppState(count: 5))\n  st.state.count\n}', 5),
    # multi-tparam inferred from field values
    ('Pair<A, B>: { a: A, b: B }\ntest* = () i32 {\n  p := Pair(a: 7, b: 9)\n  p.a + p.b\n}', 16),
    # --- std.state.store shape: a Redux-style store + a pure reducer TRAIT + generic dispatch.
    #     A value type IS its own reducer (Self == state); dispatch folds an action through it
    #     in place via MutPtr field-write. Asserts count after Inc/Add(10)/Dec == 10. ---
    ('Reducer<A>: { reduce: (Self, A) Self }\nStore<S>: { state: S }\nAppState: { count: i32, clicks: i32 }\nAction: Inc | Dec | Add(i32)\nAppState.impl(Reducer<Action>, { reduce = (s: AppState, a: Action) AppState { a.match({ .Inc => AppState(count: s.count + 1, clicks: s.clicks + 1), .Dec => AppState(count: s.count - 1, clicks: s.clicks + 1), .Add(n) => AppState(count: s.count + n, clicks: s.clicks + 1) }) } })\ndispatch<S, A> = (st: MutPtr<Store<S>>, a: A) void { st.state = st.state.reduce(a) }\ntest* = () i32 {\n  st := Store(state: AppState(count: 0, clicks: 0))\n  p := st.addr()\n  dispatch(p, Action.Inc)\n  dispatch(p, Action.Add(10))\n  dispatch(p, Action.Dec)\n  st.state.count\n}', 10),
    # --- GENERIC DISPATCH on a STATEMENT-MATCH payload binding: the lowered binding must be TYPED so
    #     the generic call (trait dispatch) monomorphizes (was: link error, undefined trait method) ---
    ('Cell*: { x: i64 }\nDoubler*: { dbl: (Self) i64 }\ni64.impl(Doubler, { dbl = (n: i64) i64 { n * 2 } })\napply<T> = (x: T) i64 { x.dbl() }\nE*: Num(i64) | Add(i64)\ntest* = () i64 {\n  c := Cell(x: 0)\n  e := E.Num(21)\n  e.match({ .Num(n) => store_i64(c.addr(), apply(n)), .Add(m) => store_i64(c.addr(), apply(m)) })\n  load_i64(c.addr())\n}', 42),
    # same, but the generic call is on a MEMBER of the payload binding (`apply(ps.len)`)
    ('Cell*: { x: i64 }\nDoubler*: { dbl: (Self) i64 }\ni64.impl(Doubler, { dbl = (n: i64) i64 { n * 2 } })\napply<T> = (x: T) i64 { x.dbl() }\nW*: Obj([i32]) | None\ntest* = () i64 {\n  c := Cell(x: 0)\n  w := W.Obj([10, 20, 30])\n  w.match({ .Obj(ps) => store_i64(c.addr(), apply(ps.len)), .None => store_i64(c.addr(), 0-1) })\n  load_i64(c.addr())\n}', 6),
    # STATEMENT-position match whose SUBJECT is an enclosing arm's payload binding (`.Bin(bo)` then
    # `bo.match(...)` on the RHS of `=`): the binding must be TYPED so the inner match recovers `bo`'s
    # enum name and emits qualified case labels (`B_OpAdd`, not bare `_OpAdd` → cc undeclared).
    ('B*: OpAdd | OpSub\nO*: Bin(B)\nf = (op: O) i32 { r := 0  op.match({ .Bin(bo) => { r = bo.match({ .OpAdd => 1, .OpSub => 2 }) } })  r }\ntest* = () i32 { f(O.Bin(B.OpSub)) }', 2),
    # --- ENUM `==`/`!=`: lower to a TAG comparison (raw struct == is invalid C) ---
    ('State*: Idle | Run(i32)\ntest* = () i32 {\n  a := State.Idle\n  b := State.Idle\n  r := (a == b).to_i32()\n  r\n}', 1),
    ('State*: Idle | Run(i32)\ntest* = () i32 {\n  a := State.Idle\n  b := State.Run(5)\n  r := (a != b).to_i32()\n  r\n}', 1),
    # `==` against a variant literal (different tag → 0)
    ('State*: Idle | Run(i32)\ntest* = () i32 {\n  a := State.Run(2)\n  r := (a == State.Idle).to_i32()\n  r\n}', 0),
    # --- bare variant ctor arg to a GENERIC fn: the inferred type arg disambiguates which enum owns
    #     the shared variant name (`.Num` exists on both Tok and Expr; T=Tok from the other arg) ---
    ('Tok*: Num(i64) | End\nExpr*: Num(i64) | Bin(i64)\nsecond<T> = (a: T, b: T) T { b }\nunNum = (t: Tok) i64 { t.match({ .Num(n) => n, .End => 0-1 }) }\ntest* = () i64 {\n  base := Tok.End\n  r := second(base, .Num(7))\n  unNum(r)\n}', 7),
    # --- a lambda bound to a LOCAL (`g := (n){…}`) is a compile-time alias: spliced at each use (HOF
    #     arg + direct call), captures the enclosing scope, reused — no zen__unlowered_lambda / undef ---
    ('apply = (f: (i32) i32, x: i32) i32 { f(x) }\ntest* = () i32 {\n  k := 10\n  g := (n) { n + k }\n  apply(g, 41) + apply(g, 2)\n}', 63),
    ('twice = (f: (i32) i32, x: i32) i32 { f(f(x)) }\ntest* = () i32 {\n  g := (n) { n + 3 }\n  twice(g, 1)\n}', 7),
    ('Vec<T>: { ptr: RawPtr<u8>, len: i64, cap: i64 }\nmalloc = (n: i64) RawPtr<u8>\nbuf<T> = (v: Vec<T>) [T] { slice(v.ptr, v.cap) }\nget<T> = (v: Vec<T>, i: i64) T { v.buf()[i] }\nof<T> = (xs: [T]) Vec<T> {\n  v := Vec<T>(ptr: malloc(xs.len * sizeof(T)), len: xs.len, cap: xs.len)\n  b := v.buf()\n  xs.loop((h, i, x) { b[i] = x })\n  v\n}\ntest* = () i32 {\n  v := of([10, 20, 30])\n  v.get(0) + v.get(2)\n}', 40),
    # --- generic in-place sort with an INLINE-LAMBDA comparator (std.collections.iter.sort shape):
    #     the comparator `less` is invoked DIRECTLY inside the generic fn's nested loops (never
    #     forwarded to a helper, which would leave a `zen__unlowered_lambda`), so it splices like fold.
    ('srt<T> = (xs: [T], less: (T, T) bool) void {\n  xs.loop((ho, i, e) {\n    xs.loop((hi, k, e2) {\n      j := i - k\n      (j <= 0).match ({\n        true  => { hi.break },\n        false => less(xs[j], xs[j - 1]).match ({\n          true => { tmp := xs[j]  xs[j] = xs[j - 1]  xs[j - 1] = tmp },\n          false => { hi.break }\n        })\n      })\n    })\n  })\n}\ntest* = () i32 {\n  xs := [3, 1, 2, 5, 4]\n  xs.srt((a, b){ a < b })\n  (xs[0] * 10000) + (xs[1] * 1000) + (xs[2] * 100) + (xs[3] * 10) + xs[4]\n}', 12345),
    # same sort, DESCENDING comparator (a > b) → [5,4,3,2,1]
    ('srt<T> = (xs: [T], less: (T, T) bool) void {\n  xs.loop((ho, i, e) {\n    xs.loop((hi, k, e2) {\n      j := i - k\n      (j <= 0).match ({\n        true  => { hi.break },\n        false => less(xs[j], xs[j - 1]).match ({\n          true => { tmp := xs[j]  xs[j] = xs[j - 1]  xs[j - 1] = tmp },\n          false => { hi.break }\n        })\n      })\n    })\n  })\n}\ntest* = () i32 {\n  xs := [3, 1, 2, 5, 4]\n  xs.srt((a, b){ a > b })\n  (xs[0] * 10000) + (xs[1] * 1000) + (xs[2] * 100) + (xs[3] * 10) + xs[4]\n}', 54321),
    # --- zero-element generic constructor whose T comes from the LHS annotation (std.collections
    #     Vec/Map `empty` shape): `v: Vec<i32> := empty()` infers T=i32 with no seed arg, then push/get.
    ('Vec<T>: { ptr: RawPtr<u8>, len: i64, cap: i64 }\nmalloc = (n: i64) RawPtr<u8>\nbuf<T> = (v: Vec<T>) [T] { slice(v.ptr, v.cap) }\nempty<T> = () Vec<T> { Vec<T>(ptr: malloc(sizeof(T)), len: 0, cap: 1) }\npush<T> = (v: Vec<T>, x: T) Vec<T> { b := v.buf()  b[v.len] = x  Vec<T>(ptr: v.ptr, len: v.len + 1, cap: v.cap) }\nget<T> = (v: Vec<T>, i: i64) T { v.buf()[i] }\ntest* = () i32 {\n  v: Vec<i32> := empty()\n  v = v.push(42)\n  v.get(0)\n}', 42),
    # --- pair-iteration: a generic struct METHOD takes a 2-arg fn param and invokes an INLINE LAMBDA
    #     directly (std.collections.map.each_pair shape — visits key+value together), mutating an
    #     outer-scope local through the closure. Splices like iter.each; no zen__unlowered_lambda.
    ('Pairs<T>: { ks: [str], vs: [T]\n    each_pair = (p: Pairs<T>, f: (str, T) void) void {\n        p.ks.loop((h, i, k) { f(k, p.vs[i]) })\n    }\n}\ntest* = () i32 {\n    p := Pairs<i32>(ks: ["a", "b", "c"], vs: [10, 20, 30])\n    s := 0\n    p.each_pair((k, v){ s = s + v })\n    s\n}', 60),
    ('Opt<T>: Some(T) | None\nu<T> = (o: Opt<T>) i32 { o.match({ .Some(x) => 1, .None => 0 }) }\ntest* = () i32 { u(.Some(42)) }', 1),
    ('Opt<T>: Some(T) | None\nunwrap<T> = (o: Opt<T>, d: T) T { o.match({ .Some(x) => x, .None => d }) }\ntest* = () i32 { unwrap(.Some(7), 0) }', 7),
    ('A*: { v: i32 }\nB*: { v: i32 }\nShow*: { area: (Ptr<Self>) i32 }\nA.impl(Show, { area = (a: Ptr<A>) i32 { a.v } })\nB.impl(Show, { area = (b: Ptr<B>) i32 { b.v * b.v } })\ntest* = () i32 {\n  a := A(v: 5)\n  b := B(v: 6)\n  a.addr().area() + b.addr().area()\n}', 41),
    ('P*: { x: i32 }\nQ*: { x: i32 }\nDbl*: { f: (Ptr<Self>, i32) i32 }\nP.impl(Dbl, { f = (p: Ptr<P>, k: i32) i32 { p.x + k } })\nQ.impl(Dbl, { f = (q: Ptr<Q>, k: i32) i32 { q.x * k } })\ntest* = () i32 {\n  p := P(x: 10)\n  q := Q(x: 3)\n  p.addr().f(2) + q.addr().f(4)\n}', 24),
    # --- TRAIT DEFAULT METHODS: a trait method with a body; one type inherits it, another overrides it ---
    ('Show*: { area = (s: Ptr<Self>) i32 { 100 } }\nA*: { v: i32 }\nB*: { v: i32 }\nA.impl(Show, { })\nB.impl(Show, { area = (b: Ptr<B>) i32 { b.v * b.v } })\ntest* = () i32 {\n  a := A(v: 5)\n  b := B(v: 6)\n  a.addr().area() + b.addr().area()\n}', 136),
    # default body reads a field on the concrete receiver (Self -> A, member auto-derefs to ->)
    ('Show*: { area = (s: Ptr<Self>) i32 { s.v + 1 } }\nA*: { v: i32 }\nA.impl(Show, { })\ntest* = () i32 { a := A(v: 41)  a.addr().area() }', 42),
    # one trait, two defaults, an override of just one; the other default still dispatches
    ('T*: { a = (s: Ptr<Self>) i32 { 1 }, b = (s: Ptr<Self>) i32 { 2 } }\nN*: { v: i32 }\nN.impl(T, { b = (s: Ptr<N>) i32 { 20 } })\ntest* = () i32 { n := N(v: 0)  n.addr().a() * 100 + n.addr().b() }', 120),
    # NEWLINE-separated defaults; a default body that CALLS another (omitted) defaulted method on Self
    ('Greet*: {\n  name = (s: Ptr<Self>) i32 { 7 }\n  greet = (s: Ptr<Self>) i32 { s.name() + 1 }\n}\nP*: { v: i32 }\nP.impl(Greet, { })\ntest* = () i32 { p := P(v: 0)  p.addr().greet() }', 8),
    # a default dispatched through a GENERIC receiver, monomorphized per concrete type (Heap default, Bump override)
    ('malloc = (n: i64) RawPtr<u8>\nAlloc*: { acquire = (s: MutPtr<Self>, n: i64) RawPtr<u8> { malloc(n) } }\nHeap*: { _: i32 }\nBump*: { buf: RawPtr<u8>, off: i64 }\nHeap.impl(Alloc, { })\nBump.impl(Alloc, { acquire = (s: MutPtr<Bump>, n: i64) RawPtr<u8> { p := s.buf.offset(s.off)  s.off = s.off + n  p } })\nfill<A> = (a: MutPtr<A>) i64 { p := a.acquire(8)  store_i64(p, 21)  q := a.acquire(8)  store_i64(q, 21)  load_i64(p) + load_i64(q) }\ntest* = () i32 {\n  h := Heap(_: 0)\n  b := Bump(buf: malloc(64), off: 0)\n  to_i32(fill(h.addr()) + fill(b.addr()) + b.off)\n}', 100),
    ('counter := 0\nbump* = () i32 { counter = counter + 1  counter }\ntest* = () i32 { bump() + bump() }', 3),
    ('total := 100\nadd* = (n: i32) i32 { total = total + n  total }\ntest* = () i32 { add(5)  add(20) }', 125),
    ('Cell*: { x: i64 }\ntest* = () i64 { c := Cell(x: 0)  store_i64(c.addr(), 42)  load_i64(c.addr()) }', 42),
    ('Arena*: { buf: RawPtr<u8>, off: i64, cap: i64 }\nmalloc = (n: i64) RawPtr<u8>\nan* = (cap: i64) Arena { Arena(buf: malloc(cap), off: 0, cap: cap) }\nbump* = (a: MutPtr<Arena>, n: i64) RawPtr<u8> { p := a.buf.offset(a.off)  a.off = a.off + n  p }\ntest* = () i64 {\n  a := an(64)\n  p := a.addr().bump(8)\n  store_i64(p, 99)\n  q := a.addr().bump(8)\n  store_i64(q, 1)\n  load_i64(p) + load_i64(q)\n}', 100),
    ('Cell*: { x: i64 }\nset = (c: MutPtr<Cell>, n: i64) void { (n == 0).match({ true => {}, false => store_i64(c, n) }) }\ntest* = () i64 {\n  c := Cell(x: 1)\n  set(c.addr(), 0)\n  set(c.addr(), 9)\n  load_i64(c.addr())\n}', 9),
    ('Rc<T>: { base: RawPtr<u8> }\nmalloc = (n: i64) RawPtr<u8>\nfree = (p: RawPtr<u8>) void\nrc_val<T> = (r: Rc<T>) [T] { slice(r.base.offset(8), 1) }\nrc_new<T> = (x: T) Rc<T> { base := malloc(8 + sizeof(T))  store_i64(base, 1)  r := Rc<T>(base: base)  s := r.rc_val()  s[0] = x  r }\nrc_get<T> = (r: Rc<T>) T { r.rc_val()[0] }\nrc_clone<T> = (r: Rc<T>) Rc<T> { store_i64(r.base, load_i64(r.base) + 1)  Rc<T>(base: r.base) }\nrc_drop<T> = (r: Rc<T>) void { n := load_i64(r.base) - 1  store_i64(r.base, n)  (n == 0).match({ true => free(r.base), false => {} }) }\nrc_count<T> = (r: Rc<T>) i64 { load_i64(r.base) }\ntest* = () i64 {\n  r := rc_new(42)\n  r2 := r.rc_clone()\n  a := r.rc_count()\n  r.rc_drop()\n  b := r.rc_count()\n  v := r.rc_get()\n  a * 100 + b * 10 + v\n}', 252),
    ('getcontext  = (ctx: RawPtr<u8>) i32\nmakecontext = (ctx: RawPtr<u8>, fn: () void, argc: i32) void\nswapcontext = (out: RawPtr<u8>, inc: RawPtr<u8>) i32\nmalloc = (n: i64) RawPtr<u8>\ng_cur := null_ptr()\ng_link := null_ptr()\ng_paused := 0\ng_n := 0\nCoro*: { ctx: RawPtr<u8>, link: RawPtr<u8>, stack: RawPtr<u8> }\ncoro_new = (work: () void) Coro {\n  stack := malloc(65536)\n  ctx := malloc(1024)\n  link := malloc(1024)\n  getcontext(ctx)\n  store_i64(ctx.offset(16), stack)\n  store_i64(ctx.offset(32), 65536)\n  store_i64(ctx.offset(8), link)\n  makecontext(ctx, work, 0)\n  Coro(ctx: ctx, link: link, stack: stack)\n}\ncoro_resume = (c: Coro) i32 { g_cur = c.ctx  g_link = c.link  g_paused = 0  swapcontext(c.link, c.ctx)  g_paused }\ncoro_checkpoint = () void { g_paused = 1  swapcontext(g_cur, g_link) }\nwork = () void { g_n = g_n + 1  coro_checkpoint()  g_n = g_n + 10  coro_checkpoint()  g_n = g_n + 100 }\ntest* = () i32 { c := coro_new(work)  r1 := coro_resume(c)  r2 := coro_resume(c)  r3 := coro_resume(c)  g_n * 10 + r1 + r2 + r3 }', 1112),
    ('getcontext  = (ctx: RawPtr<u8>) i32\nmakecontext = (ctx: RawPtr<u8>, fn: () void, argc: i32) void\nswapcontext = (out: RawPtr<u8>, inc: RawPtr<u8>) i32\nmalloc = (n: i64) RawPtr<u8>\ng_cur := null_ptr()\ng_back := null_ptr()\ng_flag := 0\ng_n := 0\nCoro*: { ctx: RawPtr<u8>, link: RawPtr<u8>, stack: RawPtr<u8> }\ncoro_new = (work: () void) Coro {\n  stack := malloc(65536)\n  ctx := malloc(1024)\n  link := malloc(1024)\n  getcontext(ctx)\n  store_i64(ctx.offset(16), stack)\n  store_i64(ctx.offset(32), 65536)\n  store_i64(ctx.offset(8), link)\n  makecontext(ctx, work, 0)\n  Coro(ctx: ctx, link: link, stack: stack)\n}\ncoro_resume = (c: Coro) i32 { g_cur = c.ctx  g_back = c.link  g_flag = 0  swapcontext(c.link, c.ctx)  g_flag }\ncoro_checkpoint = () void { g_flag = 1  swapcontext(g_cur, g_back) }\nRuntime*: { checkpoint: (Ptr<Self>) void }\nSync*: { _: i32 }\nAsync*: { _: i32 }\nSync.impl(Runtime, { checkpoint = (s: Ptr<Sync>) void { } })\nAsync.impl(Runtime, { checkpoint = (a: Ptr<Async>) void { coro_checkpoint() } })\nworker<R> = (r: Ptr<R>) void { g_n = g_n + 1  r.checkpoint()  g_n = g_n + 10  r.checkpoint()  g_n = g_n + 100 }\nawork = () void { a := Async(_: 0)  worker(a.addr()) }\ntest* = () i32 {\n  s := Sync(_: 0)\n  worker(s.addr())\n  sync_n := g_n\n  g_n = 0\n  c := coro_new(awork)\n  coro_resume(c)\n  coro_resume(c)\n  coro_resume(c)\n  sync_n * 1000 + g_n\n}', 111111),
    ('getcontext  = (ctx: RawPtr<u8>) i32\nmakecontext = (ctx: RawPtr<u8>, fn: () void, argc: i32) void\nswapcontext = (out: RawPtr<u8>, inc: RawPtr<u8>) i32\nmalloc = (n: i64) RawPtr<u8>\ng_cur := null_ptr()\ng_back := null_ptr()\ng_flag := 0\ng_log := 0\nCoro*: { ctx: RawPtr<u8>, link: RawPtr<u8>, stack: RawPtr<u8> }\ncoro_new = (work: () void) Coro { stack := malloc(65536)  ctx := malloc(1024)  link := malloc(1024)  getcontext(ctx)  store_i64(ctx.offset(16), stack)  store_i64(ctx.offset(32), 65536)  store_i64(ctx.offset(8), link)  makecontext(ctx, work, 0)  Coro(ctx: ctx, link: link, stack: stack) }\nresume = (c: Coro) i32 { g_cur = c.ctx  g_back = c.link  g_flag = 0  swapcontext(c.link, c.ctx)  g_flag }\ncoro_checkpoint = () void { g_flag = 1  swapcontext(g_cur, g_back) }\nawork = () void { g_log = g_log * 10 + 1  coro_checkpoint()  g_log = g_log * 10 + 1  coro_checkpoint()  g_log = g_log * 10 + 1 }\nbwork = () void { g_log = g_log * 10 + 2  coro_checkpoint()  g_log = g_log * 10 + 2 }\nmark_alive = (flags: RawPtr<u8>, i: i64, n: i64) void { store_i64(flags.offset(i * 8), 1)  init_flags(flags, i + 1, n) }\ninit_flags = (flags: RawPtr<u8>, i: i64, n: i64) void { (i < n).match({ true => mark_alive(flags, i, n), false => {} }) }\ndo_tick = (coros: [Coro], flags: RawPtr<u8>, i: i64) i32 { r := coros[i].resume()  store_i64(flags.offset(i * 8), r)  r }\ntick = (coros: [Coro], flags: RawPtr<u8>, i: i64) i32 { (load_i64(flags.offset(i * 8)) == 1).match({ true => do_tick(coros, flags, i), false => 0 }) }\npass = (coros: [Coro], flags: RawPtr<u8>, i: i64, n: i64) i32 { (i < n).match({ true => tick(coros, flags, i) + pass(coros, flags, i + 1, n), false => 0 }) }\ndrive = (coros: [Coro], flags: RawPtr<u8>, n: i64) void { (pass(coros, flags, 0, n) > 0).match({ true => drive(coros, flags, n), false => {} }) }\nrun = (coros: [Coro]) void { n := coros.len  flags := malloc(n * 8)  init_flags(flags, 0, n)  drive(coros, flags, n) }\ntest* = () i32 { a := coro_new(awork)  b := coro_new(bwork)  run([a, b])  g_log }', 12121),
    ('getcontext  = (ctx: RawPtr<u8>) i32\nmakecontext = (ctx: RawPtr<u8>, fn: () void, argc: i32) void\nswapcontext = (out: RawPtr<u8>, inc: RawPtr<u8>) i32\nmalloc = (n: i64) RawPtr<u8>\ng_cur := null_ptr()\ng_back := null_ptr()\ng_flag := 0\ng_mbox := null_ptr()\ng_head := 0\ng_tail := 0\ng_acc := 0\nCoro*: { ctx: RawPtr<u8>, link: RawPtr<u8>, stack: RawPtr<u8> }\ncoro_new = (work: () void) Coro { stack := malloc(65536)  ctx := malloc(1024)  link := malloc(1024)  getcontext(ctx)  store_i64(ctx.offset(16), stack)  store_i64(ctx.offset(32), 65536)  store_i64(ctx.offset(8), link)  makecontext(ctx, work, 0)  Coro(ctx: ctx, link: link, stack: stack) }\ncoro_resume = (c: Coro) i32 { g_cur = c.ctx  g_back = c.link  g_flag = 0  swapcontext(c.link, c.ctx)  g_flag }\ncoro_checkpoint = () void { g_flag = 1  swapcontext(g_cur, g_back) }\nsend = (m: i64) void { store_i64(g_mbox.offset(g_tail * 8), m)  g_tail = g_tail + 1 }\nrecv = () i64 { m := load_i64(g_mbox.offset(g_head * 8))  g_head = g_head + 1  m }\nhas_msg = () i32 { (g_head < g_tail).match({ true => 1, false => 0 }) }\nproducer = () void { send(1)  coro_checkpoint()  send(2)  coro_checkpoint()  send(3) }\ntake = () void { g_acc = g_acc * 10 + recv() }\nconsume = (remaining: i32) void { (remaining == 0).match({ true => {}, false => (has_msg() == 1).match({ true => after_take(remaining), false => after_wait(remaining) }) }) }\nafter_take = (remaining: i32) void { take()  consume(remaining - 1) }\nafter_wait = (remaining: i32) void { coro_checkpoint()  consume(remaining) }\nconsumer = () void { consume(3) }\nstep = (c: Coro, alive: i32) i32 { (alive == 1).match({ true => coro_resume(c), false => 0 }) }\nrun2 = (a: Coro, b: Coro, aa: i32, bb: i32) void { na := step(a, aa)  nb := step(b, bb)  ((na + nb) > 0).match({ true => run2(a, b, na, nb), false => {} }) }\ntest* = () i32 { g_mbox = malloc(128)  p := coro_new(producer)  c := coro_new(consumer)  run2(p, c, 1, 1)  g_acc }', 123),
    ('Alloc*: { acquire: (MutPtr<Self>, i64) RawPtr<u8> }\nmalloc = (n: i64) RawPtr<u8>\nHeap*: { _: i32 }\nBump*: { buf: RawPtr<u8>, off: i64 }\nHeap.impl(Alloc, { acquire = (s: MutPtr<Heap>, n: i64) RawPtr<u8> { malloc(n) } })\nBump.impl(Alloc, { acquire = (s: MutPtr<Bump>, n: i64) RawPtr<u8> { p := s.buf.offset(s.off)  s.off = s.off + n  p } })\nfill<A> = (a: MutPtr<A>) i64 { p := a.acquire(8)  store_i64(p, 21)  q := a.acquire(8)  store_i64(q, 21)  load_i64(p) + load_i64(q) }\ntest* = () i32 {\n  h := Heap(_: 0)\n  b := Bump(buf: malloc(64), off: 0)\n  to_i32(fill(h.addr()) + fill(b.addr()) + b.off)\n}', 100),
    ('Arc<T>: { base: RawPtr<u8> }\nmalloc = (n: i64) RawPtr<u8>\nfree = (p: RawPtr<u8>) void\narc_val<T> = (r: Arc<T>) [T] { slice(r.base.offset(8), 1) }\narc_new<T> = (x: T) Arc<T> { base := malloc(8 + sizeof(T))  store_i64(base, 1)  r := Arc<T>(base: base)  sl := r.arc_val()  sl[0] = x  r }\narc_get<T> = (r: Arc<T>) T { r.arc_val()[0] }\narc_count<T> = (r: Arc<T>) i64 { load_i64(r.base) }\narc_clone<T> = (r: Arc<T>) Arc<T> { atomic_add_i64(r.base, 1)  Arc<T>(base: r.base) }\narc_drop<T> = (r: Arc<T>) void { (atomic_add_i64(r.base, 0 - 1) == 0).match({ true => free(r.base), false => {} }) }\ntest* = () i64 {\n  r := arc_new(42)\n  r2 := r.arc_clone()\n  a := r.arc_count()\n  r.arc_drop()\n  b := r.arc_count()\n  v := r.arc_get()\n  a * 100 + b * 10 + v\n}', 252),
    ('g_dropped := 0\nDrop*: { drop: (MutPtr<Self>) void }\nResource*: { id: i32 }\nResource.impl(Drop, { drop = (s: MutPtr<Resource>) void { g_dropped = g_dropped + s.id } })\ntest* = () i32 {\n  r := Resource(id: 7)\n  r.addr().drop()\n  g_dropped\n}', 7),
    ('malloc = (n: i64) RawPtr<u8>\nfree = (p: RawPtr<u8>) void\ng_dropped := 0\nDrop*: { drop: (MutPtr<Self>) void }\nResource*: { id: i32 }\nResource.impl(Drop, { drop = (s: MutPtr<Resource>) void { g_dropped = g_dropped + 1 } })\nOwn*: { base: RawPtr<u8> }\nown_val = (o: Own) [Resource] { slice(o.base.offset(8), 1) }\nown_new = (x: Resource) Own { base := malloc(8 + sizeof(Resource))  store_i64(base, 1)  o := Own(base: base)  s := o.own_val()  s[0] = x  o }\nown_clone = (o: Own) Own { store_i64(o.base, load_i64(o.base) + 1)  Own(base: o.base) }\nown_ptr = (o: Own) MutPtr<Resource> { o.own_val()[0].addr() }\nown_release = (o: Own) void { n := load_i64(o.base) - 1  store_i64(o.base, n)  (n == 0).match({ true => own_fin(o), false => {} }) }\nown_fin = (o: Own) void { o.own_ptr().drop()  free(o.base) }\ntest* = () i32 {\n  o := own_new(Resource(id: 5))\n  o2 := o.own_clone()\n  o.own_release()\n  mid := g_dropped\n  o2.own_release()\n  mid * 10 + g_dropped\n}', 1),
    ('malloc = (n: i64) RawPtr<u8>\nfree = (p: RawPtr<u8>) void\ng_dropped := 0\nDrop*: { drop: (MutPtr<Self>) void }\nResource*: { id: i32 }\nResource.impl(Drop, { drop = (s: MutPtr<Resource>) void { g_dropped = g_dropped + 1 } })\nOwn<T>: { base: RawPtr<u8> }\nown_val<T> = (o: Own<T>) [T] { slice(o.base.offset(8), 1) }\nown_new<T> = (x: T) Own<T> { base := malloc(8 + sizeof(T))  store_i64(base, 1)  o := Own<T>(base: base)  s := o.own_val()  s[0] = x  o }\nown_clone<T> = (o: Own<T>) Own<T> { store_i64(o.base, load_i64(o.base) + 1)  Own<T>(base: o.base) }\nown_ptr<T> = (o: Own<T>) MutPtr<T> { o.own_val()[0].addr() }\nown_release<T> = (o: Own<T>) void { n := load_i64(o.base) - 1  store_i64(o.base, n)  (n == 0).match({ true => own_fin(o), false => {} }) }\nown_fin<T> = (o: Own<T>) void { o.own_ptr().drop()  free(o.base) }\ntest* = () i32 {\n  o := own_new(Resource(id: 5))\n  o2 := o.own_clone()\n  o.own_release()\n  mid := g_dropped\n  o2.own_release()\n  mid * 10 + g_dropped\n}', 1),
# the trailing-comma bool-pair DESYNC family (census 2026-06-10): `{ true => {..}, false => {..}, }`
# in statement position used to swallow every statement after the match (the match became the fn's
# return: f(5) ran as 5 not 105, and inside @while the lost increment HUNG). parse_bool_pair now
# tolerates the trailing comma and VERIFIES the record's `}`.
    ('f = (n: i32) i32 {\n r := 0\n (n > 0).match ({ true => { r = n }, false => { r = 1 }, })\n r + 100\n}\ntest* = () i32 { f(5) }', 105),
    ('f = (n: i32) i32 { (n > 10).match ({ true => { return 1 }, false => 0, })  n * 2 }\ntest* = () i32 { f(20) * 10 + f(3) }', 16),
    ('test* = () i32 {\n i := 0\n @while (i < 5) {\n  (i > 2).match ({ true => { i = i + 2 }, false => { i = i + 1 }, })\n }\n i * 10\n}', 50),
# the loop HANDLER controls (user-decided design 2026-06-10): `h.break` / `h.continue` in a .loop
# body lower to C break/continue (nearest enclosing loop). No bare keywords — match-only stays.
    ('test* = () i32 {\n acc := 0\n [1, 2, 3, 4, 5].loop((h, i, x) {\n  (x > 3).match ({ true => { h.break }, false => { acc = acc + x } })\n })\n acc\n}', 6),
    ('test* = () i32 {\n acc := 0\n [1, 2, 3, 4, 5].loop((h, i, x) {\n  (x == 3).match ({ true => { h.continue }, false => {} })\n  acc = acc + x\n })\n acc\n}', 12),
    ('test* = () i32 {\n acc := 0\n [1, 2].loop((h, i, x) {\n  [10, 20, 30].loop((g, j, y) {\n   (y > 10).match ({ true => { g.break }, false => { acc = acc + y } })\n  })\n })\n acc\n}', 20),
# soundness batch (census gaps 2/5): str == is CONTENT equality (was pointer identity); u8
# arithmetic truncates at the inferred-u8 let (was typed u8 but run as the un-truncated C int);
# an out-of-i32-range literal IS an i64.
    ('eqs = (a: str, b: str) bool { a == b }\ntest* = () i32 { eqs("ab", "ab").match ({ true => 11, false => 21 }) }', 11),
    ('test* = () i32 {\n a: u8 := 200\n b: u8 := 100\n c := a + b\n to_i32(c)\n}', 44),
    ('test* = () i32 { x: i64 := 4294967296\n ((x / 1073741824) == 4).match ({ true => 1, false => 0 }) }', 1),
# std.concurrent.cown — the FFI MEMORY CONVENTION (Goal N3): a raw boundary pointer/handle is re-owned via a
# wrapper type + impl(Drop, { … free/close … }); Own<T> fires the matching release EXACTLY ONCE at
# refcount zero (observable via the g_freed/g_closed counters). Buf: v(65)+mid(0)*100+end(1)*10 = 75;
# File: fd(7)+mid(0)*100+end(1)*10 = 17. (Examples 1+2 of zen/std/concurrent/cown.zen, flattened.)
    ("malloc = (n: i64) RawPtr<u8>\nfree = (p: RawPtr<u8>) void\ng_freed := 0\nfree_obs = (p: RawPtr<u8>) void { g_freed = g_freed + 1  free(p) }\nDrop*: { drop: (MutPtr<Self>) void }\nOwn<T>: { base: RawPtr<u8> }\nown_val<T> = (o: Own<T>) [T] { slice(o.base.offset(8), 1) }\nown_get<T> = (o: Own<T>) T { o.own_val()[0] }\nown_new<T> = (x: T) Own<T> { base := malloc(8 + sizeof(T))  store_i64(base, 1)  o := Own<T>(base: base)  s := o.own_val()  s[0] = x  o }\nown_clone<T> = (o: Own<T>) Own<T> { store_i64(o.base, load_i64(o.base) + 1)  Own<T>(base: o.base) }\nown_ptr<T> = (o: Own<T>) MutPtr<T> { o.own_val()[0].addr() }\nown_release<T> = (o: Own<T>) void { n := load_i64(o.base) - 1  store_i64(o.base, n)  (n == 0).match({ true => own_fin(o), false => {} }) }\nown_fin<T> = (o: Own<T>) void { o.own_ptr().drop()  free(o.base) }\nBuf*: { p: RawPtr<u8>, len: i64 }\nbuf_alloc = (n: i64) Own<Buf> { own_new(Buf(p: malloc(n), len: n)) }\nbuf_set = (o: Own<Buf>, i: i64, v: u8) void { store(o.own_get().p.offset(i), v) }\nbuf_get = (o: Own<Buf>, i: i64) u8 { load(o.own_get().p.offset(i)) }\nBuf.impl(Drop, { drop = (b: MutPtr<Buf>) void { free_obs(b.p) } })\ntest* = () i32 {\n  o := buf_alloc(8)\n  o.buf_set(0, 65)\n  v := o.buf_get(0)\n  o2 := o.own_clone()\n  o.own_release()\n  mid := g_freed\n  o2.own_release()\n  end := g_freed\n  v + mid * 100 + end * 10\n}", 75),
    ("malloc = (n: i64) RawPtr<u8>\nfree = (p: RawPtr<u8>) void\nclose = (fd: i32) i32\ng_closed := 0\nclose_obs = (fd: i32) i32 { g_closed = g_closed + 1  0 }\nDrop*: { drop: (MutPtr<Self>) void }\nOwn<T>: { base: RawPtr<u8> }\nown_val<T> = (o: Own<T>) [T] { slice(o.base.offset(8), 1) }\nown_get<T> = (o: Own<T>) T { o.own_val()[0] }\nown_new<T> = (x: T) Own<T> { base := malloc(8 + sizeof(T))  store_i64(base, 1)  o := Own<T>(base: base)  s := o.own_val()  s[0] = x  o }\nown_clone<T> = (o: Own<T>) Own<T> { store_i64(o.base, load_i64(o.base) + 1)  Own<T>(base: o.base) }\nown_ptr<T> = (o: Own<T>) MutPtr<T> { o.own_val()[0].addr() }\nown_release<T> = (o: Own<T>) void { n := load_i64(o.base) - 1  store_i64(o.base, n)  (n == 0).match({ true => own_fin(o), false => {} }) }\nown_fin<T> = (o: Own<T>) void { o.own_ptr().drop()  free(o.base) }\nFile*: { fd: i32 }\nfile_wrap = (fd: i32) Own<File> { own_new(File(fd: fd)) }\nfile_fd = (o: Own<File>) i32 { o.own_get().fd }\nFile.impl(Drop, { drop = (f: MutPtr<File>) void { close_obs(f.fd) } })\ntest* = () i32 {\n  o := file_wrap(7)\n  fd := o.file_fd()\n  o2 := o.own_clone()\n  o.own_release()\n  mid := g_closed\n  o2.own_release()\n  end := g_closed\n  fd + mid * 100 + end * 10\n}", 17),
    ('malloc = (n: i64) RawPtr<u8>\nrealloc = (p: RawPtr<u8>, n: i64) RawPtr<u8>\nfree = (p: RawPtr<u8>) void\ng_freed := 0\ng_dropped := 0\nBLACK := 0\nGRAY  := 1\nWHITE := 2\nstore_ptr = (b: RawPtr<u8>, p: RawPtr<u8>) void { store_i64(b, p) }\nload_ptr = (b: RawPtr<u8>) RawPtr<u8> { load_i64(b).offset(0) }\nhcount = (b: RawPtr<u8>) i64 { load_i64(b.offset(0)) }\nhset_count = (b: RawPtr<u8>, v: i64) void { store_i64(b.offset(0), v) }\nhcolor = (b: RawPtr<u8>) i64 { load_i64(b.offset(8)) }\nhset_color = (b: RawPtr<u8>, v: i64) void { store_i64(b.offset(8), v) }\ng_white := null_ptr()\nlist_new = () RawPtr<u8> { l := malloc(16 + 64)  store_i64(l.offset(0), 0)  store_i64(l.offset(8), 8)  l }\nlist_len = (l: RawPtr<u8>) i64 { load_i64(l.offset(0)) }\nlist_get = (l: RawPtr<u8>, i: i64) RawPtr<u8> { load_ptr(l.offset(16 + i * 8)) }\nlist_push = (l: RawPtr<u8>, p: RawPtr<u8>) RawPtr<u8> {\n  n := list_len(l)\n  r := (n == load_i64(l.offset(8))).match({ true => { nc := load_i64(l.offset(8)) * 2  g := realloc(l, 16 + nc * 8)  store_i64(g.offset(8), nc)  g }, false => l })\n  store_ptr(r.offset(16 + n * 8), p)\n  store_i64(r.offset(0), n + 1)\n  r\n}\nroots := null_ptr()\nroots_list = () RawPtr<u8> {\n  (roots == null_ptr()).match({ true => { roots = list_new()  roots }, false => roots })\n}\nroots_add = (b: RawPtr<u8>) void { roots = roots_list().list_push(b) }\nroots_clear = () void { store_i64(roots_list().offset(0), 0) }\nTracer*: { op: i32 }\nTrace*: { trace: (Ptr<Self>, MutPtr<Tracer>) void }\nDrop*: { drop: (MutPtr<Self>) void }\nRc<T>: { base: RawPtr<u8> }\nrc_val<T> = (r: Rc<T>) [T] { slice(r.base.offset(16), 1) }\nrc_get<T> = (r: Rc<T>) T { r.rc_val()[0] }\nrc_base<T> = (r: Rc<T>) RawPtr<u8> { r.base }\nrc_new<T> = (x: T) Rc<T> {\n  base := malloc(16 + sizeof(T))\n  store_i64(base.offset(0), 0)\n  store_i64(base.offset(8), 0)\n  r := Rc<T>(base: base)\n  s := r.rc_val()\n  s[0] = x\n  r\n}\nrc_inc<T> = (r: Rc<T>) void { store_i64(r.base.offset(0), load_i64(r.base.offset(0)) + 1) }\ndo_drop<T> = (r: Rc<T>) void { s := r.rc_val()  s[0].addr().drop() }\ndo_trace<T> = (r: Rc<T>, t: MutPtr<Tracer>) void {\n  s := r.rc_val()\n  s[0].addr().trace(t)\n}\nvisit_child = (cb: RawPtr<u8>, t: MutPtr<Tracer>) void {\n  (t.op == 0).match({ true => { hset_count(cb, hcount(cb) - 1)  cc_mark(cb) }, false =>\n  (t.op == 1).match({ true => { cc_scan(cb) }, false =>\n  (t.op == 2).match({ true => { hset_count(cb, hcount(cb) + 1)  cc_scan_black(cb) }, false =>\n  { cc_gather(cb) } }) }) })\n}\ncc_mark = (b: RawPtr<u8>) void {\n  (hcolor(b) == GRAY).match({ true => {}, false => {\n    hset_color(b, GRAY)\n    mt := Tracer(op: 0)\n    blk_trace(b, mt.addr())\n  } })\n}\ncc_scan = (b: RawPtr<u8>) void {\n  (hcolor(b) == GRAY).match({ true => {\n    (hcount(b) > 0).match({ true => { cc_scan_black(b) }, false => {\n      hset_color(b, WHITE)\n      st := Tracer(op: 1)\n      blk_trace(b, st.addr())\n    } })\n  }, false => {} })\n}\ncc_scan_black = (b: RawPtr<u8>) void {\n  hset_color(b, BLACK)\n  bt := Tracer(op: 2)\n  blk_trace(b, bt.addr())\n}\ncc_gather = (b: RawPtr<u8>) void {\n  (hcolor(b) == WHITE).match({ true => {\n    hset_color(b, BLACK)\n    g_white = g_white.list_push(b)\n    gt := Tracer(op: 3)\n    blk_trace(b, gt.addr())\n  }, false => {} })\n}\nNode*: { has: i32, kid: RawPtr<u8> }\nNode.impl(Drop, { drop = (s: MutPtr<Node>) void { g_dropped = g_dropped + 1 } })\nNode.impl(Trace, { trace = (s: Ptr<Node>, t: MutPtr<Tracer>) void {\n  (s.has == 0).match({ true => {}, false => { visit_child(s.kid, t) } })\n} })\nblk_trace = (b: RawPtr<u8>, t: MutPtr<Tracer>) void { do_trace(Rc<Node>(base: b), t) }\nblk_drop = (b: RawPtr<u8>) void { do_drop(Rc<Node>(base: b)) }\nset_kid = (parent: Rc<Node>, child: Rc<Node>) void {\n  p := parent.rc_val()\n  p[0] = Node(has: 1, kid: child.base)\n  child.rc_inc()\n}\ndrive = (op: i32, i: i64) void {\n  (i < roots_list().list_len()).match({ true => {\n    b := roots_list().list_get(i)\n    (op == 0).match({ true => { cc_mark(b) }, false =>\n    (op == 1).match({ true => { cc_scan(b) }, false =>\n    { cc_gather(b) } }) })\n    drive(op, i + 1)\n  }, false => {} })\n}\nfree_all = (i: i64) void {\n  (i < g_white.list_len()).match({ true => { g_freed = g_freed + 1  blk_drop(g_white.list_get(i))  free(g_white.list_get(i))  free_all(i + 1) }, false => {} })\n}\ncollect = () void {\n  g_white = list_new()\n  drive(0, 0)\n  drive(1, 0)\n  drive(2, 0)\n  free_all(0)\n  roots_clear()\n}\ntest* = () i32 {\n  a := rc_new(Node(has: 0, kid: null_ptr()))\n  b := rc_new(Node(has: 0, kid: null_ptr()))\n  set_kid(a, b)\n  set_kid(b, a)\n  roots_add(a.base)\n  roots_add(b.base)\n  collect()\n  g_dropped\n}', 2),
    ('getcontext  = (ctx: RawPtr<u8>) i32\nmakecontext = (ctx: RawPtr<u8>, fn: () void, argc: i32) void\nswapcontext = (out: RawPtr<u8>, inc: RawPtr<u8>) i32\nmalloc = (n: i64) RawPtr<u8>\ng_cur := null_ptr()\ng_back := null_ptr()\ng_flag := 0\ng_result := 0\nCoro*: { ctx: RawPtr<u8>, link: RawPtr<u8>, stack: RawPtr<u8> }\ncoro_new = (work: () void) Coro { stack := malloc(65536)  ctx := malloc(1024)  link := malloc(1024)  getcontext(ctx)  store_i64(ctx.offset(16), stack)  store_i64(ctx.offset(32), 65536)  store_i64(ctx.offset(8), link)  makecontext(ctx, work, 0)  Coro(ctx: ctx, link: link, stack: stack) }\ncoro_resume = (c: Coro) i32 { g_cur = c.ctx  g_back = c.link  g_flag = 0  swapcontext(c.link, c.ctx)  g_flag }\ncoro_checkpoint = () void { g_flag = 1  swapcontext(g_cur, g_back) }\nRuntime*: { alloc: (MutPtr<Self>, i64) RawPtr<u8>, checkpoint: (MutPtr<Self>) void }\nSync*: { _: i32 }\nAsync*: { buf: RawPtr<u8>, off: i64 }\nSync.impl(Runtime, { alloc = (s: MutPtr<Sync>, n: i64) RawPtr<u8> { malloc(n) }\ncheckpoint = (s: MutPtr<Sync>) void { } })\nAsync.impl(Runtime, { alloc = (s: MutPtr<Async>, n: i64) RawPtr<u8> { p := s.buf.offset(s.off)  s.off = s.off + n  p }\ncheckpoint = (s: MutPtr<Async>) void { coro_checkpoint() } })\ntask<R> = (r: MutPtr<R>) void { p := r.alloc(8)  store_i64(p, 5)  r.checkpoint()  store_i64(p, load_i64(p) + 100)  g_result = g_result + load_i64(p) }\nawork = () void { a := Async(buf: malloc(64), off: 0)  task(a.addr()) }\ntest* = () i32 {\n  sy := Sync(_: 0)\n  task(sy.addr())\n  c := coro_new(awork)\n  coro_resume(c)\n  coro_resume(c)\n  g_result\n}', 210),
    ('malloc = (n: i64) RawPtr<u8>\nRuntime*: { alloc: (MutPtr<Self>, i64) RawPtr<u8>, checkpoint: (MutPtr<Self>) void }\nSync*: { _: i32 }\nSync.impl(Runtime, { alloc = (s: MutPtr<Sync>, n: i64) RawPtr<u8> { malloc(n) }, checkpoint = (s: MutPtr<Sync>) void { } })\ntask<R> = (r: MutPtr<R>) i64 { p := r.alloc(8)  store_i64(p, 5)  r.checkpoint()  store_i64(p, load_i64(p) + 100)  load_i64(p) }\ntest* = () i64 {\n  sy := Sync(_: 0)\n  task(sy.addr())\n}', 105),
    ('malloc = (n: i64) RawPtr<u8>\nRuntime*: { alloc: (MutPtr<Self>, i64) RawPtr<u8>, checkpoint: (MutPtr<Self>) void }\nSync*: { _: i32 }\nSync.impl(Runtime, { alloc = (s: MutPtr<Sync>, n: i64) RawPtr<u8> { malloc(n) }\ncheckpoint = (s: MutPtr<Sync>) void { } })\ntask<R> = (r: MutPtr<R>) i64 { p := r.alloc(8)  store_i64(p, 5)  r.checkpoint()  store_i64(p, load_i64(p) + 100)  load_i64(p) }\ntest* = () i64 {\n  sy := Sync(_: 0)\n  task(sy.addr())\n}', 105),
    ('malloc = (n: i64) RawPtr<u8>\nfill = (p: RawPtr<u8>, go: i32) void { (go == 1).match({ true => { store_i64(p.offset(0), 7)  store_i64(p.offset(8), 35) }, false => {} }) }\ntest* = () i64 {\n  p := malloc(64)\n  store_i64(p.offset(0), 0)\n  store_i64(p.offset(8), 0)\n  fill(p, 1)\n  load_i64(p.offset(0)) + load_i64(p.offset(8))\n}', 42),
    ('malloc = (n: i64) RawPtr<u8>\nfill = (p: RawPtr<u8>, go: i32) void { (go == 1).match({ true => { store_i64(p.offset(0), 7)  store_i64(p.offset(8), 35) }, false => {} }) }\ntest* = () i64 {\n  p := malloc(64)\n  store_i64(p.offset(0), 0)\n  store_i64(p.offset(8), 0)\n  fill(p, 0)\n  load_i64(p.offset(0)) + load_i64(p.offset(8))\n}', 0),
    ('R*: Ok(i32) | Err\nmalloc = (n: i64) RawPtr<u8>\nfill = (p: RawPtr<u8>, r: R) void { r.match({ .Ok(v) => { store_i64(p.offset(0), 3)  store_i64(p.offset(8), 39) }, .Err => {} }) }\ntest* = () i64 {\n  p := malloc(64)\n  store_i64(p.offset(0), 0)\n  store_i64(p.offset(8), 0)\n  fill(p, .Ok(7))\n  load_i64(p.offset(0)) + load_i64(p.offset(8))\n}', 42),
    ('system = (cmd: str) i32\ntest* = () i32 { system(cstr("true")) }', 0),
    ('malloc = (n: i64) RawPtr<u8>\nopen = (path: str, flags: i32, mode: i32) i32\nwrite = (fd: i32, buf: RawPtr<u8>, n: i64) i64\nread = (fd: i32, buf: RawPtr<u8>, n: i64) i64\nclose = (fd: i32) i32\ntest* = () i32 {\n  wbuf := malloc(8)\n  store(offset(wbuf, 0), \'A\')\n  store(offset(wbuf, 1), \'B\')\n  store(offset(wbuf, 2), \'C\')\n  wfd := open(cstr("/tmp/zen_io_diff_rt.txt"), 577, 420)\n  write(wfd, wbuf, 3)\n  close(wfd)\n  rbuf := malloc(8)\n  rfd := open(cstr("/tmp/zen_io_diff_rt.txt"), 0, 0)\n  read(rfd, rbuf, 3)\n  close(rfd)\n  load(offset(rbuf, 0))\n}', 65),
    ('malloc = (n: i64) RawPtr<u8>\nsystem = (cmd: str) i32\nopen = (path: str, flags: i32, mode: i32) i32\nread = (fd: i32, buf: RawPtr<u8>, n: i64) i64\nclose = (fd: i32) i32\nlseek = (fd: i32, off: i64, whence: i32) i64\nread_len = (path: str) i64 {\n  fd := open(path, 0, 0)\n  n := lseek(fd, 0, 2)\n  lseek(fd, 0, 0)\n  buf := malloc(n + 1)\n  read(fd, buf, n)\n  store(offset(buf, n), 0)\n  close(fd)\n  n\n}\ntest* = () i64 {\n  system(cstr("printf ABC > /tmp/zen_io_diff_len.txt"))\n  read_len(cstr("/tmp/zen_io_diff_len.txt"))\n}', 3),
# --- test_integer_match ---
    ('test* = () i32 { (2).match({ 0 => 10, 1 => 11, 2 => 12, _ => 99 }) }', 12),
    ('test* = () i32 { (1).match({ 0 => 10, 1 => 11, _ => 20 }) }', 11),
    ('test* = () i32 { (1).match({ 1 => 100, _ => 200 }) }', 100),
    ('test* = () i32 { (9).match({ 0 => 10, 1 => 11, _ => 20 }) }', 20),
    ('test* = () i32 { (3).match({ 0=>0, 1=>10, 2=>20, 3=>30, _=>99 }) }', 30),
# --- test_member_assignment ---
    ('P*: { x: i32 }\nf* = (p: P) i32 {\n p.x = 99\n 5\n}\ntest* = () i32 { f(P(x: 0)) }', 5),
    ('P*: { x: i32 }\nf* = (p: P) i32 {\n p.x = 99\n p.x\n}\ntest* = () i32 { f(P(x: 0)) }', 99),
    ('test* = () i32 {\n x := 5\n x = 7\n x\n}', 7),
    ('P*: { x: i32 }\nbump* = (p: Ptr<P>) i32 {\n p.x = 42\n p.x\n}\ntest* = () i32 { q := P(x: 0)\n bump(q.addr()) }', 42),
    ('I*: { n: i32 }\nO*: { i: I }\nf* = (o: O) i32 {\n o.i.n = 42\n o.i.n\n}\ntest* = () i32 { f(O(i: I(n: 0))) }', 42),
# --- test_guard_early_return ---
    ('f* = (b: bool) i32 {\n b.match({ false => { return 9 }, _ })\n 7\n}\ntest* = () i32 { f(false) }', 9),
    ('f* = (b: bool) i32 {\n b.match({ false => { return 9 }, _ })\n 7\n}\ntest* = () i32 { f(true) }', 7),
    ('f* = (b: bool) i32 {\n b.match({ true => { return 9 }, _ })\n 7\n}\ntest* = () i32 { f(true) }', 9),
    ('R*: Ok(i32) | Err\nf* = (r: R) i32 {\n r.match({ .Err => { return 9 }, _ })\n 7\n}\ntest* = () i32 { f(.Err()) }', 9),
    ('R*: Ok(i32) | Err\nf* = (r: R) i32 {\n r.match({ .Err => { return 9 }, _ })\n 7\n}\ntest* = () i32 { f(.Ok(0)) }', 7),
    ('R*: Ok(i32) | Err(i32)\nf* = (r: R) i32 {\n r.match({ .Err(e) => { return e }, _ })\n 7\n}\ntest* = () i32 { f(.Err(42)) }', 42),
    ('f* = (n: i32) i32 {\n x := 0\n n.match({ 0 => { x = 1 }, 1 => { x = 2 }, _ })\n x\n}\ntest* = () i32 { f(0)*100 + f(1)*10 + f(9) }', 120),
    ('R*: Ok(i32) | Err\nf* = (r: R) i32 {\n r.match({ .Ok(v) => { return v }, .Err => { return 9 } })\n 0\n}\ntest* = () i32 { f(.Ok(5)) + f(.Err()) }', 14),
# --- test_value_position_trailing_value_accepted (value half) ---
    ('R*: Ok(i32) | Err(i32)\nf* = (r: R) i32 {\n v := r.match({ .Ok(x) => { return x }, .Err(e) => e })\n v + 1\n}\ntest* = () i32 { f(.Ok(5)) }', 6),
    ('f* = (b: bool) i32 {\n v := b.match({ true => { 7 }, false => 0 })\n v\n}\ntest* = () i32 { f(true) }', 7),
# --- recovered breadth: integer-match default + non-first arm (migrated test_check value half) ---
    ('test* = () i32 { (7).match({ 5 => 50, 7 => 70, _ => 0 }) }', 70),
    ('test* = () i32 { (4).match({ 5 => 50, 7 => 70, _ => 11 }) }', 11),
# --- recovered breadth: nested struct field read ---
    ('I*: { n: i32 }\nO*: { a: I, b: I }\ntest* = () i32 { o := O(a: I(n: 3), b: I(n: 4))\n o.a.n * 10 + o.b.n }', 34),
# --- recovered breadth: a comparison drives a bool match ---
    ('test* = () i32 { (3 < 5).match({ true => 1, false => 0 }) }', 1),
    ('test* = () i32 { (5 < 3).match({ true => 1, false => 0 }) }', 0),
# --- recovered breadth: slice write-then-read ---
    ('test* = () i32 { s := [1, 2, 3]\n s[1] = 20\n s[0] + s[1] + s[2] }', 24),
# --- std.core.slice: sub/take/drop zero-copy VIEWS (ptr = base + lo*sizeof(T), len = hi-lo). Bounds
#     are clamped to [0, len] so an out-of-range hi yields a shorter view, not an OOB read. ---
    ('sl_clamp = (v: i64, lo: i64, hi: i64) i64 { (v < lo).match({ true => lo, false => (v > hi).match({ true => hi, false => v }) }) }\nsub<T> = (xs: [T], lo: i64, hi: i64) [T] { l := sl_clamp(lo, 0, xs.len)  h := sl_clamp(hi, l, xs.len)  slice(xs.ptr.offset(l * sizeof(T)), h - l) }\ntake<T> = (xs: [T], n: i64) [T] { xs.sub(0, n) }\ndrop<T> = (xs: [T], n: i64) [T] { xs.sub(n, xs.len) }\ntest* = () i32 {\n  s := [10, 20, 30, 40]\n  v: [i32] := s.sub(1, 3)\n  t: [i32] := s.take(2)\n  d: [i32] := s.drop(3)\n  o: [i32] := s.sub(2, 99)\n  v.len.to_i32() * 1000 + v[0] * 10 + v[1] + t[0] + d[0] + o.len.to_i32()\n}', 2282),
# --- std.core.slice: reverse_in allocates a NEW slice and copies xs in reverse (out[len-1-i] = x). ---
    ('Heap*: { z: i32 }\nhacq = (a: MutPtr<Heap>, n: i64) Ptr<u8> { malloc(n) }\nhbuf<A, T> = (a: MutPtr<A>, n: i64, like: [T]) [T] { slice(a.hacq(n * sizeof(T)), n) }\nreverse_in<A, T> = (a: MutPtr<A>, xs: [T]) [T] { out := a.hbuf(xs.len, xs)  xs.loop((h, i, x) { out[xs.len - 1 - i] = x })  out }\ntest* = () i32 {\n  h := Heap(z: 0)\n  r: [i32] := h.addr().reverse_in([1, 2, 3, 4])\n  r[0] * 1000 + r[1] * 100 + r[2] * 10 + r[3]\n}', 4321),
# --- std.core.slice: index_of/contains (via `==`, scalar elems) and find_by (predicate, any elem). ---
    ('index_of<T> = (xs: [T], x: T) i64 { r := 0 - 1  xs.loop((h, i, e) { (e == x).match({ true => (r < 0).match({ true => { r = i }, false => {} }), false => {} }) })  r }\ncontains<T> = (xs: [T], x: T) bool { xs.index_of(x) >= 0 }\nis30 = (x: i32) bool { x == 30 }\nfind_by<T> = (xs: [T], pred: (T) bool) i64 { r := 0 - 1  xs.loop((h, i, e) { pred(e).match({ true => (r < 0).match({ true => { r = i }, false => {} }), false => {} }) })  r }\ntest* = () i32 {\n  s := [10, 20, 30, 40]\n  ix := s.index_of(30)\n  miss := s.index_of(99)\n  has := s.contains(40).match({ true => 1, false => 0 })\n  fb := s.find_by(is30)\n  ix.to_i32() * 1000 + (miss + 1).to_i32() * 100 + has * 10 + fb.to_i32()\n}', 2012),
# --- recovered breadth: arithmetic precedence + recursion ---
    ('test* = () i32 { 2 + 3 * 4 - 1 }', 13),
    ('fac* = (n: i32) i32 { (n == 0).match({ true => 1, false => n * fac(n - 1) }) }\ntest* = () i32 { fac(5) }', 120),
# --- regression (#93): an INLINE nested match on a GENERIC enum's payload bind. The outer
#     `r.match({ .Err(e) => e.match({…}) })` must give `e` the SUBSTITUTED concrete payload type
#     (E = IoError of Result<i32, IoError>) so the inner match resolves IoError's tags — they used
#     to emit BARE (`_Errno`) instead of prefixed (`IoError_Errno`), producing uncompilable C.
    ('Result<T, E>: Ok(T) | Err(E)\nIoError*: NotFound | Denied | Errno(i32)\nmkErr<T, E> = (ok: T, x: E) Result<T, E> { .Err(x) }\ntest* = () i32 {\n  r := mkErr(0, .Errno(7))\n  r.match({ .Ok(v) => v, .Err(e) => e.match({ .NotFound => 1, .Denied => 2, .Errno(n) => n }) })\n}', 7),
# the same idiom on a single-tparam generic enum (Box<T> wrapping the inner enum)
    ('IoError*: NotFound | Denied | Errno(i32)\nBox<T>: B(T)\nmkBox<T> = (x: T) Box<T> { .B(x) }\ntest* = () i32 {\n  r := mkBox(.Denied)\n  r.match({ .B(e) => e.match({ .NotFound => 1, .Denied => 2, .Errno(n) => n }) })\n}', 2),
# --- arm-record unification: the TRAILING comma is tolerated on the LAST arm of every match form,
#     in VALUE position too (the house match-arm style). The bool record used to be four hand-rolled
#     paths and the pair form once swallowed everything after the match on a trailing comma — these
#     pin all four record shapes through the ONE unified walker. ---
    ('test* = () i32 { b := 2 < 3  v := b.match ({ true => { 7 }, false => { 0 }, })  v + 10 }', 17),   # bool pair, trailing comma
    ('test* = () i32 { v := (1 < 2).match ({ false => 5, _ => 9, })  v }', 9),                          # bool + `_ => body`, trailing comma
    ('test* = () i32 { (2).match ({ 1 => 10, 2 => 20, _ => 99, }) }', 20),                              # literal arms, trailing comma
    ('C*: A | B\ntest* = () i32 { c := C.B()  c.match ({ .A => 1, .B => 2, }) }', 2),                   # variant arms, trailing comma
# --- enum variant DEFAULT values (`Name = expr`): a zero-arg `.Name` bakes in the constant; payload
#     and bare variants still mix in the same declaration. ---
    ('RGB*: { r: i32, g: i32, b: i32 }\nColour*: Red = RGB(r: 255, g: 0, b: 0) | Green | Blue | Custom(RGB)\ntest* = () i32 {\n  c := Colour.Red\n  c.match ({ .Red(v) => v.r, .Custom(v) => v.r, .Green => 0, .Blue => 0 })\n}', 255),   # struct default
    ('Lvl*: Low = 1 | High = 9 | Exact(i32)\nf* = (l: Lvl) i32 { l.match ({ .Low(v) => v, .High(v) => v, .Exact(v) => v }) }\ntest* = () i32 { f(Lvl.Low) + f(Lvl.High) }', 10),                                              # scalar defaults
    ('Lvl*: Low = 1 | High = 9 | Exact(i32)\nf* = (l: Lvl) i32 { l.match ({ .Low(v) => v, .High(v) => v, .Exact(v) => v }) }\ntest* = () i32 { f(.Low) + f(.Exact(40)) }', 41),                                                # leading-dot default + payload
# --- f64 floats (Goal R): a literal carries its TEXT through the compiler (the compiler itself has
#     no float values); f64 op f64 only for + - * / and comparisons; the int<->float boundary is
#     crossed ONLY by the explicit to_f64 / to_i64 / to_i32 casts (C truncation toward zero). ---
    ('test* = () i32 { to_i32(1.5 * 4.0) }', 6),
    ('test* = () i32 {\n  x := 2.5\n  y := x + 0.25\n  to_i32(y * 4.0)\n}', 11),
    ('test* = () i32 { (1.5 > 1.25).match({ true => 1, false => 0 }) }', 1),
    ('test* = () i32 { to_i32(to_f64(7) * 0.5 * 2.0) }', 7),                                  # to_f64 widens an int
    ('test* = () i32 { to_i32(-2.5 * -2.0) }', 5),                                            # prefix `-` on f64 (the 0.0 - x lowering)
    ('half* = (x: f64) f64 { x / 2.0 }\ntest* = () i32 { to_i32(half(9.0) * 2.0) }', 9),      # f64 params + returns
    ('test* = () i64 { to_i64(2.9) }', 2),                                                    # to_i64 truncates a double the C way
    ('test* = () i32 {\n  x := 0.25\n  x.match ({ 0.25 => 1, 1.5 => 2, _ => 9 })\n}', 1),     # a float-literal match is an `==` chain
    ('g := 1.5\ntest* = () i32 { to_i32(g * 2.0) }', 3),                                      # a module-global f64 (constant init)
    # --- ESCAPE-1: `\xNN` hex escape → one byte; `\\` keeps the backslash (no silent drop) ---
    # (use \x41='A' in STRING cases — a raw high byte in emitted C breaks the text-mode oracle harness;
    #  the high-byte value path is covered by the char-literal case, which lowers to a numeric literal.)
    ("test* = () i32 { '\\xc8' }", 200),                                                       # char-literal \xNN → 200
    ('at = (s: str, i: i32) u8 { s.offset(i).load() }\ntest* = () i32 { at("\\x41", 0) }', 65),  # \x41 → byte 'A'
    ('at = (s: str, i: i32) u8 { s.offset(i).load() }\ntest* = () i32 { at("a\\\\b", 1) }', 92),  # \\ stays a backslash (byte 92)
    ('cnt = (s: str, i: i32) i32 { (s.offset(i).load() == 0).match({ true => i, false => cnt(s, i + 1) }) }\ntest* = () i32 { cnt("\\x41", 0) }', 1),  # \x41 is ONE byte (len 1, not 3)
    # --- LAMBDA-1: typed lambda literals — optional `: Type` per param and an optional return type
    #     must PARSE (the types are discarded; FnT context supplies them on inline-splice) ---
    ('apply = (f: (i32, i32) i32, a: i32, b: i32) i32 { f(a, b) }\ntest* = () i32 { apply((x: i32, y: i32) { x + y }, 3, 4) }', 7),   # typed params
    ('apply = (f: (i32, i32) i32, a: i32, b: i32) i32 { f(a, b) }\ntest* = () i32 { apply((x, y) i32 { x + y }, 5, 6) }', 11),       # untyped params + return type
    ('apply = (f: (i32, i32) i32, a: i32, b: i32) i32 { f(a, b) }\ntest* = () i32 { apply((x: i32, y: i32) i32 { x + y }, 8, 9) }', 17),  # typed params + return type
    ('apply = (f: (i32, i32) i32, a: i32, b: i32) i32 { f(a, b) }\ntest* = () i32 { apply((x: i32, y) { x + y }, 2, 5) }', 7),        # mixed typed/untyped params
    ('fold<T> = (xs: [T], init: T, f: (T, T) T) T {\n  acc := init\n  xs.loop((h, i, x) { acc = f(acc, x) })\n  acc\n}\ntest* = () i32 { [1, 2, 3].fold(0, (x: i32, y: i32) { x + y }) }', 6),  # the motivating fold repro
    ('apply = (f: (i32, i32) i32, a: i32, b: i32) i32 { f(a, b) }\ntest* = () i32 { apply((x, y) { x + y }, 4, 5) }', 9),            # untyped lambda still works (regression guard)
    # --- LVALUE-1: nested store targets — any `ident (.field | [i])*` place expression is assignable ---
    ('S*: { buf: [i32] }\ntest* = () i32 { s := S(buf: [1, 2, 3])  s.buf[0] = 9  s.buf[0] + s.buf[1] }', 11),                       # member then index
    ('P*: { x: i32, y: i32 }\ntest* = () i32 { a := [P(x: 1, y: 2), P(x: 3, y: 4)]  a[0].x = 7  a[0].x + a[1].x }', 10),            # index then field
    ('In*: { p: [i32] }\nS*: { inner: In }\ntest* = () i32 { s := S(inner: In(p: [10, 20]))  s.inner.p[1] = 5  s.inner.p[0] + s.inner.p[1] }', 15),  # member.member.index
    ('test* = () i32 { a := [1, 2, 3]  a[1] = 8  a[0] + a[1] }', 9),                                                                 # plain name[i] = v still works (SIdx path)
    # --- PARSE-RETURN-ARM: a bare `return expr` in arm-body position (not just braced `{ return expr }`) ---
    ('test* = () i32 {\n  n := 150\n  (n > 100).match({ true => return 999, false => 0 })\n}', 999),                                  # bare return arm fires
    ('test* = () i32 {\n  n := 50\n  (n > 100).match({ true => return 999, false => 7 })\n}', 7),                                     # other arm still a value
    ('test* = () i32 {\n  n := 150\n  (n > 100).match({ true => { return 999 }, false => 0 })\n}', 999),                              # braced form unchanged (regression guard)
    # --- TAILPAREN-1: a statement-leading `(` after a qualified ctor starts a NEW statement (a
    #     parenthesized expr), not a payload glued onto the ctor (`State.Idle` ⏎ `(a).q()`) ---
    ('State*: Idle | Run\nq = (s: State) i32 { 7 }\ntest* = () i32 {\n  a := State.Idle\n  (a).q()\n}', 7),                            # newline un-glues the '('
    ('E*: A(i32) | B\nval = (e: E) i32 { e.match({ .A(x) => x, .B => 0 }) }\ntest* = () i32 { val(E.A(42)) }', 42),                  # same-line payload still glues (regression guard)
    # --- G1: multi-field enum payloads — `B(i32, i32)` ≡ `B({_0: i32, _1: i32})`; `.B(a, b)` constructs
    #     the anon struct, `.B(p)` binds it (fields `_0`, `_1`, …). NON-generic enums only — a generic
    #     anon-struct payload (`Cons(T, …)`) hits a pre-existing checker/mono limit, same as the explicit
    #     `Cons({_0: T, …})` form, so it is out of parser scope. ---
    ('E*: A | B(i32, i32)\nsum = (e: E) i32 { e.match({ .A => 0, .B(p) => p._0 + p._1 }) }\ntest* = () i32 { sum(E.B(3, 4)) }', 7),    # qualified ctor
    ('E*: A | B(i32, i32)\nsum = (e: E) i32 { e.match({ .A => 0, .B(p) => p._0 + p._1 }) }\ntest* = () i32 {\n  e := .B(10, 20)\n  sum(e)\n}', 30),  # bare ctor
    ('T*: N | V(i32, i32, i32)\nsum = (t: T) i32 { t.match({ .N => 0, .V(p) => p._0 + p._1 + p._2 }) }\ntest* = () i32 { sum(T.V(1, 2, 3)) }', 6),  # three fields
    ('O*: Some(i32) | None\nun = (o: O) i32 { o.match({ .Some(x) => x, .None => 0 }) }\ntest* = () i32 { un(O.Some(42)) }', 42),     # single payload unchanged (regression guard)

    # --- std.text.str.trim — the ASCII-whitespace scan that backs trim/ltrim/rtrim_view. Walks a [u8]
    #     view, finds the first/last non-whitespace index; result encodes ws_start*100 + trimmed_len.
    #     For "  hi \n": ws_start=2, trimmed_len=2 -> 202 (guards both the offset AND the length). ---
    ('strlen = (s: str) i64\nis_ws = (b: u8) bool { (b == \' \') || (b == \'\\t\') || (b == \'\\n\') || (b == \'\\r\') }\nws_start = (v: [u8]) i64 { lo: i64 := v.len  v.loop((h, i, b) { b.is_ws().match({ true => {}, false => { lo = i  h.break } }) })  lo }\nws_end = (v: [u8]) i64 { hi: i64 := 0  v.loop((h, i, b) { b.is_ws().match({ true => {}, false => { hi = i + 1 } }) })  hi }\ntest* = () i32 { s := "  hi \\n"  v: [u8] := slice(s, strlen(s))  to_i32(ws_start(v) * 100 + (ws_end(v) - ws_start(v))) }', 202),

    # --- std.text.str.split_in — the sep-scan that emits each field's (start, len). Walks a [u8] view,
    #     accumulating per-field lengths as a base-10 checksum (acc = acc*10 + field_len). For "a,,b"
    #     on ',' the fields are 1,0,1 bytes -> 101 (the EMPTY middle field is what 0 guards). ---
    ('strlen = (s: str) i64\ntest* = () i32 { s := "a,,b"  v: [u8] := slice(s, strlen(s))  acc: i64 := 0  start: i64 := 0  v.loop((h, i, b) { (b == \',\').match ({ true => { acc = acc * 10 + (i - start)  start = i + 1 }, _ => {} }) })  acc = acc * 10 + (v.len - start)  to_i32(acc) }', 101),

    # --- std.text.str.words_in — split on RUNS of whitespace, dropping empties. Walks the [u8] view,
    #     opening a word at the first non-ws byte and closing it at the next ws, accumulating each
    #     word's length as a base-10 checksum. "  the  cat sat " -> words 3,3,3 -> 333 (the leading,
    #     doubled, and trailing whitespace must all collapse — any leaked empty would skew the digits). ---
    ('strlen = (s: str) i64\nis_ws = (b: u8) bool { (b == \' \') || (b == \'\\t\') || (b == \'\\n\') || (b == \'\\r\') }\ntest* = () i32 { s := "  the  cat sat "  v: [u8] := slice(s, strlen(s))  acc: i64 := 0  start: i64 := 0 - 1  v.loop((h, i, b) { b.is_ws().match ({ true => (start >= 0).match ({ true => { acc = acc * 10 + (i - start)  start = 0 - 1 }, false => {} }), false => (start < 0).match ({ true => { start = i }, false => {} }) }) })  (start >= 0).match ({ true => { acc = acc * 10 + (v.len - start) }, false => {} })  to_i32(acc) }', 333),
]

# (src, verdict) the check binary must produce.
VERDICT_CASES = [
    # --- soundness batch rejects (census gaps 5/6/13): literal out of range, comparison chains,
    # --- generic-call arity (used to check ok then segfault: the half-bound template was inlined)
    ('test* = () i32 { a: u8 := 300  to_i32(a) }', 'reject'),
    ('test* = () i32 { x: i32 := 4294967296  to_i32(x) }', 'reject'),
    ('test* = () i32 { x := 50  (1 < x < 10).match ({ true => 1, false => 0 }) }', 'reject'),
    ('pick<T> = (xs: [T], a: T) T { a }\ntest* = () i32 { pick([1, 2]) }', 'reject'),
    # --- VARIADIC PARAMS: a `...T` param must be LAST and there may be at most ONE (parse rejects otherwise) ---
    ('bad = (xs: ...i32, y: i32) i32 { y }\ntest* = () i32 { bad(1, 2, 3) }', 'reject'),
    ('bad = (xs: ...i32, ys: ...i32) i32 { 0 }\ntest* = () i32 { bad(1) }', 'reject'),
    # --- test_self_hosted_rejects ---
    ('test* = () i32 {  }', 'reject'),
    ('test* = () i32 {\n  x := 5\n}', 'reject'),
    ('test* = () i32 {\n  x := 5\n  x = 6\n}', 'reject'),
    ('test* = () i32 { "hi" }', 'reject'),
    # --- test_block_arm_validation ---
    ('f* = (flags: RawPtr<u8>, i: i32, n: i32) void { (i < n).match({ true => { store_i64(flags, 1)  store_i64(flags, 2) }, false => {} }) }\ntest* = () i32 { 0 }', 'accept'),
    ('g* = (x: i32) i32 { x }\nf* = (flags: RawPtr<u8>, i: i32, n: i32) void { (i < n).match({ true => { g(1, 2, 3)  store_i64(flags, 1) }, false => {} }) }\ntest* = () i32 { 0 }', 'reject'),
    ('f* = (flags: RawPtr<u8>, i: i32, n: i32) void { (i < n).match({ true => { store_i64(flags)  store_i64(flags, 1) }, false => {} }) }\ntest* = () i32 { 0 }', 'reject'),
    # --- test_duplicate_function_name_rejected ---
    ('foo* = () i32 { 1 }\nfoo* = () i32 { 2 }\ntest* = () i32 { foo() }', 'reject'),
    ('a* = () i32 { 1 }\ndup* = () i32 { 2 }\ndup* = () i32 { 3 }\ntest* = () i32 { a() }', 'reject'),
    # --- test_partial_match_without_wildcard_rejected ---
    ('R*: Ok(i32) | Err\nf* = (r: R) i32 {\n r.match({ .Err => { return 9 } })\n 7\n}\ntest* = () i32 { f(.Ok(0)) }', 'reject'),
    ('f* = (b: bool) i32 {\n b.match({ false => { return 9 } })\n 7\n}\ntest* = () i32 { f(false) }', 'reject'),
    # --- #96: a single non-`_` bool/literal match arm is non-exhaustive (lone value-arm = subject-
    #     ignoring default); a single `_` arm, or a tested arm + a default, is fine ---
    ('f* = (b: bool) i32 {\n b.match({ false => 9 })\n}\ntest* = () i32 { f(false) }', 'reject'),                         # 1 non-`_` bool arm
    ('f* = (b: bool) i32 {\n b.match({ true => 1 })\n}\ntest* = () i32 { f(true) }', 'reject'),                           # 1 non-`_` bool arm
    ('f* = (n: i32) i32 {\n n.match({ 0 => 9 })\n}\ntest* = () i32 { f(5) }', 'reject'),                                 # 1 non-`_` literal arm
    ('f* = (b: bool) i32 {\n b.match({ true => 1, false => 0 })\n}\ntest* = () i32 { f(false) }', 'accept'),             # tested + default (2 arms)
    ('f* = (b: bool) i32 {\n b.match({ false => 9, _ })\n 7\n}\ntest* = () i32 { f(false) }', 'accept'),                 # arm + bare `_` guard
    ('f* = (n: i32) i32 {\n n.match({ 0 => 1, _ => 2 })\n}\ntest* = () i32 { f(5) }', 'accept'),                         # literal arm + `_` default
    ('f* = (n: i32) i32 {\n n.match({ _ => 0 })\n}\ntest* = () i32 { f(5) }', 'accept'),                                 # lone `_` catch-all
    ('f* = (n: i32) i32 {\n n.match({ 0 => 1, 1 => 2, _ => 3 })\n}\ntest* = () i32 { f(5) }', 'accept'),                 # 3-arm literal match
    ('f* = (b: bool) i32 {\n if (b) { return 9 }\n 7\n}\ntest* = () i32 { f(true) }', 'reject'),              # source-level if is not part of Zen
    ('f* = (b: bool) i32 {\n if (b) { return 9 } else { return 8 }\n 7\n}\ntest* = () i32 { f(false) }', 'reject'),
    # --- test_value_position_return_rejected ---
    # A VALUE-position match arm with an EARLY (non-trailing) `return` is rejected: the emitter
    # (genc's ret_to_expr) makes the block's TRAILING statement the produced value, but an early
    # `return` mid-block is turned into a bare `e;` and silently dropped — control never leaves the
    # function and the WRONG (later) expr is produced. Guard returns must be STATEMENT-position
    # (those lower to real `if`). (C-audit #7; block-arm harden.)
    ('R*: Ok(i32) | Err(i32)\nf* = (r: R) i32 {\n v := r.match({ .Ok(x) => { return x  x + 1 }, .Err(e) => e })\n v + 1\n}\ntest* = () i32 { f(.Ok(5)) }', 'reject'),
    ('f* = (b: bool) i32 {\n v := b.match({ true => { return 7  9 }, false => 0 })\n v\n}\ntest* = () i32 { f(true) }', 'reject'),
    # --- test_value_position_trailing_value_accepted (verdict half) ---
    ('R*: Ok(i32) | Err(i32)\nf* = (r: R) i32 {\n v := r.match({ .Ok(x) => { return x }, .Err(e) => e })\n v + 1\n}\ntest* = () i32 { f(.Ok(5)) }', 'accept'),
    ('f* = (b: bool) i32 {\n v := b.match({ true => { 7 }, false => 0 })\n v\n}\ntest* = () i32 { f(true) }', 'accept'),

    # --- Phase C: a brace after a value is a BLOCK, not a struct literal. The ONLY struct
    #     construction is the paren form; the old brace construction form no longer constructs.
    #     The discriminating pair below pins that: the paren form builds the struct (so `.x` is
    #     valid -> accept), while the brace form parses `P` as a bare value and the braces as a
    #     block, so the field access is no longer on a struct literal -> reject. ---
    ('P*: { x: i32 }\ntest* = () i32 { (P(x: 7)).x }', 'accept'),     # paren = the sole struct construction
    ('P*: { x: i32 }\ntest* = () i32 { (P {x: 7}).x }', 'reject'),    # brace in expr position is NOT a struct literal

    # ════════════════════════════════════════════════════════════════════════════════════════
    # RECOVERED BREADTH — accept/reject verdicts the binary CHECK still produces, migrated from
    # the deleted test_reject.py / test_check.py / test_undefined.py. EVERY case below was VERIFIED
    # against the real CHECK binary (tests/_oracle.verdict) on the goalz-oracle-corpus branch; only
    # genuinely-passing verdicts are committed. Cases are chosen to CATCH plausible regressions
    # (a too-few-args call MUST reject; a valid widening MUST accept).
    # ════════════════════════════════════════════════════════════════════════════════════════

    # --- CALL ARITY: a known fn must get exactly its declared number of args ---
    ('add* = (a: i32, b: i32) i32 { a + b }\ntest* = () i32 { add(1) }', 'reject'),            # too few
    ('add* = (a: i32, b: i32) i32 { a + b }\ntest* = () i32 { add(1, 2, 3) }', 'reject'),      # too many
    ('add* = (a: i32, b: i32) i32 { a + b }\ntest* = () i32 { add(1, 2) }', 'accept'),         # exact
    ('zero* = () i32 { 0 }\ntest* = () i32 { zero(1) }', 'reject'),                            # arg to nullary
    ('one* = (a: i32) i32 { a }\ntest* = () i32 { one() }', 'reject'),                         # missing the only arg

    # --- UNDEFINED NAMES: a call to a non-intrinsic, non-imported, non-trait-method is rejected ---
    ('test* = () i32 { nope() }', 'reject'),
    ('test* = () i32 { foo(1) + bar(2) }', 'reject'),
    ('helper* = () i32 { 5 }\ntest* = () i32 { helper() }', 'accept'),                         # a real local is fine
    ('use* = (n: i32) i32 { n }\ntest* = () i32 { use(missing()) }', 'reject'),                # undefined nested in an arg
    ('test* = () i32 { 1 + gone() }', 'reject'),                                               # undefined nested in an operand

    # --- ARG-TYPE NARROWING / MISMATCH: each arg's type must `fit` the parameter ---
    ('takes_u8* = (b: u8) i32 { 0 }\nbig* = () i64 { 9999999999 }\ntest* = () i32 { takes_u8(big()) }', 'reject'),  # i64 ⊀ u8
    ('P*: { x: i32 }\nneeds_p* = (p: P) i32 { p.x }\nmk* = () i64 { 5 }\ntest* = () i32 { needs_p(mk()) }', 'reject'),  # i64 where struct P wanted
    ('A*: { v: i32 }\nB*: { v: i32 }\nneeds_a* = (a: A) i32 { a.v }\ntest* = () i32 { needs_a(B(v: 5)) }', 'reject'),  # B ⊀ A
    ('scalar* = (n: i32) i32 { n }\ntest* = () i32 { s := [1, 2]\n scalar(s) }', 'reject'),    # slice where scalar wanted
    ('takes_i32* = (n: i32) i32 { n }\nlit* = () i32 { takes_i32(5) }\ntest* = () i32 { lit() }', 'accept'),  # a literal fits
    ('widen* = (n: i64) i64 { n }\nsmall* = () u8 { 3 }\ntest* = () i64 { widen(small()) }', 'accept'),  # u8 widens to i64
    ('A*: { v: i32 }\nneeds_a* = (a: A) i32 { a.v }\ntest* = () i32 { needs_a(A(v: 5)) }', 'accept'),  # exact struct

    # --- INTRINSIC ARITY: store/offset/slice = 2 operands, null_ptr = 0, load/load_i64 = 1 ---
    ('test* = () i64 { p := malloc(8)  store_i64(p)  0 }', 'reject'),                          # store_i64 needs 2
    ('test* = () i64 { p := malloc(8)  store_i64(p, 1, 2)  0 }', 'reject'),                    # store_i64 takes 2, not 3
    ('test* = () i64 { p := malloc(8)  q := offset(p)  0 }', 'reject'),                        # offset needs 2
    ('test* = () i64 { p := null_ptr(7)  0 }', 'reject'),                                      # null_ptr takes none
    ('test* = () i64 { p := malloc(8)  store_i64(p, 7)  load_i64(p) }', 'accept'),             # correct arities
    ('test* = () i64 { p := malloc(8)  q := p.offset(8)  load_i64(p) }', 'accept'),            # offset(p, 8) via UFCS

    # --- STRUCT-LITERAL FIELDS: every init field must EXIST + its value must FIT ---
    ('P*: { x: i32 }\ntest* = () i32 { p := P(x: 0, y: 1)  p.x }', 'reject'),               # unknown field y
    ('P*: { x: i32 }\ntest* = () i32 { p := P(z: 0)  0 }', 'reject'),                       # unknown field z
    ('P*: { x: i32, flag: bool }\nmk* = () i64 { 5 }\ntest* = () i32 { p := P(x: mk())  p.x }', 'reject'),  # i64 ⊀ i32 field
    ('P*: { x: i32, flag: bool }\ntest* = () i32 { p := P(x: 0, flag: true)  p.x }', 'accept'),
    ('P*: { x: i32 }\ntest* = () i32 { p := P(x: 0)  p.x }', 'accept'),

    # --- FIELD ACCESS: obj.field must name a real field of obj's struct (value + Ptr receiver) ---
    ('P*: { x: i32 }\ntest* = () i32 { p := P(x: 5)  p.nope }', 'reject'),
    ('P*: { x: i32 }\nget* = (p: Ptr<P>) i32 { p.bad }\ntest* = () i32 { q := P(x: 1)  get(q.addr()) }', 'reject'),
    ('P*: { x: i32, y: i32 }\ntest* = () i32 { p := P(x: 5, y: 6)  p.x + p.y }', 'accept'),

    # --- MATCH EXHAUSTIVENESS: an enum match must cover every variant (or have `_`) ---
    ('C*: A | B | Cc\nf* = (c: C) i32 { c.match({ .A => 1, .B => 2 }) }\ntest* = () i32 { f(.A()) }', 'reject'),          # missing .Cc
    ('R*: Ok(i32) | Err\nf* = (r: R) i32 { r.match({ .Ok(v) => v }) }\ntest* = () i32 { f(.Ok(5)) }', 'reject'),         # missing .Err
    ('C*: A | B | Cc\nf* = (c: C) i32 { c.match({ .A => 1, .B => 2, .Cc => 3 }) }\ntest* = () i32 { f(.A()) }', 'accept'),
    ('C*: A | B | Cc\nf* = (c: C) i32 { c.match({ .A => 1, _ => 0 }) }\ntest* = () i32 { f(.A()) }', 'accept'),          # wildcard covers

    # --- MATCH DUPLICATE VARIANT: no arm may repeat a variant ---
    ('C*: A | B\nf* = (c: C) i32 { c.match({ .A => 1, .A => 2, .B => 3 }) }\ntest* = () i32 { f(.A()) }', 'reject'),
    ('R*: Ok(i32) | Err\nf* = (r: R) i32 { r.match({ .Ok(v) => v, .Ok(w) => w, .Err => 0 }) }\ntest* = () i32 { f(.Ok(5)) }', 'reject'),
    ('C*: A | B\nf* = (c: C) i32 { c.match({ .A => 1, .B => 2 }) }\ntest* = () i32 { f(.A()) }', 'accept'),

    # --- OPERAND TYPES: arith `+ - * /` needs numeric, logic `&& ||` needs bool ---
    ('P*: { x: i32 }\ntest* = () i32 { p := P(x: 1)  q := P(x: 2)  (p + q).x }', 'reject'),  # struct + struct
    ('test* = () i32 { ("hi" + "bye")  0 }', 'reject'),                                        # str + str
    ('test* = () bool { 1 && 2 }', 'reject'),                                                  # && on numbers
    ('test* = () bool { true && false }', 'accept'),
    ('test* = () i32 { 1 + 2 * 3 }', 'accept'),

    # --- INDEX: seq[idx] needs a SLICE seq and a NUMERIC idx ---
    ('test* = () i32 { x := 5  x[0] }', 'reject'),                                             # indexing a non-slice
    ('P*: { x: i32 }\ntest* = () i32 { s := [1, 2, 3]  p := P(x: 0)  s[p] }', 'reject'),    # non-numeric index
    ('test* = () i32 { s := [10, 20, 30]  s[1] }', 'accept'),

    # --- RETURN FITS: a returned value must fit the declared return type ---
    ('test* = () i32 { 1 < 2 }', 'reject'),                                                    # concrete bool ⊀ i32
    ('big* = () i64 { 9999999999 }\ntest* = () i32 { big() }', 'reject'),                      # i64 ⊀ i32 (computed narrowing)
    ('test* = () bool { 5 }', 'reject'),                                                       # numeric ⊀ bool
    ('P*: { x: i32 }\ntest* = () i32 { P(x: 5) }', 'reject'),                               # struct ⊀ i32
    ('test* = () bool { 1 < 2 }', 'accept'),                                                   # concrete bool fits bool
    ('small* = () u8 { 3 }\ntest* = () i64 { small() }', 'accept'),                            # u8 widens to i64
    ('test* = () i32 { 42 }', 'accept'),

    # --- ASSIGN FITS: x = v must fit x's let-inferred type ---
    ('test* = () i32 { x := 5\n y := (1 < 2)\n x = y\n x }', 'reject'),                        # bool into i32 local
    ('big* = () i64 { 9999999999 }\ntest* = () i32 { x := 1\n x = big()\n x }', 'reject'),     # i64 into i32 local
    ('test* = () i64 { x := 5000000000\n y := 1\n x = y\n x }', 'accept'),                     # numeric ok

    # --- INDEX-SET FITS: s[i] = v must store the slice's element type ---
    ('test* = () i32 { s := [1, 2, 3]\n s[0] = (1 < 2)\n s[0] }', 'reject'),                   # bool into i32 slice
    ('test* = () i32 { s := [1, 2, 3]\n s[0] = 99\n s[0] }', 'accept'),

    # --- TRAILING VALUE: a non-void fn body must end in a value that fits the return type ---
    ('test* = () i32 { x := 5 }', 'reject'),                                                   # ends in a let -> no value
    ('test* = () i32 { x := 5\n x }', 'accept'),
    ('noop* = () void { x := 5 }\ntest* = () i32 { noop()  0 }', 'accept'),                    # a void fn may end in a let

    # --- TRAIT CONFORMANCE: a Type.impl(Trait) must define every method with a matching signature ---
    ('Show*: { area: (Ptr<Self>) i32 }\nA*: { v: i32 }\nA.impl(Show, { })\ntest* = () i32 { 0 }', 'reject'),                                   # missing method
    ('Show*: { area: (Ptr<Self>) i32 }\nA*: { v: i32 }\nA.impl(Show, { area = (a: Ptr<A>) i64 { 0 } })\ntest* = () i32 { 0 }', 'reject'),        # wrong return type
    ('Dbl*: { f: (Ptr<Self>, i32) i32 }\nA*: { v: i32 }\nA.impl(Dbl, { f = (a: Ptr<A>) i32 { a.v } })\ntest* = () i32 { 0 }', 'reject'),          # wrong arity
    ('Dbl*: { f: (Ptr<Self>, i32) i32 }\nA*: { v: i32 }\nA.impl(Dbl, { f = (a: Ptr<A>, k: i64) i32 { a.v } })\ntest* = () i32 { 0 }', 'reject'),  # wrong param type
    ('Show*: { area: (Ptr<Self>) i32 }\nA*: { v: i32 }\nA.impl(Show, { area = (a: Ptr<A>) i32 { a.v } })\ntest* = () i32 { 0 }', 'accept'),
    ('Eq*: { eq: (Ptr<Self>, Ptr<Self>) bool }\nA*: { v: i32 }\nA.impl(Eq, { eq = (a: Ptr<A>, b: Ptr<A>) bool { 1 < 2 } })\ntest* = () i32 { 0 }', 'accept'),  # Self in two params
    # --- TRAIT DEFAULT METHODS: an omitted method is OK iff the trait gives it a default body ---
    ('Show*: { area = (s: Ptr<Self>) i32 { 1 } }\nA*: { v: i32 }\nA.impl(Show, { })\ntest* = () i32 { 0 }', 'accept'),                              # omit a DEFAULTED method
    ('Show*: { area = (s: Ptr<Self>) i32 { 1 } }\nA*: { v: i32 }\nA.impl(Show, { area = (a: Ptr<A>) i32 { a.v } })\ntest* = () i32 { 0 }', 'accept'), # override a defaulted method
    ('T*: { a = (s: Ptr<Self>) i32 { 1 }, b: (Ptr<Self>) i32 }\nA*: { v: i32 }\nA.impl(T, { })\ntest* = () i32 { 0 }', 'reject'),                    # b has NO default and is omitted
    ('T*: { a = (s: Ptr<Self>) i32 { 1 }, b: (Ptr<Self>) i32 }\nA*: { v: i32 }\nA.impl(T, { b = (s: Ptr<A>) i32 { 2 } })\ntest* = () i32 { 0 }', 'accept'),  # b provided, a defaulted

    # --- DUPLICATE FUNCTION NAMES: two top-level fns of one name collide (Zen has no overloading) ---
    ('f* = (a: i32) i32 { a }\nf* = (a: i32, b: i32) i32 { a + b }\ntest* = () i32 { f(1) }', 'reject'),  # even differing arity
    ('uniq* = () i32 { 1 }\nother* = () i32 { 2 }\ntest* = () i32 { uniq() + other() }', 'accept'),

    # --- VALUE-POSITION EARLY-RETURN: a non-trailing `return` in a value-position block arm is dropped ---
    ('f* = (n: i32) i32 {\n v := n.match({ 0 => { return 1  2 }, _ => 9 })\n v\n}\ntest* = () i32 { f(0) }', 'reject'),
    ('f* = (n: i32) i32 {\n v := n.match({ 0 => { 1 }, _ => 9 })\n v\n}\ntest* = () i32 { f(0) }', 'accept'),

    # --- BLOCK-ARM SUB-EXPRESSION CHECKING: a bad call inside a value-position block arm is still caught ---
    ('f* = (b: bool) i32 { b.match({ true => { ghost()  1 }, false => 0 }) }\ntest* = () i32 { f(1 < 2) }', 'reject'),          # undefined call
    ('g* = (a: i32) i32 { a }\nf* = (b: bool) i32 { b.match({ true => { g(1, 2)  1 }, false => 0 }) }\ntest* = () i32 { f(1 < 2) }', 'reject'),  # mis-arity call
    ('g* = (a: i32) i32 { a }\nf* = (b: bool) i32 { b.match({ true => { g(1)  1 }, false => 0 }) }\ntest* = () i32 { f(1 < 2) }', 'accept'),

    # Bare bool literals are real bool values, not i32 return values.
    ('test* = () i32 { true }', 'reject'),

    # --- PARSER TOTALITY: garbage/truncated input REJECTS — never a silent stop (a truncated module
    #     the checker misreads) and never a wrong-value run. Each of these used to slip through as a
    #     misleading position-less type error or, worse, RUN (`x := 1 @@ 2` ran and returned 2). The
    #     parse-failure flag plants the `__syntax_error` sentinel; kinds are pinned in
    #     VERDICT_KIND_CASES below. ---
    ('f = () i32 {\ntest* = () i32 { 42 }', 'reject'),                # unclosed `{` after a fn header
    ('f = () i32 {', 'reject'),                                       # unclosed `{` at EOF
    ('test* = () i32 { x := (1 + 2  x }', 'reject'),                  # unclosed `(`
    ('test* = () i32 { s := "abc  0 }', 'reject'),                    # unterminated string
    ('test* = () i32 { x := * 3  x }', 'reject'),                     # no expression starts with `*`
    ('test* = () i32 { x := 1 @@ 2  x }', 'reject'),                  # mid-expr garbage (ran as 2!)
    ('test* = () i32 { x := 1  $ ?  x }', 'reject'),                  # garbage statement mid-block (ran as 1!)
    ('f = () i32 { 0 .match ({ 1 => 2', 'reject'),                    # unterminated match record
    ('f* = (b: bool) i32 { b.match ({ true => 1 false => 2 }) }\ntest* = () i32 { f(true) }', 'reject'),   # arms need ','
    ('C*: A | B\nf* = (c: C) i32 { c.match ({ .A => 1 .B => 2 }) }\ntest* = () i32 { f(C.A()) }', 'reject'),
    ('f* = (b: bool) i32 { b.match { true => 1, false => 2 } }\ntest* = () i32 { f(true) }', 'reject'),    # bare-brace match (no parens)
    ('C*: A | B\nf* = (c: C) i32 { c.match ({ .A => 1, 5 => 2 }) }\ntest* = () i32 { f(C.A()) }', 'reject'),  # a literal arm in a variant match (was: silently taken as `_`)
    ('f* = (b: bool) i32 { b.match ({ true => 1, 0 => 2 }) }\ntest* = () i32 { f(true) }', 'reject'),      # a non-bool label in a bool match (was: silently accepted)

    # --- f64 floats: STRICT — no implicit int<->float mixing in EITHER direction (literals included),
    #     and no float `%`, bitwise, or shifts. f64 op f64 (+ - * / and the comparisons) accepts. ---
    ('test* = () f64 { 1.5 * 2.0 }', 'accept'),
    ('test* = () i32 { (0.5 <= 0.5).match({ true => 1, false => 0 }) }', 'accept'),
    ('test* = () i32 { to_i32(1.5 + 1.0) }', 'accept'),
    ('test* = () f64 { 1.5 + 1 }', 'reject'),                            # int<->float mix
    ('test* = () f64 { x := 2.0\n x + 1 }', 'reject'),                   # the mix through a local
    ('test* = () f64 { 1.5 % 2.0 }', 'reject'),                          # no float modulo
    ('test* = () f64 { 1.5 & 2.0 }', 'reject'),                          # no float bitwise
    ('test* = () f64 { 1.5 << 1 }', 'reject'),                           # no float shifts
    ('test* = () i32 { x: u8 := 1.5\n to_i32(x) }', 'reject'),           # a float literal never fits an int slot
    ('test* = () i32 { x: i32 := 1.5\n x }', 'reject'),
    ('test* = () f64 { x: f64 := 1\n x }', 'reject'),                    # an int literal never floats — write 1.0
    ('test* = () f64 { 1 }', 'reject'),                                  # return-fit: i32 ⊀ f64
    ('test* = () i32 { 1.5 }', 'reject'),                                # return-fit: f64 ⊀ i32
    ('test* = () i32 { b := 1.5 == 1\n 0 }', 'reject'),                  # mixed equality is the mix too
    ('eat* = (x: f64) f64 { x }\ntest* = () f64 { eat(2) }', 'reject'),  # int arg ⊀ f64 param
    ('test* = () i32 { x := 3\n x.match ({ 0.25 => 1, _ => 9 }) }', 'reject'),   # a float label on an int subject
    # --- lambda-value (LAMBDA-2 safety net): a lambda the inliner can't splice — stored in a field or
    #     returned — is rejected cleanly (was: leaked unlowered C). A local-bound lambda used as a call
    #     arg is NOT here (it's aliased/spliced — see the VALUE cases above). Pinned `reject` (count):
    #     the kind code is 18 and the oracle's check-kind harness masks `& 15`, so the exact
    #     `lambda-value` kind is verified through the driver in test_resolver_fixes.py. ---
    ('S*: { f: (i32) i32 }\ntest* = () i32 {\n  s := S(f: (n) { n + 1 })\n  0\n}', 'reject'),
    ('mk* = () (i32) i32 { (n) { n + 1 } }\ntest* = () i32 { 0 }', 'reject'),
]

# ════════════════════════════════════════════════════════════════════════════════════════════════
# REJECT KINDS — each reject pinned by its FIRST-error KIND (check_validate.check_module_kind), so a
# reject-for-the-wrong-reason no longer slips through. Every (src, kind) here was VERIFIED against the
# real CHECK-KIND binary on the goalz-diagnostics branch — `_oracle.verdict_kind(src) == kind`, AND
# `_oracle.verdict(src) == 'reject'` (kind != 'none'). The kind labels are check_validate.zen's K*
# table: arity / arg-type / undefined-name / struct-field / exhaustiveness / dup-variant /
# operand-type / index / return-fit / assign-fit / conformance / dup-fn / value-pos-return. The same
# srcs already appear in VERDICT_CASES as 'reject'; here their REASON is fixed too. Grouped by kind.
# ════════════════════════════════════════════════════════════════════════════════════════════════
VERDICT_KIND_CASES = [
    # --- arity: a call's arg COUNT must equal the declared param count (local fn OR fixed-arity intrinsic) ---
    ('g* = (x: i32) i32 { x }\nf* = (flags: RawPtr<u8>, i: i32, n: i32) void { (i < n).match({ true => { g(1, 2, 3)  store_i64(flags, 1) }, false => {} }) }\ntest* = () i32 { 0 }', 'arity'),
    ('f* = (flags: RawPtr<u8>, i: i32, n: i32) void { (i < n).match({ true => { store_i64(flags)  store_i64(flags, 1) }, false => {} }) }\ntest* = () i32 { 0 }', 'arity'),
    ('add* = (a: i32, b: i32) i32 { a + b }\ntest* = () i32 { add(1) }', 'arity'),
    ('add* = (a: i32, b: i32) i32 { a + b }\ntest* = () i32 { add(1, 2, 3) }', 'arity'),
    ('zero* = () i32 { 0 }\ntest* = () i32 { zero(1) }', 'arity'),
    ('one* = (a: i32) i32 { a }\ntest* = () i32 { one() }', 'arity'),
    ('test* = () i64 { p := malloc(8)  store_i64(p)  0 }', 'arity'),
    ('test* = () i64 { p := malloc(8)  store_i64(p, 1, 2)  0 }', 'arity'),
    ('test* = () i64 { p := malloc(8)  q := offset(p)  0 }', 'arity'),
    ('test* = () i64 { p := null_ptr(7)  0 }', 'arity'),
    ('g* = (a: i32) i32 { a }\nf* = (b: bool) i32 { b.match({ true => { g(1, 2)  1 }, false => 0 }) }\ntest* = () i32 { f(1 < 2) }', 'arity'),   # mis-arity inside a block arm

    # --- arg-type: right arity, but an arg's type doesn't `fit` its parameter ---
    ('takes_u8* = (b: u8) i32 { 0 }\nbig* = () i64 { 9999999999 }\ntest* = () i32 { takes_u8(big()) }', 'arg-type'),     # i64 ⊀ u8
    ('P*: { x: i32 }\nneeds_p* = (p: P) i32 { p.x }\nmk* = () i64 { 5 }\ntest* = () i32 { needs_p(mk()) }', 'arg-type'),  # i64 where P wanted
    ('A*: { v: i32 }\nB*: { v: i32 }\nneeds_a* = (a: A) i32 { a.v }\ntest* = () i32 { needs_a(B(v: 5)) }', 'arg-type'), # B ⊀ A
    ('scalar* = (n: i32) i32 { n }\ntest* = () i32 { s := [1, 2]\n scalar(s) }', 'arg-type'),                            # slice ⊀ scalar

    # --- undefined-name: a call to a non-local, non-intrinsic, non-imported, non-trait name ---
    ('test* = () i32 { nope() }', 'undefined-name'),
    ('test* = () i32 { foo(1) + bar(2) }', 'undefined-name'),
    ('use* = (n: i32) i32 { n }\ntest* = () i32 { use(missing()) }', 'undefined-name'),                                  # nested in an arg
    ('test* = () i32 { 1 + gone() }', 'undefined-name'),                                                                 # nested in an operand
    ('f* = (b: bool) i32 { b.match({ true => { ghost()  1 }, false => 0 }) }\ntest* = () i32 { f(1 < 2) }', 'undefined-name'),  # inside a block arm
    # A bool/literal match with a SINGLE non-`_` arm is non-exhaustive (its lone value-arm becomes a
    # subject-ignoring default — #96). The parser, having no error channel, lowers it to a call to an
    # undefined sentinel (`__nonexhaustive_match`), so the validator rejects it as an undefined name.
    ('f* = (b: bool) i32 {\n b.match({ false => { return 9 } })\n 7\n}\ntest* = () i32 { f(false) }', 'undefined-name'),  # single non-`_` bool arm
    ('f* = (b: bool) i32 {\n b.match({ false => 9 })\n}\ntest* = () i32 { f(false) }', 'undefined-name'),                 # single non-`_` bool arm (expr body)
    ('f* = (n: i32) i32 {\n n.match({ 0 => 9 })\n}\ntest* = () i32 { f(5) }', 'undefined-name'),                          # single non-`_` literal arm
    ('f* = (b: bool) i32 {\n if (b) { return 9 }\n 7\n}\ntest* = () i32 { f(true) }', 'undefined-name'),                         # `if` parses as an undefined call
    ('f* = (b: bool) i32 {\n if (b) { return 9 } else { return 8 }\n 7\n}\ntest* = () i32 { f(false) }', 'undefined-name'),

    # --- struct-field: a struct-literal init field / a member access that names no real field, or a mistyped init ---
    ('P*: { x: i32 }\ntest* = () i32 { p := P(x: 0, y: 1)  p.x }', 'struct-field'),                                   # unknown init field y
    ('P*: { x: i32 }\ntest* = () i32 { p := P(z: 0)  0 }', 'struct-field'),                                           # unknown init field z
    ('P*: { x: i32, flag: bool }\nmk* = () i64 { 5 }\ntest* = () i32 { p := P(x: mk())  p.x }', 'struct-field'),       # i64 ⊀ i32 field
    ('P*: { x: i32 }\ntest* = () i32 { p := P(x: 5)  p.nope }', 'struct-field'),                                      # member access
    ('P*: { x: i32 }\nget* = (p: Ptr<P>) i32 { p.bad }\ntest* = () i32 { q := P(x: 1)  get(q.addr()) }', 'struct-field'),  # Ptr receiver

    # --- exhaustiveness: a non-wildcard enum match must cover every variant ---
    ('R*: Ok(i32) | Err\nf* = (r: R) i32 {\n r.match({ .Err => { return 9 } })\n 7\n}\ntest* = () i32 { f(.Ok(0)) }', 'exhaustiveness'),  # missing .Ok
    ('C*: A | B | Cc\nf* = (c: C) i32 { c.match({ .A => 1, .B => 2 }) }\ntest* = () i32 { f(.A()) }', 'exhaustiveness'),  # missing .Cc
    ('R*: Ok(i32) | Err\nf* = (r: R) i32 { r.match({ .Ok(v) => v }) }\ntest* = () i32 { f(.Ok(5)) }', 'exhaustiveness'), # missing .Err

    # --- dup-variant: a match arm repeats a variant ---
    ('C*: A | B\nf* = (c: C) i32 { c.match({ .A => 1, .A => 2, .B => 3 }) }\ntest* = () i32 { f(.A()) }', 'dup-variant'),
    ('R*: Ok(i32) | Err\nf* = (r: R) i32 { r.match({ .Ok(v) => v, .Ok(w) => w, .Err => 0 }) }\ntest* = () i32 { f(.Ok(5)) }', 'dup-variant'),

    # --- operand-type: arith on non-numeric / logic on non-bool ---
    ('P*: { x: i32 }\ntest* = () i32 { p := P(x: 1)  q := P(x: 2)  (p + q).x }', 'operand-type'),                  # struct + struct
    ('test* = () i32 { ("hi" + "bye")  0 }', 'operand-type'),                                                            # str + str
    ('test* = () bool { 1 && 2 }', 'operand-type'),                                                                      # && on numbers

    # --- index: seq[idx] with a non-slice seq or a non-numeric idx ---
    ('test* = () i32 { x := 5  x[0] }', 'index'),                                                                        # non-slice seq
    ('P*: { x: i32 }\ntest* = () i32 { s := [1, 2, 3]  p := P(x: 0)  s[p] }', 'index'),                               # non-numeric idx

    # --- return-fit: a returned / trailing value doesn't fit (or is absent for) the declared return type ---
    ('test* = () i32 {  }', 'return-fit'),                                                                               # empty body
    ('test* = () i32 {\n  x := 5\n}', 'return-fit'),                                                                     # ends in a let
    ('test* = () i32 {\n  x := 5\n  x = 6\n}', 'return-fit'),                                                            # ends in an assign
    ('test* = () i32 { "hi" }', 'return-fit'),                                                                           # str ⊀ i32
    ('test* = () i32 { 1 < 2 }', 'return-fit'),                                                                          # bool ⊀ i32
    ('big* = () i64 { 9999999999 }\ntest* = () i32 { big() }', 'return-fit'),                                            # i64 ⊀ i32
    ('test* = () bool { 5 }', 'return-fit'),                                                                             # numeric ⊀ bool
    ('P*: { x: i32 }\ntest* = () i32 { P(x: 5) }', 'return-fit'),                                                     # struct ⊀ i32
    ('C*: A | B\ntest* = () i32 { c := C.A()  c.match({ .A => 1, .B => "bad" }) }', 'return-fit'),                    # enum match string/non-string result mismatch
    ('C*: A | B\ntest* = () i32 { c := C.A()  bad := c.match({ .A => 1, .B => (1 < 2) })  0 }', 'return-fit'),       # enum match i32/bool result mismatch
    ('test* = () i32 { x := 5 }', 'return-fit'),                                                                         # trailing let, no value

    # --- assign-fit: x = v (or xs[i] = v) where v doesn't fit x's / the element's type ---
    ('test* = () i32 { x := 5\n y := (1 < 2)\n x = y\n x }', 'assign-fit'),                                              # bool into i32 local
    ('big* = () i64 { 9999999999 }\ntest* = () i32 { x := 1\n x = big()\n x }', 'assign-fit'),                           # i64 into i32 local
    ('test* = () i32 { s := [1, 2, 3]\n s[0] = (1 < 2)\n s[0] }', 'assign-fit'),                                         # bool into i32 slice elem

    # --- conformance: a Type.impl(Trait) misses a method or its signature differs ---
    ('Show*: { area: (Ptr<Self>) i32 }\nA*: { v: i32 }\nA.impl(Show, { })\ntest* = () i32 { 0 }', 'conformance'),                                  # missing method
    ('Show*: { area: (Ptr<Self>) i32 }\nA*: { v: i32 }\nA.impl(Show, { area = (a: Ptr<A>) i64 { 0 } })\ntest* = () i32 { 0 }', 'conformance'),       # wrong return type
    ('Dbl*: { f: (Ptr<Self>, i32) i32 }\nA*: { v: i32 }\nA.impl(Dbl, { f = (a: Ptr<A>) i32 { a.v } })\ntest* = () i32 { 0 }', 'conformance'),         # wrong arity
    ('Dbl*: { f: (Ptr<Self>, i32) i32 }\nA*: { v: i32 }\nA.impl(Dbl, { f = (a: Ptr<A>, k: i64) i32 { a.v } })\ntest* = () i32 { 0 }', 'conformance'), # wrong param type

    # --- dup-fn: two top-level fns share a name (Zen has no overloading) ---
    ('foo* = () i32 { 1 }\nfoo* = () i32 { 2 }\ntest* = () i32 { foo() }', 'dup-fn'),
    ('a* = () i32 { 1 }\ndup* = () i32 { 2 }\ndup* = () i32 { 3 }\ntest* = () i32 { a() }', 'dup-fn'),
    ('f* = (a: i32) i32 { a }\nf* = (a: i32, b: i32) i32 { a + b }\ntest* = () i32 { f(1) }', 'dup-fn'),                  # even differing arity

    # --- value-pos-return: an early (dropped) `return` in a value-position block arm ---
    ('R*: Ok(i32) | Err(i32)\nf* = (r: R) i32 {\n v := r.match({ .Ok(x) => { return x  x + 1 }, .Err(e) => e })\n v + 1\n}\ntest* = () i32 { f(.Ok(5)) }', 'value-pos-return'),
    ('f* = (b: bool) i32 {\n v := b.match({ true => { return 7  9 }, false => 0 })\n v\n}\ntest* = () i32 { f(true) }', 'value-pos-return'),
    ('f* = (n: i32) i32 {\n v := n.match({ 0 => { return 1  2 }, _ => 9 })\n v\n}\ntest* = () i32 { f(0) }', 'value-pos-return'),

    # --- parse (KPARSE): PARSER TOTALITY — garbage/truncated input is rejected AS A PARSE ERROR (the
    #     `__syntax_error` sentinel, planted first), not misreported as a knock-on type error from the
    #     truncated tree. Each shape used to surface as a position-less return-fit/undefined-name — or
    #     silently RUN with a wrong value (`x := 1 @@ 2` returned 2; `$ ?` was dropped). ---
    ('f = () i32 {\ntest* = () i32 { 42 }', 'parse'),                 # unclosed `{` after a fn header (was undefined-name)
    ('f = () i32 {', 'parse'),                                        # unclosed `{` at EOF (was return-fit)
    ('test* = () i32 { x := (1 + 2  x }', 'parse'),                   # unclosed `(` (was return-fit)
    ('test* = () i32 { s := "abc  0 }', 'parse'),                     # unterminated string (was return-fit)
    ('test* = () i32 { x := * 3  x }', 'parse'),                      # no expression starts with `*` (was return-fit)
    ('test* = () i32 { x := 1 @@ 2  x }', 'parse'),                   # mid-expr garbage (was ACCEPTED, ran as 2)
    ('test* = () i32 { x := 1  $ ?  x }', 'parse'),                   # garbage statement mid-block (was ACCEPTED, ran as 1)
    ('f = () i32 { 0 .match ({ 1 => 2', 'parse'),                     # unterminated match record (was undefined-name)
    ('f* = (b: bool) i32 { b.match ({ true => 1 false => 2 }) }\ntest* = () i32 { f(true) }', 'parse'),    # bool arms need ','
    ('C*: A | B\nf* = (c: C) i32 { c.match ({ .A => 1 .B => 2 }) }\ntest* = () i32 { f(C.A()) }', 'parse'),  # variant arms need ','
    ('f* = (b: bool) i32 { b.match { true => 1, false => 2 } }\ntest* = () i32 { f(true) }', 'parse'),     # bare-brace match (parens required)
    ('C*: A | B\nf* = (c: C) i32 { c.match ({ .A => 1, 5 => 2 }) }\ntest* = () i32 { f(C.A()) }', 'parse'),  # a literal arm in a variant match (was: silently the `_` catch-all)

    # --- f64: a mix / a float operator outside the f64 surface pins to operand-type; a float
    #     into an int slot (and vice versa) pins to the fit kinds — never a misreported kind. ---
    ('test* = () f64 { 1.5 + 1 }', 'operand-type'),
    ('test* = () f64 { 1.5 % 2.0 }', 'operand-type'),
    ('test* = () i32 { x: u8 := 1.5\n to_i32(x) }', 'assign-fit'),
    ('test* = () i32 { 1.5 }', 'return-fit'),
]
