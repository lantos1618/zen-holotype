"""The raw intrinsics, each exercised end-to-end in isolation: addr / load / store /
offset / slice / sizeof / cstr. Each is special-cased in THREE phases (check in types.py,
lower in lower.py, monomorphization scan in emit.py); a refactor that drops one in one
phase fails the matching test here, instead of surfacing buried in a complex stdlib test.
Byte values are char literals ('h'), never raw ASCII codes.
"""
import subprocess

from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


def run(tmp_path, src):
    (tmp_path / "main.zen").write_text(src)
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)
    assert "main.main" in passing
    c = emit_c(files, passing, namespace, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-std=gnu11",
                        str(tmp_path / "o.c"), "-o", str(tmp_path / "o")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run([str(tmp_path / "o")]).returncode


def test_addr_load_store(tmp_path):
    # addr takes a pointer to a local; store writes through it; load reads it back
    assert run(tmp_path, "main* = () i32 { n := 5\n p := addr(n)\n store(p, 7)\n load(p) }") == 7


def test_offset(tmp_path):
    # offset does pointer arithmetic over a raw buffer
    assert run(tmp_path, """
{ alloc } = std.mem
main* = () i32 {
    p := alloc(4)
    store(p, 3)
    store(offset(p, 1), 4)
    load(p) + load(offset(p, 1))
}
""") == 7


def test_slice(tmp_path):
    # slice reinterprets a raw pointer as a [T] view; index read/write through it
    assert run(tmp_path, """
{ alloc } = std.mem
buf = (n: i64) [i32] { slice(alloc(n * 4), n) }
main* = () i32 {
    xs := buf(3)
    xs[0] = 10
    xs[1] = 20
    xs[2] = 30
    xs[0] + xs[1] + xs[2]
}
""") == 60


def test_sizeof(tmp_path):
    assert run(tmp_path, "Pair*: { a: i32, b: i32 }\n"
                         "main* = () i32 { (sizeof(Pair) == 8).match { true => 1, false => 0 } }") == 1


def test_cstr(tmp_path):
    # build a NUL-terminated buffer at runtime, view it as a str, compare
    assert run(tmp_path, """
{ alloc } = std.mem
{ eq } = std.str
main* = () i32 {
    p := alloc(3)
    store(p, 'h')
    store(offset(p, 1), 'i')
    store(offset(p, 2), '\\0')
    eq(cstr(p), "hi").match { true => 1, false => 0 }
}
""") == 1
