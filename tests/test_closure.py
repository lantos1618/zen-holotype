"""Closures-as-values. A function with a closure-typed (`(A, B) C`) parameter is
an *inline template*: it is never emitted as a standalone C function. Each call
site splices the template body as a GNU statement-expression, with the closure
argument inlined where the parameter is called. So closures are zero-cost (no
function pointers) and captures resolve in the caller's scope — they read AND
mutate exactly as written. The emitted C stays warning-clean under
-Wall -Wextra -Werror."""
import subprocess
import pytest

from holotype.main import (load, build_space, build_scopes, resolve, check, emit_c)
from holotype.parser import parse


def build(tmp_path, src):
    (tmp_path / "m.zen").write_text(src)
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    results, passing = check(files, space)
    c = emit_c(files, passing, space)
    return results, passing, c


def run(tmp_path, c, entry="main"):
    cfile = tmp_path / "o.c"
    cfile.write_text(c + f"\nint main(void){{ return m_{entry}(); }}\n")
    # hardened: the emitted C must be warning-clean under -Wall -Wextra -Werror
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-std=gnu11",
                        str(cfile), "-o", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run([str(tmp_path / "o")]).returncode


_FOLD = """
fold = (xs: [i32], init: i32, f: (i32, i32) i32) i32 {
    acc := init
    xs.loop((h, i, x) { acc = f(acc, x) })
    acc
}
"""


def test_fold_sum(tmp_path):
    results, _, c = build(tmp_path, _FOLD + """
main* = () i32 { fold([10, 20, 30], 0, (a, x) { a + x }) }
""")
    assert ("m.main", True, "ok") in results
    assert run(tmp_path, c) == 60


def test_fold_product_same_template_two_closures(tmp_path):
    # one template, two distinct closures at two call sites — each inlined separately
    results, _, c = build(tmp_path, _FOLD + """
main* = () i32 {
    s := fold([10, 20, 30], 0, (a, x) { a + x })
    p := fold([1, 2, 3, 4], 1, (a, x) { a * x })
    s + p
}
""")
    assert ("m.main", True, "ok") in results
    assert run(tmp_path, c) == 60 + 24


def test_template_is_never_a_standalone_c_function(tmp_path):
    # a closure type has no C type — the template is inlined, never emitted as `fold(...)`
    _, _, c = build(tmp_path, _FOLD + """
main* = () i32 { fold([1, 2, 3], 0, (a, x) { a + x }) }
""")
    assert "m_fold" not in c                 # no standalone definition or call
    assert "({" in c                         # inlined as a GNU statement-expression


def test_void_closure_with_mutation_capture(tmp_path):
    # the closure mutates a caller local `r`; because it is inlined, the write lands
    # on the real `r` in the caller's scope — no by-value copy, no function pointer
    results, _, c = build(tmp_path, """
each = (xs: [i32], f: (i32) void) void {
    xs.loop((h, i, x) { f(x) })
}
main* = () i32 {
    r := 0
    each([10, 20, 40], (x) { r = r + x })
    r
}
""")
    assert ("m.main", True, "ok") in results
    assert run(tmp_path, c) == 70


def test_capture_read_from_caller_scope(tmp_path):
    # the closure reads a caller local `base` it never received as a parameter
    results, _, c = build(tmp_path, _FOLD + """
main* = () i32 {
    base := 10
    fold([1, 2, 3], 0, (a, x) { a + x + base })
}
""")
    assert ("m.main", True, "ok") in results
    assert run(tmp_path, c) == 10 * 3 + (1 + 2 + 3)   # base added once per element (< 256)


def test_param_shadowing_caller_local_is_safe(tmp_path):
    # the closure param `a` and the argument expression both name `a`-ish things;
    # the temp-first binding must avoid C self-initialization shadowing
    results, _, c = build(tmp_path, _FOLD + """
main* = () i32 {
    acc := 5
    fold([1, 2, 3], acc, (a, x) { a + x })
}
""")
    assert ("m.main", True, "ok") in results
    assert run(tmp_path, c) == 5 + 1 + 2 + 3


def test_closure_return_type_must_fit_param(tmp_path):
    # the closure body yields bool but the FnT result is i32 -> a located error
    results, _, _ = build(tmp_path, _FOLD + """
main* = () i32 { fold([1, 2, 3], 0, (a, x) { a < x }) }
""")
    assert any(q == "m.main" and not ok and "bool" in why and "i32" in why
               for q, ok, why in results)


def test_bare_closure_needs_a_function_type(tmp_path):
    # a closure with no expected FnT (e.g. bound to a plain local) is rejected
    results, _, _ = build(tmp_path, """
main* = () i32 {
    f := (a, x) { a + x }
    0
}
""")
    assert any(q == "m.main" and not ok for q, ok, why in results)


def test_closure_parses(tmp_path):
    # the closure literal `(a, x) { body }` parses (block-trailing, not a paren-expr)
    parse("f = (g: (i32, i32) i32) i32 { g(1, 2) }\n"
          "main* = () i32 { f((a, b) { a + b }) }", "m")
