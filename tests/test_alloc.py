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


def test_vec_grows_through_its_allocator(compile_main):
    # a Vec carries no allocator of its own — push takes it explicitly. Start at cap 2,
    # push 4 (forcing a grow via the allocator's resize), sum the items view -> 10.
    rc = compile_main("""
{ Malloc } = std.alloc
{ Vec, vec, push, items, vfree } = std.vec
main* = () i32 {
    m := Malloc { _: 0 }
    v := addr(m).vec(2)
    v = v.push(addr(m), 1)
    v = v.push(addr(m), 2)
    v = v.push(addr(m), 3)
    v = v.push(addr(m), 4)
    s := 0
    addr(v).items().loop((h, i, x) { s = s + x })
    v.vfree(addr(m))
    s
}
""")
    assert rc == 10
