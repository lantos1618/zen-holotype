"""UFCS: `x.f(a, b)` is sugar for `f(x, a, b)` — the receiver becomes the first
argument. It desugars uniformly in the checker, the reachability scanner, and the
lowerer, so it resolves free functions and trait-bound methods exactly as the
free-call form does (the loop handle's `h.break()`/`h.continue()` stay special)."""
import subprocess

from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


def build(tmp_path, src):
    (tmp_path / "main.zen").write_text(src)
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    results, passing = check(files, namespace)
    return results, passing, namespace, files


def run(tmp_path, files, passing, namespace):
    c = emit_c(files, passing, namespace)
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-std=gnu11",
                        str(tmp_path / "o.c"), "-o", str(tmp_path / "o")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run([str(tmp_path / "o")]).returncode


def test_ufcs_on_a_free_function(tmp_path):
    _, passing, ns, files = build(tmp_path, "dbl* = (n: i32) i32 { n * 2 }\nmain* = () i32 { 21.dbl() }")
    assert "main.main" in passing
    assert run(tmp_path, files, passing, ns) == 42


def test_ufcs_passes_extra_args(tmp_path):
    # x.f(a, b) == f(x, a, b)
    _, passing, ns, files = build(tmp_path,
        "add3* = (a: i32, b: i32, c: i32) i32 { a + b + c }\nmain* = () i32 { 1.add3(2, 3) }")
    assert run(tmp_path, files, passing, ns) == 6


def test_ufcs_chains(tmp_path):
    _, passing, ns, files = build(tmp_path,
        "inc* = (n: i32) i32 { n + 1 }\ndbl* = (n: i32) i32 { n * 2 }\nmain* = () i32 { 5.inc().dbl() }")
    assert run(tmp_path, files, passing, ns) == 12


def test_ufcs_dispatches_a_bound_trait_method(tmp_path):
    # t.scale(k) on a bounded T: Scale resolves the trait method and the impl is
    # reached for codegen (regression: the scanner ignored MethodCall, so the impl
    # was called but never emitted -> implicit declaration at cc).
    _, passing, ns, files = build(tmp_path, """
P*: { x: i32, y: i32 }
Scale*: { scale: (Ptr<Self>, i32) i32 }
P.impl(Scale) { scale = (p: Ptr<P>, k: i32) i32 { (p.x + p.y) * k } }
go*<T: Scale> = (t: Ptr<T>) i32 { t.scale(2) }
main* = () i32 { q := P { x: 3, y: 4 }\n go(addr(q)) }
""")
    assert "main.main" in passing
    assert run(tmp_path, files, passing, ns) == 14          # (3+4)*2, impl reached & emitted


def test_ufcs_and_free_form_emit_identical_c(tmp_path):
    # the desugar is exact: `x.f()` and `f(x)` produce the same code.
    a = emit_c(*_ce(tmp_path / "a", "dbl* = (n: i32) i32 { n * 2 }\nmain* = () i32 { 21.dbl() }"))
    b = emit_c(*_ce(tmp_path / "b", "dbl* = (n: i32) i32 { n * 2 }\nmain* = () i32 { dbl(21) }"))
    line_a = [l for l in a.splitlines() if "main_main" in l and "return" in l][0]
    line_b = [l for l in b.splitlines() if "main_main" in l and "return" in l][0]
    assert line_a == line_b == "int32_t main_main(void) { return main_dbl(21); }"


def _ce(d, src):
    d.mkdir(parents=True, exist_ok=True)
    (d / "main.zen").write_text(src)
    files = load(d)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)
    return files, passing, namespace
