"""Phase 1 — first-class lambdas in the self-hosted toolchain.

Increment A (this file's current scope): the parser accepts lambda values `(a, x) { body }`
and tells them apart from parenthesized expressions (the trailing `{` decides). Proven via
std.genc.gen_sexpr, which renders a parsed lambda as `(lambda <names>)`. Later increments add
checking (against the FnT it's passed to) and inline lowering so a lambda actually RUNS.
"""
import subprocess

import pytest

from zen.main import (load, build_namespace, build_scopes, resolve,
                      fold_comptime, run_emits, check, emit_c)

_DRIVER = """
{ Malloc } = std.alloc
{ parse } = std.parse
{ gen_sexpr } = std.genc
{ String, new, bytes } = std.string
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
main* = () i32 {
    m := Malloc { _: 0 }
    emit(new().gen_sexpr(addr(m).parse("%s")))
    0
}
"""


def _sexpr(tmp_path, expr):
    (tmp_path / "main.zen").write_text(_DRIVER % expr)
    files = load(tmp_path); ns = build_namespace(files)
    build_scopes(files); resolve(files, ns)
    fold_comptime(files, ns); run_emits(files, ns)
    _, passing = check(files, ns)
    c = emit_c(files, passing, ns, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                          capture_output=True, text=True).returncode == 0
    return subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout


@pytest.mark.parametrize("expr,want", [
    ("(n) { n + 1 }",          "(lambda n)"),
    ("(acc, x) { acc + x }",   "(lambda acc x)"),
    ("(a, b, c) { a }",        "(lambda a b c)"),
    ("() { 42 }",              "(lambda)"),
    # a lambda as a call argument — the real usage (higher-order calls like map/fold)
    ("map(xs, (n) { n * 2 })", "(map xs (lambda n))"),
    ("fold(xs, 0, (a, x) { a + x })", "(fold xs 0 (lambda a x))"),
])
def test_lambda_parses(tmp_path, expr, want):
    assert _sexpr(tmp_path, expr) == want


@pytest.mark.parametrize("expr,want", [
    # a parenthesized expression must NOT be mistaken for a lambda (no trailing brace)
    ("(a + b) * c", "(* (+ a b) c)"),
    ("(x)",         "x"),
    ("(a, b)",      None),     # a bare paren-pair with no body isn't a lambda; just parses the first
])
def test_parens_not_mistaken_for_lambda(tmp_path, expr, want):
    out = _sexpr(tmp_path, expr)
    if want is not None:
        assert out == want
    assert "lambda" not in out
