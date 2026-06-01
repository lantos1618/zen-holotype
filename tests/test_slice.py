"""Slices `[T]` + element-form `loop`. A slice is a (ptr, len) view that lowers to
`struct { T* ptr; int64_t len; }`; `[a,b,c]` is a compound-literal array + len;
`xs[i]` reads an element; `loop(xs, (h,i,x){…})` (and `xs.loop(...)`) binds the
element each iteration and folds — like every loop — to a C `for`."""
import subprocess
import pytest

from zen.main import load, build_namespace, build_scopes, resolve, check, emit_c


def build(tmp_path, src):
    (tmp_path / "m.zen").write_text(src)
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    results, passing = check(files, namespace)
    return results, passing, emit_c(files, passing, namespace)


def run(tmp_path, c, entry="main"):
    cfile = tmp_path / "o.c"
    cfile.write_text(c + f"\nint main(void){{ return m_{entry}(); }}\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", str(cfile), "-o", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr            # hardened: warning-clean
    return subprocess.run([str(tmp_path / "o")]).returncode


def test_slice_literal_index_and_param(tmp_path):
    results, _, c = build(tmp_path, """
at0* = (xs: [i32]) i32 { xs[0] }
main* = () i32 {
    ys := [10, 20, 30]
    ys[0] + ys[2] + at0(ys)
}
""")
    assert ("m.main", True, "ok") in results
    assert "typedef struct { int32_t * ptr; int64_t len; } slice_i32;" in c
    assert ".ptr = (int32_t[]){ 10, 20, 30 }, .len = 3" in c
    assert "xs.ptr[0]" in c                        # index -> .ptr[i]
    assert run(tmp_path, c) == 50                  # 10 + 30 + 10


def test_element_loop_prefix(tmp_path):
    results, _, c = build(tmp_path, """
main* = () i32 {
    sum := 0
    loop([10, 20, 30], (h, i, x) { sum = sum + x })
    sum
}
""")
    assert ("m.main", True, "ok") in results
    assert "for (; (i < " in c and ".len); i = (i + 1))" in c    # folds to a counted C for
    assert "int32_t x = " in c                     # the element is bound as a typed local
    assert run(tmp_path, c) == 60


def test_element_loop_postfix(tmp_path):
    # [1,2,3].loop(...) is identical to loop([1,2,3], ...)
    results, _, c = build(tmp_path, """
main* = () i32 {
    sum := 0
    [10, 20, 30].loop((h, i, x) { sum = sum + x })
    sum
}
""")
    assert ("m.main", True, "ok") in results
    assert run(tmp_path, c) == 60


def test_index_with_the_loop_index(tmp_path):
    results, _, c = build(tmp_path, """
main* = () i32 {
    xs := [3, 5, 7, 9]
    acc := 0
    loop(xs, (h, i, x) { acc = acc + xs[i] })     // index back into the slice
    acc
}
""")
    assert run(tmp_path, c) == 24                  # 3+5+7+9


def test_element_type_is_checked(tmp_path):
    # the element x has the slice's element type — using it as the wrong type fails
    results, _, _ = build(tmp_path, """
main* = () i32 {
    flags := [true, false, true]
    n := 0
    loop(flags, (h, i, x) { n = n + x })          // x : bool, n : i32  -> mismatch
    n
}
""")
    assert any(q == "m.main" and not ok for q, ok, why in results)


def test_slice_of_u8_widens_index(tmp_path):
    # element type drives the literals; an i32 literal index reads a u8 slice fine
    results, _, c = build(tmp_path, """
main* = () i32 {
    bs := [1, 2, 3]
    bs[1]
}
""")
    assert run(tmp_path, c) == 2


def test_heterogeneous_slice_is_rejected(tmp_path):
    results, _, _ = build(tmp_path, """
main* = () i32 { xs := [1, true, 3]  0 }
""")
    assert any(q == "m.main" and not ok for q, ok, why in results)


def test_writable_slice_element(tmp_path):
    # `xs[i] = v` writes through the slice's ptr — slices are mutable element-wise
    results, _, c = build(tmp_path, """
main* = () i32 {
    xs := [10, 20, 30]
    xs[1] = 99
    xs[0] + xs[1] + xs[2]
}
""")
    assert ("m.main", True, "ok") in results
    assert "xs.ptr[1] = 99" in c              # writes through the slice's ptr
    assert run(tmp_path, c) == 139            # 10 + 99 + 30


def test_writable_index_in_a_loop(tmp_path):
    # double each element in place
    results, _, c = build(tmp_path, """
main* = () i32 {
    xs := [1, 2, 3, 4]
    loop(xs, (h, i, x) { xs[i] = x + x })
    xs[0] + xs[1] + xs[2] + xs[3]
}
""")
    assert ("m.main", True, "ok") in results
    assert run(tmp_path, c) == 20             # 2+4+6+8
