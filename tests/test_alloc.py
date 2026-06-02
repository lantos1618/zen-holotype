"""std.alloc — an explicit, Zig-style allocator. A function that allocates takes the
allocator as a parameter (no hidden malloc); a `<A: Allocator>` bound monomorphizes,
so dispatch is zero-cost. UFCS reads `a.acquire(n)` for `acquire(a, n)`."""
import subprocess

from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


def build_and_run(tmp_path, src):
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


def test_explicit_allocator_through_malloc(tmp_path):
    # a generic <A: Allocator> fn acquires/releases through whatever allocator it's
    # handed; here the libc-backed Malloc. UFCS: a.acquire(n) / a.release(p).
    rc = build_and_run(tmp_path, """
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
