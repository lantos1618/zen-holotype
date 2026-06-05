"""std.alloc — an explicit, Zig-style allocator. A function that allocates takes the
allocator as a parameter (no hidden malloc); a `<A: Allocator>` bound monomorphizes,
so dispatch is zero-cost. UFCS reads `a.acquire(n)` for `acquire(a, n)`."""


def test_explicit_allocator_through_malloc(compile_main):
    # a generic <A: Allocator> fn acquires/releases through whatever allocator it's
    # handed; here the libc-backed Malloc. UFCS: a.acquire(n) / a.release(p).
    rc = compile_main("""
{ Allocator, Malloc, acquire, release } = std.alloc
roundtrip*<A: Allocator> = (a: Ptr<A>) i32 {
    p := a.acquire(4)
    store(p, 42)
    v := load(p)
    a.release(p)
    v
}
main* = () i32 { m := Malloc { _: 0 }\n addr(m).roundtrip() }
""")
    assert rc == 42


def test_generic_vec_grows(tmp_path):
    # std.vec is now a GENERIC `Vec<T>` (generic struct literals → @self-hosted-only, skipped by the
    # Python loader). The self-hosted toolchain can't yet LINK an imported module (awaits the module
    # resolver), so we exercise the same mechanics self-contained: build from a slice, push past the
    # capacity (forcing a grow+copy), then read back through a second generic call. T = i32 here.
    from _selfhost import run_value
    run_value(tmp_path, """
malloc = (n: i64) RawPtr<u8>
Vec<T>: { ptr: RawPtr<u8>, len: i64, cap: i64 }
buf<T> = (v: Vec<T>) [T] { slice(v.ptr, v.cap) }
get<T> = (v: Vec<T>, i: i64) T { v.buf()[i] }
vlen<T> = (v: Vec<T>) i64 { v.len }
vec_of<T> = (xs: [T]) Vec<T> {
  v := Vec<T>{ ptr: malloc(xs.len * sizeof(T)), len: xs.len, cap: xs.len }
  b := v.buf()
  xs.loop((h, i, x) { b[i] = x })
  v
}
grow<T> = (v: Vec<T>) Vec<T> {
  ncap := (v.cap * 2) + 1
  nv := Vec<T>{ ptr: malloc(ncap * sizeof(T)), len: v.len, cap: ncap }
  nb := nv.buf()
  v.buf().loop((h, i, x) { nb[i] = x })
  nv
}
push<T> = (v: Vec<T>, x: T) Vec<T> {
  r := (v.len < v.cap).match ({ true => v, false => v.grow() })
  b := r.buf()
  b[r.len] = x
  Vec<T>{ ptr: r.ptr, len: r.len + 1, cap: r.cap }
}
test* = () i32 {
  v := vec_of([1, 2])
  v = v.push(3)
  v = v.push(4)
  v.get(0) + v.get(1) + v.get(2) + v.get(3) + v.vlen()
}
""", 14)   # 1+2+3+4 + len 4 = 14
